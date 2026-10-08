from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from cgg_api import (
    AgentConsoleContextCandidate,
    AgentConsoleContextProjectionRequest,
    AgentConsoleProjectionError,
    ContextGatewayService,
    RuntimeGateError,
    RuntimeSettings,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
CALLER_ID = "operator-orchestration-service"
CALLER_SECRET = "test-agent-console-secret"
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "contracts" / "schemas"


def _timestamp(value: datetime = NOW) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _candidate(content: str = "page status API_TOKEN=secret-value") -> AgentConsoleContextCandidate:
    return AgentConsoleContextCandidate(
        candidate_id="page-42-rev-7",
        scope="page",
        source_authority="governance-operations-console",
        source_mode="live",
        source_ref="console://pages/42",
        source_revision="rev-7",
        captured_at=_timestamp(),
        content=content,
        content_digest=_digest(content),
    )


def _request(**overrides: object) -> AgentConsoleContextProjectionRequest:
    values: dict[str, object] = {
        "request_id": "request-console-1",
        "correlation_id": "correlation-console-1",
        "idempotency_key": "agent-console-1",
        "session_id": "session-console-1",
        "invocation_id": "invocation-console-1",
        "operator_id": "agent:gary",
        "interaction_mode": "focused",
        "requested_at": _timestamp(),
        "candidate": _candidate(),
        "budget_tokens": 4_000,
    }
    values.update(overrides)
    return AgentConsoleContextProjectionRequest(**values)  # type: ignore[arg-type]


def _settings(root: Path, **overrides: object) -> RuntimeSettings:
    values: dict[str, object] = {
        "root": root,
        "runtime_profile_state": "active",
        "agent_console_caller_shared_secret": CALLER_SECRET,
    }
    values.update(overrides)
    return RuntimeSettings(**values)  # type: ignore[arg-type]


def _validate_schema(name: str, value: dict[str, object]) -> None:
    schema = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(value)


class AgentConsoleProjectionTests(unittest.TestCase):
    def test_projects_redacted_receipt_bound_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(_settings(Path(tmp)))

            result = service.agent_console_projector.project(
                _request(), caller_id=CALLER_ID, caller_secret=CALLER_SECRET, now=NOW
            )

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["agent_context"]["interaction_mode"], "focused")
            self.assertEqual(result["classification"]["scope"], "page")
            self.assertIn("<redacted:secret-env-var>", result["content"])
            self.assertNotIn("secret-value", json.dumps(result))
            self.assertNotIn("content", result["agent_context"]["candidate"])
            self.assertFalse(result["projection_safety"]["raw_context_exposed"])
            self.assertFalse(result["agent_context_authority"]["may_select_or_invoke_model"])
            self.assertEqual(
                result["projection_receipt_ref"],
                "/v1/context/agent-console/projections/agent-console-1",
            )
            _validate_schema("agent-console-context-projection-result.schema.json", result)

    def test_replay_survives_restart_and_conflict_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = _request()
            first_service = ContextGatewayService(_settings(root))
            first = first_service.agent_console_projector.project(
                request, caller_id=CALLER_ID, caller_secret=CALLER_SECRET, now=NOW
            )

            restarted = ContextGatewayService(_settings(root))
            replay = restarted.agent_console_projector.project(
                request,
                caller_id=CALLER_ID,
                caller_secret=CALLER_SECRET,
                now=NOW + timedelta(seconds=1),
            )
            changed_content = "different page truth"
            conflict = replace(
                request,
                candidate=replace(
                    request.candidate,
                    content=changed_content,
                    content_digest=_digest(changed_content),
                ),
            )
            with self.assertRaises(AgentConsoleProjectionError) as caught:
                restarted.agent_console_projector.project(
                    conflict,
                    caller_id=CALLER_ID,
                    caller_secret=CALLER_SECRET,
                    now=NOW + timedelta(seconds=2),
                )

            self.assertFalse(first["replayed"])
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["artifact_id"], first["artifact_id"])
            self.assertEqual(caught.exception.code, "context_projection_replay_conflict")
            record = restarted.agent_console_projection(
                request.idempotency_key,
                caller_id=CALLER_ID,
                caller_secret=CALLER_SECRET,
            )
            self.assertEqual(record["response"]["artifact_id"], first["artifact_id"])

    def test_auth_age_size_digest_scope_and_timeline_fail_closed(self) -> None:
        workspace_candidate = replace(_candidate(), scope="workspace")
        cases = (
            ("untrusted", _request(), {}, "context_projection_unauthorized"),
            (
                CALLER_ID,
                _request(
                    requested_at=_timestamp(NOW - timedelta(minutes=10)),
                    candidate=replace(
                        _candidate(), captured_at=_timestamp(NOW - timedelta(minutes=11))
                    ),
                ),
                {},
                "context_projection_stale",
            ),
            (
                CALLER_ID,
                _request(),
                {"agent_console_max_context_bytes": 32},
                "context_projection_oversized",
            ),
            (
                CALLER_ID,
                _request(candidate=replace(_candidate(), content_digest=f"sha256:{'0' * 64}")),
                {},
                "context_projection_invalid",
            ),
            (
                CALLER_ID,
                _request(
                    candidate=replace(
                        _candidate(), captured_at=_timestamp(NOW + timedelta(seconds=1))
                    )
                ),
                {},
                "context_projection_invalid",
            ),
            (
                CALLER_ID,
                _request(interaction_mode="workspace"),
                {},
                "context_projection_invalid",
            ),
        )
        self.assertEqual(workspace_candidate.scope, "workspace")
        for caller_id, request, setting_overrides, expected_code in cases:
            with self.subTest(expected_code=expected_code), tempfile.TemporaryDirectory() as tmp:
                service = ContextGatewayService(_settings(Path(tmp), **setting_overrides))
                with self.assertRaises(AgentConsoleProjectionError) as caught:
                    service.agent_console_projector.project(
                        request,
                        caller_id=caller_id,
                        caller_secret=CALLER_SECRET,
                        now=NOW,
                    )
                self.assertEqual(caught.exception.code, expected_code)
                _validate_schema(
                    "agent-console-context-projection-error.schema.json",
                    caught.exception.to_dict(),
                )
                denial = next((Path(tmp) / ".cgg" / "agent-console-denials").glob("*.json"))
                self.assertNotIn("secret-value", denial.read_text(encoding="utf-8"))

    def test_workspace_mode_accepts_workspace_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(_settings(Path(tmp)))
            result = service.agent_console_projector.project(
                _request(
                    interaction_mode="workspace",
                    candidate=replace(_candidate(), scope="workspace"),
                ),
                caller_id=CALLER_ID,
                caller_secret=CALLER_SECRET,
                now=NOW,
            )
            self.assertEqual(result["classification"]["scope"], "workspace")

    def test_inactive_unconfigured_and_namespace_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inactive = ContextGatewayService(RuntimeSettings(root=Path(tmp)))
            with self.assertRaises(RuntimeGateError):
                inactive.project_agent_console(
                    _request(), caller_id=CALLER_ID, caller_secret=CALLER_SECRET
                )

        with tempfile.TemporaryDirectory() as tmp:
            unconfigured = ContextGatewayService(
                RuntimeSettings(root=Path(tmp), runtime_profile_state="active")
            )
            self.assertFalse(
                unconfigured.readiness()["capabilities"]["agent_console_projection"]["ready"]
            )
            with self.assertRaises(AgentConsoleProjectionError) as caught:
                unconfigured.project_agent_console(
                    _request(), caller_id=CALLER_ID, caller_secret=CALLER_SECRET
                )
            self.assertEqual(caught.exception.code, "context_projection_unauthorized")

        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(_settings(Path(tmp)))
            request = _request(idempotency_key="shared-key")
            service.agent_console_projector.project(
                request, caller_id=CALLER_ID, caller_secret=CALLER_SECRET, now=NOW
            )
            self.assertIsNotNone(service.agent_console_projector.store.read("shared-key"))
            self.assertIsNone(service.lifecycle_projector.store.read("shared-key"))
            self.assertIsNone(service.refinement_projector.store.read("shared-key"))
            self.assertIsNone(service.work_design_projector.store.read("shared-key"))


if __name__ == "__main__":
    unittest.main()
