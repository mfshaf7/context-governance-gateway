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
    def test_related_drafts_planning_and_choices_are_bound_redacted_and_closed(self) -> None:
        assist = _assist_request()
        node = assist["target"]["selected_node_ids"][0]
        assist["related_drafts"] = [{"node_id": node, "field_key": "target-pi", "value": "API_TOKEN=secret-draft"}]
        work = {key: assist[key] for key in ("package_ref", "source_ref", "source_revision")}
        work.update(source_work_design_receipt_id=assist["packet"]["source_work_design_receipt_id"], coverage="Canonical facts; drafts remain unaccepted",
            nodes=[{"id": key, "kind": "Feature", "title": "Selected outcome", "description": "Local project", "planning": {"status": "new", "target_pi": "", "iteration": "", "owner_repo": "repo-a"}} for key in assist["target"]["selected_node_ids"]],
            metadata=[{"node_id": node, "field_key": "target-pi", "backend_field": "target_pi", "field_kind": "select", "required": False, "status": "complete", "source_value": "", "draft_value": "API_TOKEN=secret-draft", "allowed_values": ["PI-test"], "validation_hint": "Catalog choices"}],
            planning_rules={"workflow_id": "planning", "backlog_iteration_label": "Backlog", "iteration_prefix_templates": ["<target_pi> / "], "target_pi_required_types": ["Task"], "iteration_required_types": ["Feature"]})
        request = _request(assist_request=assist, work_context=work)
        request.validate_shape()
        _validate_schema("refinement-context-projection-request.schema.json", {"schema_version": 1, "idempotency_key": request.idempotency_key, "workflow_session_id": request.workflow_session_id, "execution_id": request.execution_id, "requested_at": request.requested_at, "assist_request": assist, "assist_request_digest": request.assist_request_digest, "work_context": work, "budget_tokens": request.budget_tokens})
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(RuntimeSettings(root=Path(tmp), runtime_profile_state="active", refinement_caller_shared_secret=CALLER_SECRET))
            result = service.refinement_projector.project(request, caller_id="operator-orchestration-service", caller_secret=CALLER_SECRET, now=NOW)
            self.assertNotIn("secret-draft", result["content"])
            self.assertIn("PI-test", result["content"])
            self.assertEqual(result["binding"]["context_digest"], _digest(request.context))
        for change in [lambda w: w["metadata"][0].update(node_id="foreign"), lambda w: w["metadata"].append(w["metadata"][0].copy()), lambda w: w["metadata"][0].update(draft_value="changed"), lambda w: w["nodes"][0]["planning"].update(execute="denied")]:
            altered = json.loads(json.dumps(work)); change(altered)
            with self.assertRaises(RefinementProjectionError):
                _request(assist_request=assist, work_context=altered).validate_shape()
        with self.assertRaises(RefinementProjectionError):
            _request(assist_request=assist).validate_shape()

    def test_numeric_constraints_are_retained_in_admitted_context(self) -> None:
        assist = _assist_request()
        node = assist["target"]["selected_node_ids"][0]
        work = {key: assist[key] for key in ("package_ref", "source_ref", "source_revision")}
        work.update(source_work_design_receipt_id=assist["packet"]["source_work_design_receipt_id"], coverage="Selected items only",
            nodes=[{"id": key, "kind": "Feature", "title": "Selected outcome", "description": ""} for key in assist["target"]["selected_node_ids"]],
            metadata=[{"node_id": node, "field_key": "business-value", "backend_field": "planned_business_value", "field_kind": "number", "numeric_type": "integer", "required": False, "status": "complete", "source_value": "8", "allowed_values": [], "validation_hint": "Whole number"}])
        request = _request(assist_request=assist, work_context=work)
        request.validate_shape()
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(RuntimeSettings(root=Path(tmp), runtime_profile_state="active", refinement_caller_shared_secret=CALLER_SECRET))
            result = service.refinement_projector.project(request, caller_id="operator-orchestration-service", caller_secret=CALLER_SECRET, now=NOW)
            self.assertEqual(json.loads(result["content"])["work_context"]["metadata"][0]["numeric_type"], "integer")
        for invalid in ["unknown", 1]:
            changed = json.loads(json.dumps(work)); changed["metadata"][0]["numeric_type"] = invalid
            with self.assertRaises(RefinementProjectionError):
                _request(assist_request=assist, work_context=changed).validate_shape()

    def test_owner_work_context_is_redacted_bound_and_replay_sensitive(self) -> None:
        assist = _assist_request()
        work = {key: assist[key] for key in ("package_ref", "source_ref", "source_revision")}
        work.update(source_work_design_receipt_id=assist["packet"]["source_work_design_receipt_id"],
                    coverage="Current canonical selected nodes and ancestors; no separate diagram contents.",
                    nodes=[{"id": key, "kind": "Feature", "title": "Accepted outcome", "description": "Architectural rule: local data. API_TOKEN=secret-value"}
                           for key in assist["target"]["selected_node_ids"]])
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(RuntimeSettings(root=Path(tmp), runtime_profile_state="active",
                refinement_caller_shared_secret=CALLER_SECRET))
            request = _request(work_context=work)
            result = service.refinement_projector.project(request,
                caller_id="operator-orchestration-service", caller_secret=CALLER_SECRET, now=NOW)
            _validate_schema("refinement-context-projection-result.schema.json", result)
            self.assertIn("Architectural rule: local data", result["content"])
            self.assertNotIn("secret-value", result["content"])
            self.assertEqual(result["binding"]["context_digest"], _digest(request.context))
            self.assertNotEqual(result["binding"]["context_digest"], request.assist_request_digest)
            changed = json.loads(json.dumps(work))
            changed["nodes"][0]["description"] = "Different accepted constraint"
            with self.assertRaises(RefinementProjectionError) as caught:
                service.refinement_projector.project(replace(request, work_context=changed),
                    caller_id="operator-orchestration-service", caller_secret=CALLER_SECRET, now=NOW)
            self.assertEqual(caught.exception.code, "context_projection_replay_conflict")
        for changed in [{**work, "source_ref": "another-project"}, {**work, "nodes": work["nodes"] * 2},
                        {**work, "nodes": []}, {**work, "execute": "forbidden"}]:
            with self.assertRaises(RefinementProjectionError):
                _request(work_context=changed).validate_shape()

    def test_budget_trimmed_selected_field_does_not_become_ready_advice_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(RuntimeSettings(root=Path(tmp), runtime_profile_state="active",
                refinement_caller_shared_secret=CALLER_SECRET))
            with self.assertRaises(RefinementProjectionError) as caught:
                service.refinement_projector.project(_request(budget_tokens=10),
                    caller_id="operator-orchestration-service", caller_secret=CALLER_SECRET, now=NOW)
            self.assertEqual(caught.exception.code, "context_projection_oversized")
            complete = service.refinement_projector.project(_request(idempotency_key="complete-field"),
                caller_id="operator-orchestration-service", caller_secret=CALLER_SECRET, now=NOW)
            self.assertEqual(complete["status"], "ready")
            self.assertIn("Describe verifiable entry conditions", complete["content"])

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
