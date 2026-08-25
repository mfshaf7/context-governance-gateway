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
    RefinementProjectionError,
    RefinementProjectionRequest,
    RuntimeGateError,
    RuntimeSettings,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
CALLER_SECRET = "test-refinement-shared-secret"
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "contracts" / "schemas"


def _canonical(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _digest(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _validate_schema(name: str, value: dict[str, object]) -> None:
    schema = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(value)


def _assist_request(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "request_id": "request-1006-1",
        "correlation_id": "correlation-1006-1",
        "delivery_id": "delivery-884",
        "package_ref": "openproject://work_packages/756",
        "source_ref": "git://workspace-delivery-art/refinement/756",
        "source_revision": "8db557156a85ddc8ed7ac177d5930242970efb2d",
        "operator": {"id": "operator:workspace-owner", "handle": "mfshaf7"},
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
            "selected_node_ids": ["feature-756", "story-789"],
            "allowed_values": [],
        },
        "operator_prompt": "Suggest a concise, testable value without applying it.",
    }
    value.update(overrides)
    return value


def _request(**overrides: object) -> RefinementProjectionRequest:
    assist = dict(overrides.pop("assist_request", _assist_request()))
    values: dict[str, object] = {
        "idempotency_key": "refinement-756-1",
        "workflow_session_id": "session-756-1",
        "execution_id": "execution-756-1",
        "requested_at": NOW.isoformat().replace("+00:00", "Z"),
        "assist_request": assist,
        "assist_request_digest": _digest(_canonical(assist)),
        "budget_tokens": 4_000,
    }
    values.update(overrides)
    return RefinementProjectionRequest(**values)  # type: ignore[arg-type]


class RefinementProjectionTests(unittest.TestCase):
    def test_projects_receipt_bound_model_safe_refinement_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    refinement_caller_shared_secret=CALLER_SECRET,
                )
            )

            result = service.refinement_projector.project(
                _request(),
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
                now=NOW,
            )

            self.assertTrue(
                service.readiness()["capabilities"]["refinement_projection"]["ready"]
            )
            self.assertEqual(result["status"], "ready")
            self.assertEqual(
                result["binding"]["task"]["contract_ref"],
                "oos.delivery-refinement.v1",
            )
            self.assertEqual(
                result["binding"]["packet"]["source_work_design_receipt_id"],
                "work-design-receipt-756",
            )
            self.assertEqual(result["admission_decision"]["raw_projection"], "denied")
            self.assertIn("<redacted:secret-env-var>", result["content"])
            self.assertNotIn("secret-value", json.dumps(result))
            self.assertEqual(
                result["projection_receipt_ref"],
                "/v1/context/refinement/projections/refinement-756-1",
            )
            self.assertEqual(
                result["authority"],
                {
                    "may_select_or_invoke_model": False,
                    "may_approve_suggestion": False,
                    "may_mutate_delivery": False,
                },
            )
            _validate_schema("refinement-context-projection-result.schema.json", result)

    def test_identical_replay_returns_original_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    refinement_caller_shared_secret=CALLER_SECRET,
                )
            )
            request = _request()
            first = service.refinement_projector.project(
                request,
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
                now=NOW,
            )
            replay = service.refinement_projector.project(
                request,
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
                now=NOW + timedelta(seconds=1),
            )

            self.assertFalse(first["replayed"])
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["artifact_id"], first["artifact_id"])
            self.assertEqual(len(service.metadata_store.list_artifact_ids()), 1)

    def test_conflicting_replay_is_denied_without_replacing_original(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    refinement_caller_shared_secret=CALLER_SECRET,
                )
            )
            original = _request()
            service.refinement_projector.project(
                original,
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
                now=NOW,
            )
            changed_assist = _assist_request(operator_prompt="Suggest another value.")
            conflict = replace(
                original,
                assist_request=changed_assist,
                assist_request_digest=_digest(_canonical(changed_assist)),
            )

            with self.assertRaisesRegex(
                RefinementProjectionError, "different Refinement context"
            ) as caught:
                service.refinement_projector.project(
                    conflict,
                    caller_id="operator-orchestration-service",
                    caller_secret=CALLER_SECRET,
                    now=NOW + timedelta(seconds=1),
                )

            self.assertEqual(caught.exception.code, "context_projection_replay_conflict")
            stored = service.refinement_projection(
                original.idempotency_key,
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
            )
            self.assertEqual(stored["status"], "ready")

    def test_denies_untrusted_stale_oversized_and_mismatched_requests(self) -> None:
        cases = [
            (
                _request(),
                "untrusted-caller",
                RuntimeSettings(
                    root=Path("."),
                    runtime_profile_state="active",
                    refinement_caller_shared_secret=CALLER_SECRET,
                ),
                "context_projection_unauthorized",
            ),
            (
                _request(requested_at=(NOW - timedelta(minutes=10)).isoformat()),
                "operator-orchestration-service",
                RuntimeSettings(
                    root=Path("."),
                    runtime_profile_state="active",
                    refinement_caller_shared_secret=CALLER_SECRET,
                ),
                "context_projection_stale",
            ),
            (
                _request(),
                "operator-orchestration-service",
                RuntimeSettings(
                    root=Path("."),
                    runtime_profile_state="active",
                    refinement_caller_shared_secret=CALLER_SECRET,
                    refinement_max_context_bytes=12,
                ),
                "context_projection_oversized",
            ),
            (
                _request(assist_request_digest=f"sha256:{'0' * 64}"),
                "operator-orchestration-service",
                RuntimeSettings(
                    root=Path("."),
                    runtime_profile_state="active",
                    refinement_caller_shared_secret=CALLER_SECRET,
                ),
                "context_projection_invalid",
            ),
        ]
        for request, caller_id, settings, expected_code in cases:
            with self.subTest(expected_code=expected_code), tempfile.TemporaryDirectory() as tmp:
                service = ContextGatewayService(replace(settings, root=Path(tmp)))
                with self.assertRaises(RefinementProjectionError) as caught:
                    service.refinement_projector.project(
                        request,
                        caller_id=caller_id,
                        caller_secret=CALLER_SECRET,
                        now=NOW,
                    )
                self.assertEqual(caught.exception.code, expected_code)
                _validate_schema(
                    "refinement-context-projection-error.schema.json",
                    caught.exception.to_dict(),
                )
                denials = list((Path(tmp) / ".cgg" / "refinement-denials").glob("*.json"))
                self.assertEqual(len(denials), 1)
                self.assertNotIn("secret-value", denials[0].read_text(encoding="utf-8"))

    def test_inactive_or_unconfigured_runtime_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inactive = ContextGatewayService(
                RuntimeSettings(root=Path(tmp), runtime_profile_state="build-admitted")
            )
            with self.assertRaises(RuntimeGateError):
                inactive.project_refinement(
                    _request(),
                    caller_id="operator-orchestration-service",
                    caller_secret=CALLER_SECRET,
                )

        with tempfile.TemporaryDirectory() as tmp:
            unconfigured = ContextGatewayService(
                RuntimeSettings(root=Path(tmp), runtime_profile_state="active")
            )
            self.assertFalse(
                unconfigured.readiness()["capabilities"]["refinement_projection"]["ready"]
            )
            with self.assertRaises(RefinementProjectionError) as caught:
                unconfigured.refinement_projector.project(
                    _request(),
                    caller_id="operator-orchestration-service",
                    caller_secret=CALLER_SECRET,
                    now=NOW,
                )
            self.assertEqual(caught.exception.code, "context_projection_unauthorized")

    def test_refinement_and_work_design_replay_namespaces_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    refinement_caller_shared_secret=CALLER_SECRET,
                )
            )
            service.refinement_projector.project(
                _request(idempotency_key="shared-key"),
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
                now=NOW,
            )

            self.assertIsNotNone(service.refinement_projector.store.read("shared-key"))
            self.assertIsNone(service.work_design_projector.store.read("shared-key"))

    def test_projection_read_requires_bound_caller(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(
                RuntimeSettings(
                    root=Path(tmp),
                    runtime_profile_state="active",
                    refinement_caller_shared_secret=CALLER_SECRET,
                )
            )
            service.refinement_projector.project(
                _request(),
                caller_id="operator-orchestration-service",
                caller_secret=CALLER_SECRET,
                now=NOW,
            )

            with self.assertRaises(RefinementProjectionError) as caught:
                service.refinement_projection(
                    "refinement-756-1",
                    caller_id="another-caller",
                    caller_secret=CALLER_SECRET,
                )
            self.assertEqual(caught.exception.code, "context_projection_unauthorized")


if __name__ == "__main__":
    unittest.main()
