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
CALLER_SECRET = "test-shared-secret"


def _validate_request_schema(payload: dict[str, object]) -> None:
    schema = json.loads(
        (SCHEMA_ROOT / "work-design-context-projection-request.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(
        payload
    )


def _payload(**overrides: object) -> dict[str, object]:
    context = str(overrides.pop("context", '{"package":"example","API_TOKEN":"secret-value"}'))
    payload: dict[str, object] = {
        "schema_version": 1,
        "request_id": "request-991-api-1",
        "correlation_id": "correlation-991-api-1",
        "idempotency_key": "work-design-991-api-1",
        "workflow_session_id": "session-991-api-1",
        "execution_id": "execution-991-api-1",
        "delivery_id": "delivery-884",
        "package_ref": "openproject://work_packages/991",
        "source_ref": "git://context-governance-gateway/example",
        "source_revision": "c06452ddcf2dedd71299db623c39578142deb89c",
        "operator": {"id": "operator:workspace-owner"},
        "task": {
            "kind": "context_advice",
            "contract_ref": "oos.delivery-work-design.v1",
            "version": "1.0",
            "output_schema_ref": "contract://oos/work-design/assist-result.v1",
            "model_profile_id": "delivery-work-design-advisor-v1",
        },
        "requested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "context": context,
        "context_digest": f"sha256:{hashlib.sha256(context.encode('utf-8')).hexdigest()}",
        "budget_tokens": 4_000,
    }
    payload.update(overrides)
    return payload


class WorkDesignApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_projects_and_replays_receipt_bound_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
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
                    "/v1/context/work-design/projections", json=payload, headers=headers
                )
                replay = await client.post(
                    "/v1/context/work-design/projections", json=payload, headers=headers
                )
                readback = await client.get(
                    "/v1/context/work-design/projections/work-design-991-api-1",
                    headers=headers,
                )

            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(readback.status_code, 200, readback.text)
            self.assertFalse(first.json()["replayed"])
            self.assertTrue(replay.json()["replayed"])
            self.assertEqual(readback.json()["status"], "ready")
            self.assertNotIn("secret-value", first.text)
            self.assertIn('"budget_tokens":4000', first.json()["content"])

    async def test_api_denies_replay_conflict_and_unbound_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
                )
            )
            headers = {
                "x-cgg-caller-id": "operator-orchestration-service",
                "x-cgg-caller-secret": CALLER_SECRET,
            }
            first = _payload()
            changed = _payload(context='{"package":"different"}')
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    "/v1/context/work-design/projections", json=first, headers=headers
                )
                conflict = await client.post(
                    "/v1/context/work-design/projections", json=changed, headers=headers
                )
                unauthorized = await client.get(
                    "/v1/context/work-design/projections/work-design-991-api-1",
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
            self.assertEqual(
                unauthorized.json()["detail"]["code"], "context_projection_unauthorized"
            )

    async def test_api_validation_failure_does_not_echo_request_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
                )
            )
            malformed = _payload()
            malformed["unexpected"] = "API_TOKEN=must-not-echo"
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/context/work-design/projections",
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

    async def test_read_validation_failure_does_not_echo_caller_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
                )
            )
            submitted_secret = "s" * 1_025
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/v1/context/work-design/projections/work-design-991-api-1",
                    headers={
                        "x-cgg-caller-id": "operator-orchestration-service",
                        "x-cgg-caller-secret": submitted_secret,
                    },
                )

            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(
                response.json()["detail"]["code"], "context_projection_invalid"
            )
            self.assertNotIn(submitted_secret, response.text)


if __name__ == "__main__":
    unittest.main()
