from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator

from cgg_api.app import create_app
from cgg_api.runtime import RuntimeSettings


SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "contracts" / "schemas"
CALLER_SECRET = "test-refinement-shared-secret"


def _canonical(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _payload(**overrides: object) -> dict[str, object]:
    assist_request: dict[str, object] = {
        "schema_version": 1,
        "request_id": "request-1006-api-1",
        "correlation_id": "correlation-1006-api-1",
        "delivery_id": "delivery-884",
        "package_ref": "openproject://work_packages/756",
        "source_ref": "git://workspace-delivery-art/refinement/756",
        "source_revision": "8db557156a85ddc8ed7ac177d5930242970efb2d",
        "operator": {"id": "operator:workspace-owner"},
        "task": {
            "kind": "metadata_advice",
            "contract_ref": "oos.delivery-refinement.v1",
            "version": "1.0",
        },
        "packet": {
            "packet_id": "refinement-packet-756",
            "packet_revision": "revision-3",
            "source_work_design_receipt_id": "work-design-receipt-756",
        },
        "target": {
            "field_key": "definition_of_ready",
            "field_label": "Definition of Ready",
            "field_kind": "long_text",
            "required": True,
            "source_value": "API_TOKEN=secret-value",
            "draft_value": "Describe verifiable entry conditions.",
            "selected_node_ids": ["feature-756"],
            "allowed_values": [],
        },
        "operator_prompt": "Suggest a concise, testable value without applying it.",
    }
    payload: dict[str, object] = {
        "schema_version": 1,
        "idempotency_key": "refinement-756-api-1",
        "workflow_session_id": "session-756-api-1",
        "execution_id": "execution-756-api-1",
        "requested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "assist_request": assist_request,
        "assist_request_digest": f"sha256:{hashlib.sha256(_canonical(assist_request).encode('utf-8')).hexdigest()}",
        "budget_tokens": 4_000,
    }
    payload.update(overrides)
    return payload


def _validate_request_schema(payload: dict[str, object]) -> None:
    schema = json.loads(
        (SCHEMA_ROOT / "refinement-context-projection-request.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(payload)


class RefinementApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_projects_replays_and_reads_refinement_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    refinement_caller_shared_secret=CALLER_SECRET,
                )
            )
            headers = {
                "x-cgg-caller-id": "operator-orchestration-service",
                "x-cgg-caller-secret": CALLER_SECRET,
            }
            payload = _payload()
            _validate_request_schema(payload)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                first = await client.post(
                    "/v1/context/refinement/projections", json=payload, headers=headers
                )
                replay = await client.post(
                    "/v1/context/refinement/projections", json=payload, headers=headers
                )
                readback = await client.get(
                    "/v1/context/refinement/projections/refinement-756-api-1",
                    headers=headers,
                )

            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(readback.status_code, 200, readback.text)
            self.assertFalse(first.json()["replayed"])
            self.assertTrue(replay.json()["replayed"])
            self.assertNotIn("secret-value", first.text)
            self.assertEqual(readback.json()["status"], "ready")

    async def test_api_denies_conflict_and_unbound_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    refinement_caller_shared_secret=CALLER_SECRET,
                )
            )
            headers = {
                "x-cgg-caller-id": "operator-orchestration-service",
                "x-cgg-caller-secret": CALLER_SECRET,
            }
            first = _payload()
            changed_assist = dict(first["assist_request"])
            changed_assist["operator_prompt"] = "Suggest a different value."
            changed = _payload(
                assist_request=changed_assist,
                assist_request_digest=f"sha256:{hashlib.sha256(_canonical(changed_assist).encode('utf-8')).hexdigest()}",
            )
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    "/v1/context/refinement/projections", json=first, headers=headers
                )
                conflict = await client.post(
                    "/v1/context/refinement/projections", json=changed, headers=headers
                )
                unauthorized = await client.get(
                    "/v1/context/refinement/projections/refinement-756-api-1",
                    headers={
                        "x-cgg-caller-id": "untrusted-caller",
                        "x-cgg-caller-secret": CALLER_SECRET,
                    },
                )

            self.assertEqual(conflict.status_code, 409, conflict.text)
            self.assertEqual(
                conflict.json()["detail"]["code"], "context_projection_replay_conflict"
            )
            self.assertEqual(unauthorized.status_code, 403, unauthorized.text)

    async def test_api_validation_error_does_not_echo_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    refinement_caller_shared_secret=CALLER_SECRET,
                )
            )
            malformed = _payload()
            malformed["unexpected"] = "API_TOKEN=must-not-echo"
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/context/refinement/projections",
                    json=malformed,
                    headers={
                        "x-cgg-caller-id": "operator-orchestration-service",
                        "x-cgg-caller-secret": CALLER_SECRET,
                    },
                )

            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(
                response.json()["detail"]["code"], "context_projection_invalid"
            )
            self.assertNotIn("must-not-echo", response.text)


if __name__ == "__main__":
    unittest.main()
