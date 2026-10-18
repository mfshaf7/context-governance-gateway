from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator, ValidationError

from cgg_api import (
    ContextGatewayService,
    LifecycleContextProjectionRequest,
    LifecycleContextSource,
    LifecycleProjectionError,
    PrototypeLifecycleSubject,
    RuntimeGateError,
    RuntimeSettings,
    canonical_sources_digest,
)
from cgg_api.app import create_app


CALLER = "operator-orchestration-service"
SECRET = "test-prototype-context-secret"
NOW = datetime.now(timezone.utc).replace(microsecond=0)
SCHEMAS = Path(__file__).resolve().parents[1] / "contracts" / "schemas"


def _timestamp(now=NOW):
    return now.isoformat().replace("+00:00", "Z")


def _subject(**changes):
    return replace(PrototypeLifecycleSubject(
        prototype_id="prototype:sample-exploration",
        registry_ref="record://prototypes/sample-exploration",
        registry_revision="a" * 40,
        source_ref="repo://dedicated-sample-owner/app",
        source_revision="b" * 40,
    ), **changes)


def _request(now=NOW, **changes):
    content = "Selected Prototype source context API_TOKEN=private-test-value"
    sources = (LifecycleContextSource(
        source_id="selected-source", source_class="repository",
        source_ref="repo://dedicated-sample-owner/app/sample.txt",
        source_revision="b" * 40, captured_at=_timestamp(now),
        availability="available", content=content,
        content_digest="sha256:" + hashlib.sha256(content.encode()).hexdigest(),
        unavailable_reason=None,
    ), LifecycleContextSource(
        source_id="preview-state", source_class="runtime",
        source_ref="devint://prototype/sample-exploration/preview",
        source_revision=None, captured_at=_timestamp(now),
        availability="unavailable", content=None, content_digest=None,
        unavailable_reason="not_configured",
    ))
    return replace(LifecycleContextProjectionRequest(
        request_id="prototype-context-request", correlation_id="prototype-correlation",
        idempotency_key="prototype-context-example", workflow_session_id="prototype-session",
        execution_id="prototype-execution", delivery_id=None, work_item_ref=None,
        landing_unit_id="prototype-sample-source", operator_id="operator:sample",
        operation="continue", lifecycle_state="prototype-source-work", next_action="draft",
        requested_at=_timestamp(now), sources=sources,
        sources_digest=canonical_sources_digest(sources), budget_tokens=4_000,
        subject=_subject(),
    ), **changes)


def _settings(root, **changes):
    return RuntimeSettings(root=root, lifecycle_caller_shared_secret=SECRET,
                           runtime_profile_state=changes.pop("runtime_profile_state", "active"), **changes)


def _wire(request):
    value = request.binding(CALLER)
    del value["caller_id"]
    value["operator"] = {"id": value.pop("operator_id")}
    value["schema_version"] = 1
    value["sources"] = [source.canonical_value() for source in request.sources]
    return value


def _validate(name, value):
    schema = json.loads((SCHEMAS / name).read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER).validate(value)


class PrototypeLifecycleProjectionTests(unittest.TestCase):
    def test_canonical_studio_slug_grammar_accepts_short_ids_through_the_actual_projector(self):
        for slug in ("a", "0", "sample", "sample-1"):
            request = _request(subject=_subject(prototype_id=f"prototype:{slug}", registry_ref=f"record://prototypes/{slug}"))
            _validate("prototype-lifecycle-context-projection-request.schema.json", _wire(request))
            with self.subTest(slug=slug), tempfile.TemporaryDirectory() as tmp:
                result = ContextGatewayService(_settings(Path(tmp))).project_lifecycle(request, caller_id=CALLER, caller_secret=SECRET)
                _validate("prototype-lifecycle-context-projection-result.schema.json", result)
                self.assertEqual(result["binding"]["subject"]["prototype_id"], f"prototype:{slug}")

    def test_noncanonical_slug_grammar_is_denied_by_runtime_and_both_closed_schemas(self):
        for slug in ("-a", "a-", "a--b", "a_b", "A"):
            request = _request(subject=_subject(prototype_id=f"prototype:{slug}", registry_ref=f"record://prototypes/{slug}"))
            with self.subTest(slug=slug), self.assertRaises(ValidationError):
                _validate("prototype-lifecycle-context-projection-request.schema.json", _wire(request))
            with self.subTest(slug=slug), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(LifecycleProjectionError):
                    ContextGatewayService(_settings(Path(tmp))).project_lifecycle(request, caller_id=CALLER, caller_secret=SECRET)
            with tempfile.TemporaryDirectory() as tmp:
                valid = ContextGatewayService(_settings(Path(tmp))).project_lifecycle(_request(), caller_id=CALLER, caller_secret=SECRET)
                valid["binding"]["subject"] = request.subject.binding()
                with self.subTest(slug=slug), self.assertRaises(ValidationError):
                    _validate("prototype-lifecycle-context-projection-result.schema.json", valid)

    def test_both_request_schemas_are_closed_and_cannot_mix_subjects(self):
        payload = _wire(_request())
        cases = [
            {**payload, "delivery_id": "delivery-1164"},
            {**payload, "work_item_ref": "invented-work"},
            {**payload, "subject": {**payload["subject"], "extra": "untrusted"}},
            {**payload, "subject": {**payload["subject"], "source_ref": "repo://sample/../other"}},
        ]
        with self.assertRaises(ValidationError):
            _validate("lifecycle-context-projection-request.schema.json", payload)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValidationError):
                _validate("prototype-lifecycle-context-projection-request.schema.json", case)

    def test_projects_separate_registry_and_source_without_delivery_or_action_authority(self):
        request = _request()
        _validate("prototype-lifecycle-context-projection-request.schema.json", _wire(request))
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(_settings(Path(tmp)))
            result = service.project_lifecycle(request, caller_id=CALLER, caller_secret=SECRET)
            _validate("prototype-lifecycle-context-projection-result.schema.json", result)
            self.assertEqual(result["binding"]["subject"], request.subject.binding())
            self.assertNotEqual(request.subject.registry_revision, request.subject.source_revision)
            self.assertNotIn("delivery_id", result["binding"])
            self.assertNotIn("work_item_ref", result["binding"])
            self.assertEqual(request.source_scope, request.subject.prototype_id)
            self.assertEqual(request.package_ref, request.subject.registry_ref)
            self.assertEqual(result["source_summary"]["unavailable"], 1)
            self.assertFalse(result["lifecycle_authority"]["may_mutate_source"])
            self.assertFalse(result["lifecycle_authority"]["may_invoke_model"])
            self.assertTrue(result["projection_safety"]["custody_bound"])
            self.assertNotIn("private-test-value", json.dumps(result))
            self.assertNotIn("content", result["source_bindings"][0])
            stored = service.lifecycle_projector.store.read(request.idempotency_key)
            self.assertNotIn("private-test-value", json.dumps(stored))
            with self.assertRaises(ValidationError):
                _validate("lifecycle-context-projection-result.schema.json", result)

    def test_legacy_delivery_result_and_schema_remain_unchanged(self):
        request = _request(subject=None, delivery_id="delivery-1164",
                           work_item_ref="openproject://work_packages/1164")
        _validate("lifecycle-context-projection-request.schema.json", _wire(request))
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(_settings(Path(tmp)))
            result = service.project_lifecycle(request, caller_id=CALLER, caller_secret=SECRET)
            _validate("lifecycle-context-projection-result.schema.json", result)
            self.assertEqual(result["schema_version"], 1)
            self.assertNotIn("subject", result["binding"])
            self.assertEqual(result["binding"]["delivery_id"], "delivery-1164")
            self.assertEqual(request.source_scope, "delivery-1164")
            with self.assertRaises(ValidationError):
                _validate("prototype-lifecycle-context-projection-result.schema.json", result)

    def test_identical_replay_and_readback_survive_restart(self):
        request = _request()
        with tempfile.TemporaryDirectory() as tmp:
            first = ContextGatewayService(_settings(Path(tmp))).project_lifecycle(
                request, caller_id=CALLER, caller_secret=SECRET)
            restarted = ContextGatewayService(_settings(Path(tmp)))
            replay = restarted.project_lifecycle(request, caller_id=CALLER, caller_secret=SECRET)
            readback = restarted.lifecycle_projection(request.idempotency_key,
                                                     caller_id=CALLER, caller_secret=SECRET)
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["artifact_id"], first["artifact_id"])
            self.assertEqual(readback["response"], first)
            self.assertEqual(replay["projection_receipt_ref"], first["projection_receipt_ref"])

    def test_subject_revision_session_execution_operator_and_contract_reuse_conflict(self):
        request = _request()
        conflicts = [
            replace(request, subject=_subject(prototype_id="prototype:other-sample",
                                              registry_ref="record://prototypes/other-sample")),
            replace(request, subject=_subject(registry_revision="c" * 40)),
            replace(request, subject=_subject(source_revision="c" * 40)),
            replace(request, subject=_subject(source_ref="repo://another-owner/app")),
            replace(request, workflow_session_id="different-session"),
            replace(request, execution_id="different-execution"),
            replace(request, operator_id="operator:another"),
            replace(request, subject=None, delivery_id="delivery-1164",
                    work_item_ref="openproject://work_packages/1164"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(_settings(Path(tmp)))
            first = service.project_lifecycle(request, caller_id=CALLER, caller_secret=SECRET)
            for changed in conflicts:
                with self.subTest(binding=changed.binding(CALLER)):
                    with self.assertRaises(LifecycleProjectionError) as caught:
                        service.project_lifecycle(changed, caller_id=CALLER, caller_secret=SECRET)
                    self.assertEqual(caught.exception.code, "context_projection_replay_conflict")
            self.assertEqual(service.lifecycle_projection(request.idempotency_key,
                caller_id=CALLER, caller_secret=SECRET)["response"], first)

        # The inverse direction must preserve an already-stored Delivery result.
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(_settings(Path(tmp)))
            legacy = replace(request, subject=None, delivery_id="delivery-1164",
                             work_item_ref="openproject://work_packages/1164")
            first = service.project_lifecycle(legacy, caller_id=CALLER, caller_secret=SECRET)
            with self.assertRaises(LifecycleProjectionError) as caught:
                service.project_lifecycle(request, caller_id=CALLER, caller_secret=SECRET)
            self.assertEqual(caught.exception.code, "context_projection_replay_conflict")
            self.assertEqual(service.lifecycle_projection(request.idempotency_key,
                caller_id=CALLER, caller_secret=SECRET)["response"], first)

    def test_malformed_or_mixed_subjects_are_bounded_denials(self):
        requests = [
            _request(subject=None), _request(subject="not-a-subject"),
            _request(delivery_id="delivery-1164"), _request(work_item_ref="invented-work"),
            _request(subject=_subject(kind="delivery")),
            _request(subject=_subject(prototype_id="prototype:../escape")),
            _request(subject=_subject(registry_ref="record://prototypes/another-prototype")),
            _request(subject=_subject(registry_revision="main")),
            _request(subject=_subject(source_revision="HEAD")),
            _request(subject=_subject(source_ref="repo://sample/../other")),
            _request(subject=_subject(source_ref="repo://sample/./app")),
            _request(subject=_subject(source_ref="https://provider.invalid/source")),
            _request(subject=_subject(source_ref="repo://sample/app?token=private-test-value")),
        ]
        for request in requests:
            with self.subTest(subject=request.subject), tempfile.TemporaryDirectory() as tmp:
                service = ContextGatewayService(_settings(Path(tmp)))
                with self.assertRaises(LifecycleProjectionError) as caught:
                    service.project_lifecycle(request, caller_id=CALLER, caller_secret=SECRET)
                self.assertEqual(caught.exception.code, "context_projection_invalid")
                self.assertIsNone(service.lifecycle_projector.store.read(request.idempotency_key))
                self.assertNotIn("private-test-value", str(caught.exception))

    def test_existing_auth_runtime_digest_age_size_and_budget_gates_apply(self):
        request = _request()
        cases = [
            (request, {}, "untrusted", SECRET, "context_projection_unauthorized"),
            (request, {}, CALLER, "wrong-secret", "context_projection_unauthorized"),
            (request, {"lifecycle_max_context_bytes": 32}, CALLER, SECRET, "context_projection_oversized"),
            (_request(now=NOW - timedelta(minutes=10)), {}, CALLER, SECRET, "context_projection_stale"),
            (replace(request, sources_digest="sha256:" + "0" * 64), {}, CALLER, SECRET, "context_projection_invalid"),
            (replace(request, budget_tokens=8_001), {}, CALLER, SECRET, "context_projection_oversized"),
        ]
        for item, settings, caller, secret, code in cases:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                service = ContextGatewayService(_settings(Path(tmp), **settings))
                with self.assertRaises(LifecycleProjectionError) as caught:
                    service.project_lifecycle(item, caller_id=caller, caller_secret=secret)
                self.assertEqual(caught.exception.code, code)
                self.assertIsNone(service.lifecycle_projector.store.read(item.idempotency_key))
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(_settings(Path(tmp), runtime_profile_state="build-admitted"))
            with self.assertRaises(RuntimeGateError):
                service.project_lifecycle(request, caller_id=CALLER, caller_secret=SECRET)

    def test_pending_recovery_and_truncation_use_existing_custody_kernel(self):
        request = _request(budget_tokens=25)
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(_settings(Path(tmp)))
            service.lifecycle_projector.store.create(request.idempotency_key, {
                "schema_version": 1, "status": "pending", "attempt": 1,
                "idempotency_key": request.idempotency_key,
                "binding": request.binding(CALLER), "request_digest": request.request_digest(CALLER),
                "started_at": _timestamp(NOW - timedelta(seconds=130)),
            })
            result = service.project_lifecycle(request, caller_id=CALLER, caller_secret=SECRET)
            self.assertTrue(result["budget"]["truncated"])
            self.assertEqual(result["binding"]["subject"], request.subject.binding())
            self.assertEqual(service.lifecycle_projector.store.read(request.idempotency_key)["attempt"], 2)

    def test_another_allowed_caller_cannot_replay_or_read_projection(self):
        request = _request()
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(_settings(Path(tmp), lifecycle_allowed_callers=frozenset({CALLER, "other-caller"})))
            service.project_lifecycle(request, caller_id=CALLER, caller_secret=SECRET)
            with self.assertRaises(LifecycleProjectionError) as caught:
                service.project_lifecycle(request, caller_id="other-caller", caller_secret=SECRET)
            self.assertEqual(caught.exception.code, "context_projection_replay_conflict")
            with self.assertRaises(LifecycleProjectionError):
                service.lifecycle_projection(request.idempotency_key, caller_id="other-caller", caller_secret=SECRET)


class PrototypeLifecycleApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_application_projects_replays_and_reads_closed_subject(self):
        payload = _wire(_request())
        headers = {"x-cgg-caller-id": CALLER, "x-cgg-caller-secret": SECRET}
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(_settings(Path(tmp)))
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                first = await client.post("/v1/context/lifecycle/projections", json=payload, headers=headers)
                self.assertEqual(first.status_code, 200, first.text)
                _validate("prototype-lifecycle-context-projection-result.schema.json", first.json())
                replay = await client.post("/v1/context/lifecycle/projections", json=payload, headers=headers)
                readback = await client.get("/v1/context/lifecycle/projections/prototype-context-example", headers=headers)
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertEqual(readback.status_code, 200, readback.text)
                self.assertTrue(replay.json()["replayed"])
                self.assertEqual(first.json()["binding"]["subject"], payload["subject"])
                self.assertEqual(first.json()["artifact_id"], readback.json()["response"]["artifact_id"])
                self.assertNotIn("private-test-value", first.text)

    async def test_http_rejects_extra_mixed_wrong_subject_and_scope_without_echo(self):
        headers = {"x-cgg-caller-id": CALLER, "x-cgg-caller-secret": SECRET}
        payload = _wire(_request())
        malformed = [
            {**payload, "delivery_id": "delivery-1164", "work_item_ref": "invented"},
            {**payload, "subject": {**payload["subject"], "extra": "API_TOKEN=private-test-value"}},
            {**payload, "subject": {**payload["subject"], "kind": "delivery"}},
            {**payload, "subject": {**payload["subject"], "registry_ref": "record://prototypes/other-sample"}},
            {**payload, "subject": {**payload["subject"], "source_ref": "repo://sample/../other"}},
            {**payload, "subject": {**payload["subject"], "source_revision": "main"}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(_settings(Path(tmp)))
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                for item in malformed:
                    with self.subTest(subject=item["subject"]):
                        response = await client.post("/v1/context/lifecycle/projections", json=item, headers=headers)
                        self.assertIn(response.status_code, {400, 422}, response.text)
                        self.assertEqual(response.json()["detail"]["code"], "context_projection_invalid")
                        self.assertNotIn("private-test-value", response.text)
                unauthorized = await client.post("/v1/context/lifecycle/projections", json=payload,
                    headers={**headers, "x-cgg-caller-secret": "wrong-secret"})
                self.assertEqual(unauthorized.status_code, 403, unauthorized.text)


if __name__ == "__main__":
    unittest.main()
