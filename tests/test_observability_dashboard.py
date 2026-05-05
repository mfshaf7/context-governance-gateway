from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cgg_api import ContextGatewayService, RuntimeSettings
from cgg_dashboard import build_dashboard_snapshot, render_dashboard_text
from context_observability import AdmissionObservation, build_prometheus_metrics, build_trace_spans


class ObservabilityDashboardTests(unittest.TestCase):
    def test_service_emits_safe_metrics_traces_and_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(RuntimeSettings(root=Path(tmp), runtime_profile_state="active"))
            result = service.project_text(
                "ERROR failed with API_TOKEN=secret-value\n",
                source_label="unit-test",
                profile_name="developer",
                budget_tokens=200,
            )

            metrics = service.prometheus_metrics()
            traces = service.trace_spans()
            dashboard = service.operator_dashboard()
            dashboard_text = service.operator_dashboard_text()
            combined_safe_payload = json.dumps(
                {
                    "metrics": metrics,
                    "traces": traces,
                    "dashboard": dashboard,
                    "dashboard_text": dashboard_text,
                },
                sort_keys=True,
            )

            self.assertIn("cgg_context_admission_packets_total", metrics)
            self.assertIn('policy_profile="developer"', metrics)
            self.assertEqual(traces["spans"][0]["attributes"]["cgg.artifact_digest"], result["artifact_digest"])
            self.assertEqual(dashboard["purpose"], "operator-safe-context-admission-dashboard")
            self.assertEqual(dashboard["summary"]["packet_count"], 1)
            self.assertEqual(dashboard["safety_posture"]["raw_context_visible"], False)
            self.assertIn(result["artifact_digest"], combined_safe_payload)
            self.assertNotIn("secret-value", combined_safe_payload)
            self.assertNotIn("raw_artifact_path", combined_safe_payload)
            self.assertNotIn("safe_context_excerpt", combined_safe_payload)

    def test_observability_exports_are_safe_metadata_seams(self) -> None:
        packet = {
            "purpose": "model-safe context packet",
            "source": {"type": "command", "command": "cat private.log"},
            "captured_at": "2026-05-05T00:00:00Z",
            "artifact_digest": "abc123",
            "failure_summary": {"detected": True},
            "policy_profile": "enterprise",
            "admission_decision": {"raw_projection": "denied"},
            "context_admission": {"decisions": [{"control": "raw_projection", "decision": "denied"}]},
            "budget": {"requested_tokens": 100, "estimated_tokens": 12, "truncated": False},
            "redactions_applied": [{"kind": "secret"}],
            "safe_context_excerpt": "redacted",
        }
        manifest = {
            "detectors": {
                "sources": ["deterministic-regex"],
                "unavailable_integrations": ["presidio"],
            }
        }
        receipt = {"artifact_id": "artifact-1", "artifact_digest": "abc123"}
        redaction_report = {"report": {"finding_count": 1}}
        observation = AdmissionObservation.from_artifacts(
            manifest=manifest,
            packet=packet,
            receipt=receipt,
            redaction_report=redaction_report,
        )

        metrics = [sample.to_dict() for sample in build_prometheus_metrics([observation])]
        spans = [span.to_dict() for span in build_trace_spans([observation])]
        dashboard = build_dashboard_snapshot([observation])
        text = render_dashboard_text(dashboard)

        self.assertEqual(observation.budget_limit_tokens, 100)
        self.assertNotIn("abc123", json.dumps(metrics, sort_keys=True))
        self.assertEqual(spans[0]["attributes"]["cgg.artifact_digest"], "abc123")
        self.assertEqual(dashboard["recent_admissions"][0]["artifact_digest"], "abc123")
        self.assertIn("Context Governance Gateway dashboard", text)
        self.assertFalse(dashboard["safety_posture"]["raw_artifact_locations_visible"])


if __name__ == "__main__":
    unittest.main()
