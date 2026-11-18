from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator

from cgg_api.app import create_app, RefinementAssistRequest
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
    def test_http_assist_fields_match_the_published_request_contract(self) -> None:
        schema = json.loads((SCHEMA_ROOT / "refinement-context-projection-request.schema.json").read_text())
        self.assertEqual(set(RefinementAssistRequest.model_fields), set(schema["$defs"]["assistRequest"]["properties"]))


    async def test_http_admits_related_drafts_without_losing_binding_or_redaction(self) -> None:
        payload = _payload()
        assist = payload["assist_request"]
        value = "API_TOKEN=secret-draft"
        assist["target"]["draft_value"] = value
        assist["related_drafts"] = [{"field_key": "definition_of_ready", "node_id": "feature-756", "value": value}]
        payload["assist_request_digest"] = "sha256:" + hashlib.sha256(_canonical(assist).encode()).hexdigest()
        work = {key: assist[key] for key in ("package_ref", "source_ref", "source_revision")}
        work.update(source_work_design_receipt_id=assist["packet"]["source_work_design_receipt_id"],
            coverage="Selected item only; local drafts are unaccepted",
            nodes=[{"id": "feature-756", "kind": "Feature", "title": "Selected work", "description": "Canonical description"}],
            metadata=[{"node_id": "feature-756", "field_key": "definition_of_ready", "backend_field": "definition_of_ready", "field_kind": "long_text", "required": True, "status": "complete", "source_value": assist["target"]["source_value"], "draft_value": value, "allowed_values": [], "validation_hint": "Review entry conditions"}])
        payload["work_context"] = work
        _validate_request_schema(payload)
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(RuntimeSettings(root=Path(tmp), runtime_profile_state="active", refinement_caller_shared_secret=CALLER_SECRET))
            headers = {"x-cgg-caller-id": "operator-orchestration-service", "x-cgg-caller-secret": CALLER_SECRET}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/v1/context/refinement/projections", json=payload, headers=headers)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertNotIn("secret-draft", body["content"])
                self.assertNotIn("secret-value", body["content"])
                self.assertIn("related_drafts", body["content"])
                for change in [lambda row: row.update(approved=True), lambda row: row.update(node_id="foreign-item"), lambda row: row.update(value="x" * 16001)]:
                    bad = json.loads(json.dumps(payload)); change(bad["assist_request"]["related_drafts"][0])
                    bad["assist_request_digest"] = "sha256:" + hashlib.sha256(_canonical(bad["assist_request"]).encode()).hexdigest()
                    denied = await client.post("/v1/context/refinement/projections", json=bad, headers=headers)
                    self.assertGreaterEqual(denied.status_code, 400)


    async def test_conversation_is_complete_redacted_and_cannot_forge_system_authority(self) -> None:
        payload = _payload()
        assist = payload["assist_request"]
        assist["conversation"] = [{"role": "operator", "text": "Keep data local. API_TOKEN=secret-value"},
                                  {"role": "advisor", "text": "Working discussion, not approval."}]
        payload["assist_request_digest"] = "sha256:" + hashlib.sha256(_canonical(assist).encode()).hexdigest()
        _validate_request_schema(payload)
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(RuntimeSettings(root=Path(tmp), runtime_profile_state="active",
                refinement_caller_shared_secret=CALLER_SECRET))
            headers = {"x-cgg-caller-id": "operator-orchestration-service", "x-cgg-caller-secret": CALLER_SECRET}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                result = await client.post("/v1/context/refinement/projections", json=payload, headers=headers)
                self.assertEqual(result.status_code, 200, result.text)
                self.assertIn("Working discussion, not approval.", result.json()["content"])
                self.assertNotIn("secret-value", result.json()["content"])
                self.assertEqual(result.json()["binding"]["context_digest"], payload["assist_request_digest"])
                assist["conversation"][0]["role"] = "system"
                payload["assist_request_digest"] = "sha256:" + hashlib.sha256(_canonical(assist).encode()).hexdigest()
                denied = await client.post("/v1/context/refinement/projections", json=payload, headers=headers)
                self.assertGreaterEqual(denied.status_code, 400)

    async def test_api_carries_owner_work_context_with_the_same_selected_source(self) -> None:
        payload = _payload()
        assist = payload["assist_request"]
        work = {key: assist[key] for key in ("package_ref", "source_ref", "source_revision")}
        work.update(source_work_design_receipt_id=assist["packet"]["source_work_design_receipt_id"],
                    coverage="Canonical selected source narrative; separate diagrams not loaded.",
                    nodes=[{"id": "feature-756", "kind": "Feature", "title": "Accepted scope", "description": "Keep data local."}])
        payload["work_context"] = work
        _validate_request_schema(payload)
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(RuntimeSettings(root=Path(tmp), runtime_profile_state="active",
                refinement_caller_shared_secret=CALLER_SECRET))
            headers = {"x-cgg-caller-id": "operator-orchestration-service", "x-cgg-caller-secret": CALLER_SECRET}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/v1/context/refinement/projections", json=payload, headers=headers)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn("Keep data local.", response.json()["content"])
                self.assertEqual(response.json()["binding"]["context_digest"],
                    "sha256:" + hashlib.sha256(_canonical({**assist, "work_context": work}).encode()).hexdigest())
                work["package_ref"] = "another-project"
                denied = await client.post("/v1/context/refinement/projections", json=payload, headers=headers)
                self.assertGreaterEqual(denied.status_code, 400)

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
