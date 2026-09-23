from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from cgg_api import (
    ContextGatewayService,
    LifecycleContextProjectionRequest,
    LifecycleContextSource,
    LifecycleProjectionError,
    RuntimeGateError,
    RuntimeSettings,
    canonical_sources_digest,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
CALLER_ID = "operator-orchestration-service"
CALLER_SECRET = "test-lifecycle-secret"
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "contracts" / "schemas"


def _timestamp(value: datetime = NOW) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _digest(value: str) -> str:
    import hashlib

    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _source(
    source_id: str = "art-1164",
    source_class: str = "art",
    content: str = "ART status active API_TOKEN=secret-value",
) -> LifecycleContextSource:
    return LifecycleContextSource(
        source_id=source_id,
        source_class=source_class,
        source_ref="openproject://work_packages/1164",
        source_revision="rev-19",
        captured_at=_timestamp(),
        availability="available",
        content=content,
        content_digest=_digest(content),
        unavailable_reason=None,
    )


def _unavailable_source() -> LifecycleContextSource:
    return LifecycleContextSource(
        source_id="runtime-status",
        source_class="runtime",
        source_ref="devint://context-governance-gateway/status",
        source_revision=None,
        captured_at=_timestamp(),
        availability="unavailable",
        content=None,
        content_digest=None,
        unavailable_reason="not_configured",
    )


def _request(**overrides: object) -> LifecycleContextProjectionRequest:
    sources = tuple(overrides.pop("sources", (_source(), _unavailable_source())))
    values: dict[str, object] = {
        "request_id": "request-1164-1",
        "correlation_id": "correlation-1164-1",
        "idempotency_key": "lifecycle-1164-1",
        "workflow_session_id": "session-1164-1",
        "execution_id": "execution-1164-1",
        "delivery_id": "delivery-1164",
        "work_item_ref": "openproject://work_packages/1164",
        "landing_unit_id": "delivery-1154-cgg-lifecycle-projection",
        "operator_id": "agent:gary",
        "operation": "continue",
        "lifecycle_state": "source-work",
        "next_action": "source-evidence",
        "requested_at": _timestamp(),
        "sources": sources,
        "sources_digest": canonical_sources_digest(sources),
        "budget_tokens": 4_000,
    }
    values.update(overrides)
    return LifecycleContextProjectionRequest(**values)  # type: ignore[arg-type]


def _settings(root: Path, **overrides: object) -> RuntimeSettings:
    values: dict[str, object] = {
        "root": root,
        "runtime_profile_state": "active",
        "lifecycle_caller_shared_secret": CALLER_SECRET,
    }
    values.update(overrides)
    return RuntimeSettings(**values)  # type: ignore[arg-type]


def _validate_schema(name: str, value: dict[str, object]) -> None:
    schema = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(
        schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    ).validate(value)


class LifecycleProjectionTests(unittest.TestCase):
    def test_projects_typed_redacted_receipt_bound_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(_settings(Path(tmp)))

            result = service.lifecycle_projector.project(
                _request(), caller_id=CALLER_ID, caller_secret=CALLER_SECRET, now=NOW
            )

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["lifecycle_context"]["operation"], "continue")
            self.assertEqual(result["source_summary"], {
                "total": 2,
                "available": 1,
                "unavailable": 1,
                "classes": ["art", "runtime"],
            })
            self.assertEqual(
                result["source_bindings"][1]["unavailable_reason"], "not_configured"
            )
            self.assertIn("<redacted:secret-env-var>", result["content"])
            self.assertNotIn("secret-value", json.dumps(result))
            self.assertFalse(result["projection_safety"]["raw_context_exposed"])
            self.assertTrue(result["projection_safety"]["custody_bound"])
            self.assertFalse(result["lifecycle_authority"]["may_choose_action"])
            self.assertEqual(
                result["projection_receipt_ref"],
                "/v1/context/lifecycle/projections/lifecycle-1164-1",
            )
            _validate_schema("lifecycle-context-projection-result.schema.json", result)

    def test_identical_replay_survives_service_restart_and_conflict_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = _request()
            first_service = ContextGatewayService(_settings(root))
            first = first_service.lifecycle_projector.project(
                request, caller_id=CALLER_ID, caller_secret=CALLER_SECRET, now=NOW
            )

            restarted = ContextGatewayService(_settings(root))
            replay = restarted.lifecycle_projector.project(
                request,
                caller_id=CALLER_ID,
                caller_secret=CALLER_SECRET,
                now=NOW + timedelta(seconds=1),
            )
            changed_sources = (_source(content="different source truth"), _unavailable_source())
            conflict = replace(
                request,
                sources=changed_sources,
                sources_digest=canonical_sources_digest(changed_sources),
            )
            with self.assertRaises(LifecycleProjectionError) as caught:
                restarted.lifecycle_projector.project(
                    conflict,
                    caller_id=CALLER_ID,
                    caller_secret=CALLER_SECRET,
                    now=NOW + timedelta(seconds=2),
                )

            self.assertFalse(first["replayed"])
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["artifact_id"], first["artifact_id"])
            self.assertEqual(caught.exception.code, "context_projection_replay_conflict")
            record = restarted.lifecycle_projection(
                request.idempotency_key,
                caller_id=CALLER_ID,
                caller_secret=CALLER_SECRET,
            )
            self.assertEqual(record["response"]["artifact_id"], first["artifact_id"])

    def test_auth_age_size_digest_and_source_shape_fail_closed(self) -> None:
        cases = (
            ("untrusted", _request(), {}, "context_projection_unauthorized"),
            (
                CALLER_ID,
                _request(
                    requested_at=_timestamp(NOW - timedelta(minutes=10)),
                    sources=(
                        replace(
                            _source(),
                            captured_at=_timestamp(NOW - timedelta(minutes=11)),
                        ),
                    ),
                ),
                {},
                "context_projection_stale",
            ),
            (
                CALLER_ID,
                _request(),
                {"lifecycle_max_context_bytes": 32},
                "context_projection_oversized",
            ),
            (
                CALLER_ID,
                _request(sources_digest=f"sha256:{'0' * 64}"),
                {},
                "context_projection_invalid",
            ),
            (
                CALLER_ID,
                _request(
                    sources=(
                        replace(_source(), content_digest=f"sha256:{'0' * 64}"),
                    )
                ),
                {},
                "context_projection_invalid",
            ),
            (
                CALLER_ID,
                _request(
                    sources=(
                        replace(_source(), captured_at=_timestamp(NOW + timedelta(seconds=1))),
                    )
                ),
                {},
                "context_projection_invalid",
            ),
        )
        for caller_id, request, setting_overrides, expected_code in cases:
            with self.subTest(expected_code=expected_code), tempfile.TemporaryDirectory() as tmp:
                service = ContextGatewayService(_settings(Path(tmp), **setting_overrides))
                with self.assertRaises(LifecycleProjectionError) as caught:
                    service.lifecycle_projector.project(
                        request,
                        caller_id=caller_id,
                        caller_secret=CALLER_SECRET,
                        now=NOW,
                    )
                self.assertEqual(caught.exception.code, expected_code)
                _validate_schema(
                    "lifecycle-context-projection-error.schema.json",
                    caught.exception.to_dict(),
                )
                denial = next((Path(tmp) / ".cgg" / "lifecycle-denials").glob("*.json"))
                self.assertNotIn("secret-value", denial.read_text(encoding="utf-8"))

    def test_budget_truncation_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            content = "line of lifecycle evidence\n" * 1_000
            sources = (_source(content=content),)
            request = _request(
                sources=sources,
                sources_digest=canonical_sources_digest(sources),
                budget_tokens=25,
            )
            service = ContextGatewayService(_settings(Path(tmp)))

            result = service.lifecycle_projector.project(
                request, caller_id=CALLER_ID, caller_secret=CALLER_SECRET, now=NOW
            )

            self.assertTrue(result["budget"]["truncated"])
            self.assertIn("[CGG truncated]", result["content"])

    def test_inactive_or_unconfigured_runtime_denies_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inactive = ContextGatewayService(RuntimeSettings(root=Path(tmp)))
            with self.assertRaises(RuntimeGateError):
                inactive.project_lifecycle(
                    _request(), caller_id=CALLER_ID, caller_secret=CALLER_SECRET
                )

        with tempfile.TemporaryDirectory() as tmp:
            unconfigured = ContextGatewayService(
                RuntimeSettings(root=Path(tmp), runtime_profile_state="active")
            )
            self.assertFalse(
                unconfigured.readiness()["capabilities"]["lifecycle_projection"]["ready"]
            )
            with self.assertRaises(LifecycleProjectionError) as caught:
                unconfigured.project_lifecycle(
                    _request(), caller_id=CALLER_ID, caller_secret=CALLER_SECRET
                )
            self.assertEqual(caught.exception.code, "context_projection_unauthorized")

    def test_lifecycle_replay_namespace_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(_settings(Path(tmp)))
            request = _request(idempotency_key="shared-key")
            service.lifecycle_projector.project(
                request, caller_id=CALLER_ID, caller_secret=CALLER_SECRET, now=NOW
            )

            self.assertIsNotNone(service.lifecycle_projector.store.read("shared-key"))
            self.assertIsNone(service.work_design_projector.store.read("shared-key"))
            self.assertIsNone(service.refinement_projector.store.read("shared-key"))


if __name__ == "__main__":
    unittest.main()
