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


CALLER_SECRET = "test-agent-console-secret"
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "contracts" / "schemas"


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _payload() -> dict[str, object]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    content = "selected page API_TOKEN=secret-value"
    return {
        "schema_version": 1,
        "request_id": "request-console-api",
        "correlation_id": "correlation-console-api",
        "idempotency_key": "agent-console-api",
        "session_id": "session-console-api",
        "invocation_id": "invocation-console-api",
        "operator_id": "agent:gary",
        "interaction_mode": "focused",
        "requested_at": now,
        "candidate": {
            "candidate_id": "page-42-rev-7",
            "scope": "page",
            "source_authority": "governance-operations-console",
            "source_mode": "live",
            "source_ref": "console://pages/42",
            "source_revision": "rev-7",
            "captured_at": now,
            "content": content,
            "content_digest": _digest(content),
        },
        "budget_tokens": 4_000,
    }


class AgentConsoleApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_projects_replays_and_reads_agent_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = _payload()
            request_schema = json.loads(
                (SCHEMA_ROOT / "agent-console-context-projection-request.schema.json").read_text(
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
                    agent_console_caller_shared_secret=CALLER_SECRET,
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
                    "/v1/context/agent-console/projections", json=payload, headers=headers
                )
                replay = await client.post(
                    "/v1/context/agent-console/projections", json=payload, headers=headers
                )
                readback = await client.get(
                    "/v1/context/agent-console/projections/agent-console-api",
                    headers=headers,
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
                    agent_console_caller_shared_secret=CALLER_SECRET,
                )
            )
            payload = _payload()
            payload["unexpected"] = "API_TOKEN=must-not-echo"
            valid_payload = _payload()
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                invalid = await client.post(
                    "/v1/context/agent-console/projections",
                    json=payload,
                    headers={
                        "x-cgg-caller-id": "operator-orchestration-service",
                        "x-cgg-caller-secret": CALLER_SECRET,
                    },
                )
                created = await client.post(
                    "/v1/context/agent-console/projections",
                    json=valid_payload,
                    headers={
                        "x-cgg-caller-id": "operator-orchestration-service",
                        "x-cgg-caller-secret": CALLER_SECRET,
                    },
                )
                unauthorized = await client.get(
                    "/v1/context/agent-console/projections/agent-console-api",
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

    async def test_api_reports_oversized_candidate_as_bounded_contract_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    agent_console_caller_shared_secret=CALLER_SECRET,
                )
            )
            payload = _payload()
            payload["candidate"]["content"] = "x" * 131_073
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/context/agent-console/projections",
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
