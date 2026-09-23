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


CALLER_SECRET = "test-lifecycle-secret"
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "contracts" / "schemas"


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _payload() -> dict[str, object]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    content = "validation passed API_TOKEN=secret-value"
    sources = [
        {
            "source_id": "validation-1164",
            "source_class": "validation",
            "source_ref": "validation://delivery-1164/ci-equivalent",
            "source_revision": "run-22",
            "captured_at": now,
            "availability": "available",
            "content": content,
            "content_digest": _digest(content),
            "unavailable_reason": None,
        },
        {
            "source_id": "runtime-1164",
            "source_class": "runtime",
            "source_ref": "devint://context-governance-gateway/status",
            "source_revision": None,
            "captured_at": now,
            "availability": "unavailable",
            "content": None,
            "content_digest": None,
            "unavailable_reason": "not_configured",
        },
    ]
    return {
        "schema_version": 1,
        "request_id": "request-1164-api",
        "correlation_id": "correlation-1164-api",
        "idempotency_key": "lifecycle-1164-api",
        "workflow_session_id": "session-1164-api",
        "execution_id": "execution-1164-api",
        "delivery_id": "delivery-1164",
        "work_item_ref": "openproject://work_packages/1164",
        "landing_unit_id": "delivery-1154-cgg-lifecycle-projection",
        "operator": {"id": "agent:gary"},
        "lifecycle": {
            "operation": "continue",
            "state": "source-work",
            "next_action": "source-evidence",
        },
        "requested_at": now,
        "sources": sources,
        "sources_digest": _digest(_canonical(sources)),
        "budget_tokens": 4_000,
    }


class LifecycleApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_projects_replays_and_reads_typed_lifecycle_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _payload()
            request_schema = json.loads(
                (SCHEMA_ROOT / "lifecycle-context-projection-request.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            Draft202012Validator.check_schema(request_schema)
            Draft202012Validator(
                request_schema, format_checker=Draft202012Validator.FORMAT_CHECKER
            ).validate(payload)
            app = create_app(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    lifecycle_caller_shared_secret=CALLER_SECRET,
                )
            )
            headers = {
                "x-cgg-caller-id": "operator-orchestration-service",
                "x-cgg-caller-secret": CALLER_SECRET,
            }
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                first = await client.post(
                    "/v1/context/lifecycle/projections", json=payload, headers=headers
                )
                replay = await client.post(
                    "/v1/context/lifecycle/projections", json=payload, headers=headers
                )
                readback = await client.get(
                    "/v1/context/lifecycle/projections/lifecycle-1164-api", headers=headers
                )

            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(readback.status_code, 200, readback.text)
            self.assertFalse(first.json()["replayed"])
            self.assertTrue(replay.json()["replayed"])
            self.assertNotIn("secret-value", first.text)
            self.assertEqual(readback.json()["status"], "ready")

    async def test_api_returns_bounded_errors_without_echoing_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    lifecycle_caller_shared_secret=CALLER_SECRET,
                )
            )
            payload = _payload()
            payload["unexpected"] = "API_TOKEN=must-not-echo"
            valid_payload = _payload()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                invalid = await client.post(
                    "/v1/context/lifecycle/projections",
                    json=payload,
                    headers={
                        "x-cgg-caller-id": "operator-orchestration-service",
                        "x-cgg-caller-secret": CALLER_SECRET,
                    },
                )
                created = await client.post(
                    "/v1/context/lifecycle/projections",
                    json=valid_payload,
                    headers={
                        "x-cgg-caller-id": "operator-orchestration-service",
                        "x-cgg-caller-secret": CALLER_SECRET,
                    },
                )
                unauthorized = await client.get(
                    "/v1/context/lifecycle/projections/lifecycle-1164-api",
                    headers={
                        "x-cgg-caller-id": "untrusted-caller",
                        "x-cgg-caller-secret": CALLER_SECRET,
                    },
                )

            self.assertEqual(invalid.status_code, 422, invalid.text)
            self.assertEqual(invalid.json()["detail"]["code"], "context_projection_invalid")
            self.assertNotIn("must-not-echo", invalid.text)
            self.assertEqual(created.status_code, 200, created.text)
            self.assertEqual(unauthorized.status_code, 403, unauthorized.text)
            self.assertEqual(
                unauthorized.json()["detail"]["code"], "context_projection_unauthorized"
            )

    async def test_api_reports_oversized_source_as_bounded_contract_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    lifecycle_caller_shared_secret=CALLER_SECRET,
                )
            )
            payload = _payload()
            payload["sources"][0]["content"] = "x" * 131_073
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/context/lifecycle/projections",
                    json=payload,
                    headers={
                        "x-cgg-caller-id": "operator-orchestration-service",
                        "x-cgg-caller-secret": CALLER_SECRET,
                    },
                )

            self.assertEqual(response.status_code, 413, response.text)
            self.assertEqual(
                response.json()["detail"]["code"], "context_projection_oversized"
            )
            self.assertNotIn("x" * 100, response.text)


if __name__ == "__main__":
    unittest.main()
