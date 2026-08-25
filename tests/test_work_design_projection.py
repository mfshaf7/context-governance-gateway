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
    ContextGatewayService,
    RuntimeGateError,
    RuntimeSettings,
    WorkDesignProjectionError,
    WorkDesignProjectionRequest,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
CALLER_SECRET = "test-shared-secret"
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "contracts" / "schemas"


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _validate_schema(name: str, value: dict[str, object]) -> None:
    schema = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(value)


def _request(**overrides: object) -> WorkDesignProjectionRequest:
    context = str(overrides.pop("context", '{"package":"example","API_TOKEN":"secret-value"}'))
    values: dict[str, object] = {
        "request_id": "request-991-1",
        "correlation_id": "correlation-991-1",
        "idempotency_key": "work-design-991-1",
        "workflow_session_id": "session-991-1",
        "execution_id": "execution-991-1",
        "delivery_id": "delivery-884",
        "package_ref": "openproject://work_packages/991",
        "source_ref": "git://context-governance-gateway/example",
        "source_revision": "c06452ddcf2dedd71299db623c39578142deb89c",
        "operator_id": "operator:workspace-owner",
        "task_kind": "context_advice",
        "task_contract_ref": "oos.delivery-work-design.v1",
        "task_version": "1.0",
        "output_schema_ref": "contract://oos/work-design/assist-result.v1",
        "model_profile_id": "delivery-work-design-advisor-v1",
        "requested_at": NOW.isoformat().replace("+00:00", "Z"),
        "context": context,
        "context_digest": _digest(context),
        "budget_tokens": 4_000,
    }
    values.update(overrides)
    return WorkDesignProjectionRequest(**values)  # type: ignore[arg-type]


class WorkDesignProjectionTests(unittest.TestCase):
    def test_projects_receipt_bound_model_safe_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
                )
            )
            self.assertTrue(
                service.readiness()["capabilities"]["work_design_projection"]["ready"]
            )

            result = service.work_design_projector.project(
                _request(),
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
                now=NOW,
            )

            self.assertEqual(result["status"], "ready")
            self.assertFalse(result["replayed"])
            self.assertEqual(result["binding"]["caller_id"], "operator-orchestration-service")
            self.assertEqual(result["binding"]["task"]["contract_ref"], "oos.delivery-work-design.v1")
            self.assertEqual(result["admission_decision"]["raw_projection"], "denied")
            self.assertTrue(result["admission_decision"]["redaction_safe"])
            self.assertIn("<redacted:secret-field>", result["content"])
            self.assertNotIn("secret-value", json.dumps(result))
            self.assertIn('"budget_tokens":4000', str(result["content"]))
            self.assertTrue(result["packet_ref"].startswith("/v1/context/packets/"))
            self.assertTrue(
                result["redaction_receipt_ref"].startswith("/v1/context/receipts/")
            )
            self.assertEqual(
                result["projection_receipt_ref"],
                "/v1/context/work-design/projections/work-design-991-1",
            )
            record = service.work_design_projection(
                "work-design-991-1",
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
            )
            self.assertEqual(record["status"], "ready")
            self.assertEqual(record["response"]["artifact_id"], result["artifact_id"])
            _validate_schema("work-design-context-projection-result.schema.json", result)

    def test_identical_replay_returns_the_original_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
                )
            )
            request = _request()

            first = service.work_design_projector.project(
                request,
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
                now=NOW,
            )
            replay = service.work_design_projector.project(
                request,
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
                now=NOW + timedelta(seconds=1),
            )

            self.assertFalse(first["replayed"])
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["artifact_id"], first["artifact_id"])
            self.assertEqual(len(service.metadata_store.list_artifact_ids()), 1)

    def test_replay_conflict_is_denied_without_replacing_the_original(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
                )
            )
            original = _request()
            service.work_design_projector.project(
                original,
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
                now=NOW,
            )
            changed_context = '{"package":"different"}'
            conflict = replace(
                original,
                context=changed_context,
                context_digest=_digest(changed_context),
            )

            with self.assertRaisesRegex(WorkDesignProjectionError, "different Work Design context") as caught:
                service.work_design_projector.project(
                    conflict,
                    caller_id="operator-orchestration-service",
                    caller_secret=CALLER_SECRET,
                    now=NOW + timedelta(seconds=1),
                )

            self.assertEqual(caught.exception.code, "context_projection_replay_conflict")
            record = service.work_design_projection(
                original.idempotency_key,
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
            )
            self.assertEqual(record["status"], "ready")

    def test_current_pending_request_blocks_and_stale_pending_request_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
                    work_design_pending_timeout_seconds=10,
                )
            )
            request = _request()
            pending = {
                "schema_version": 1,
                "status": "pending",
                "idempotency_key": request.idempotency_key,
                "request_digest": request.request_digest("operator-orchestration-service"),
                "binding": request.binding("operator-orchestration-service"),
                "started_at": NOW.isoformat().replace("+00:00", "Z"),
                "attempt": 1,
            }
            service.work_design_projector.store.create(request.idempotency_key, pending)

            with self.assertRaises(WorkDesignProjectionError) as caught:
                service.work_design_projector.project(
                    request,
                    caller_id="operator-orchestration-service",
                    caller_secret=CALLER_SECRET,
                    now=NOW + timedelta(seconds=5),
                )
            self.assertEqual(caught.exception.code, "context_projection_in_progress")
            self.assertTrue(caught.exception.retryable)

            service.work_design_projector.store.replace(
                request.idempotency_key,
                {
                    **pending,
                    "started_at": (NOW - timedelta(seconds=20)).isoformat().replace(
                        "+00:00", "Z"
                    ),
                },
            )
            recovered = service.work_design_projector.project(
                request,
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
                now=NOW,
            )

            self.assertEqual(recovered["status"], "ready")
            record = service.work_design_projector.store.read(request.idempotency_key)
            self.assertEqual(record["attempt"], 2)

    def test_unauthorized_stale_oversized_and_malformed_requests_are_bounded(self) -> None:
        cases = [
            (
                _request(),
                "untrusted-caller",
                RuntimeSettings(
                    root=Path("."),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
                ),
                "context_projection_unauthorized",
            ),
            (
                _request(requested_at=(NOW - timedelta(minutes=10)).isoformat()),
                "operator-orchestration-service",
                RuntimeSettings(
                    root=Path("."),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
                ),
                "context_projection_stale",
            ),
            (
                _request(context="context that exceeds the test boundary"),
                "operator-orchestration-service",
                RuntimeSettings(
                    root=Path("."),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
                    work_design_max_context_bytes=12,
                ),
                "context_projection_oversized",
            ),
            (
                _request(context_digest=f"sha256:{'0' * 64}"),
                "operator-orchestration-service",
                RuntimeSettings(
                    root=Path("."),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
                ),
                "context_projection_invalid",
            ),
        ]
        for request, caller_id, settings, expected_code in cases:
            with self.subTest(expected_code=expected_code), tempfile.TemporaryDirectory() as tmp:
                service = ContextGatewayService(replace(settings, root=Path(tmp)))
                with self.assertRaises(WorkDesignProjectionError) as caught:
                    service.work_design_projector.project(
                        request,
                        caller_id=caller_id,
                        caller_secret=CALLER_SECRET,
                        now=NOW,
                    )
                self.assertEqual(caught.exception.code, expected_code)
                _validate_schema(
                    "work-design-context-projection-error.schema.json",
                    caught.exception.to_dict(),
                )
                denial_files = list((Path(tmp) / ".cgg" / "work-design-denials").glob("*.json"))
                self.assertEqual(len(denial_files), 1)
                denial = json.loads(denial_files[0].read_text(encoding="utf-8"))
                self.assertEqual(denial["error"]["code"], expected_code)
                self.assertNotIn(request.context, json.dumps(denial))

    def test_inactive_runtime_denies_projection_before_custody_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(
                RuntimeSettings(root=Path(tmp), runtime_profile_state="build-admitted")
            )

            with self.assertRaises(RuntimeGateError):
                service.project_work_design(
                    _request(),
                    caller_id="operator-orchestration-service",
                    caller_secret=CALLER_SECRET,
                )

            self.assertEqual(service.metadata_store.list_artifact_ids(), [])

    def test_missing_caller_secret_keeps_work_design_capability_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(
                RuntimeSettings(root=Path(tmp), runtime_profile_state="active")
            )

            self.assertFalse(
                service.readiness()["capabilities"]["work_design_projection"]["ready"]
            )
            with self.assertRaises(WorkDesignProjectionError) as caught:
                service.work_design_projector.project(
                    _request(),
                    caller_id="operator-orchestration-service",
                    caller_secret=CALLER_SECRET,
                    now=NOW,
                )

            self.assertEqual(caught.exception.code, "context_projection_unauthorized")

    def test_incorrect_caller_secret_is_denied_without_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            submitted_secret = "incorrect-composition-binding"
            service = ContextGatewayService(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
                )
            )

            with self.assertRaises(WorkDesignProjectionError) as caught:
                service.work_design_projector.project(
                    _request(),
                    caller_id="operator-orchestration-service",
                    caller_secret=submitted_secret,
                    now=NOW,
                )

            self.assertEqual(caught.exception.code, "context_projection_unauthorized")
            denials = list((Path(tmp) / ".cgg" / "work-design-denials").glob("*.json"))
            self.assertEqual(len(denials), 1)
            self.assertNotIn(
                submitted_secret,
                denials[0].read_text(encoding="utf-8"),
            )

    def test_projection_read_requires_the_bound_caller(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    work_design_caller_shared_secret=CALLER_SECRET,
                )
            )
            service.work_design_projector.project(
                _request(),
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
                now=NOW,
            )

            with self.assertRaises(WorkDesignProjectionError) as caught:
                service.work_design_projection(
                    "work-design-991-1",
                    caller_id="another-caller",
                    caller_secret=CALLER_SECRET,
                )

            self.assertEqual(caught.exception.code, "context_projection_unauthorized")


if __name__ == "__main__":
    unittest.main()
