from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from context_core.pipeline import ContextPipeline
from context_core.profiles import get_profile
from context_policy import (
    CustomRecognizer,
    OpaPolicyEngine,
    build_default_detector_registry,
    evaluate_context_admission,
    scan_sensitive_context,
)


class PolicyFoundationTests(unittest.TestCase):
    def test_policy_denies_raw_projection_and_debug_override_on_sensitive_findings(self) -> None:
        _, redaction_report = scan_sensitive_context("API_TOKEN=secret-value\n")
        evaluation = evaluate_context_admission(
            profile=get_profile("developer"),
            redaction_report=redaction_report,
            debug_override_requested=True,
        )

        self.assertEqual(evaluation.admission_decision["raw_projection"], "denied")
        self.assertEqual(evaluation.admission_decision["debug_override"], "denied")
        self.assertTrue(evaluation.admission_decision["redaction_safe"])
        self.assertEqual(evaluation.opa["status"], "adapter_seam_not_configured")

    def test_detector_registry_reports_local_findings_and_external_scanner_seams(self) -> None:
        redacted, report = scan_sensitive_context("Bearer abcdefghijklmnopqrstuvwxyz\n10.2.3.4\n")

        self.assertIn("Bearer <redacted:bearer-token>", redacted)
        self.assertEqual(report["finding_count"], 2)
        self.assertIn("local-deterministic-rules", report["detector_sources"])
        unavailable = {item["name"]: item["status"] for item in report["unavailable_integrations"]}
        self.assertEqual(unavailable["presidio"], "not_configured")
        self.assertEqual(unavailable["gitleaks"], "not_configured")
        self.assertEqual(unavailable["trufflehog"], "not_configured")

    def test_custom_recognizer_can_extend_detection_without_changing_core_rules(self) -> None:
        registry = build_default_detector_registry(
            (
                CustomRecognizer(
                    code="ticket-secret",
                    pattern=r"TICKET-[0-9]{4}-SECRET",
                    replacement="<redacted:ticket-secret>",
                    description="Example operator-owned recognizer",
                ),
            )
        )
        redacted, report = scan_sensitive_context("TICKET-1234-SECRET\n", registry=registry)

        self.assertIn("<redacted:ticket-secret>", redacted)
        self.assertEqual(report["finding_count"], 1)
        self.assertIn("configured-custom-recognizers", report["detector_sources"])

    def test_opa_policy_engine_is_explicit_adapter_seam(self) -> None:
        engine = OpaPolicyEngine()

        self.assertEqual(engine.status()["status"], "not_configured")
        with self.assertRaises(NotImplementedError):
            engine.evaluate(package="context.admission", input_document={})

    def test_pipeline_records_policy_and_detector_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = ContextPipeline(root).project_text(
                "ERROR failed with API_TOKEN=secret-value\n",
                source_label="unit-test",
                profile_name="developer",
                budget_tokens=200,
            )
            packet = json.loads((root / result["packet_path"]).read_text(encoding="utf-8"))
            manifest = json.loads((root / result["manifest_path"]).read_text(encoding="utf-8"))
            report = json.loads((root / ".cgg" / "manifests" / f"{result['artifact_id']}.redaction-report.json").read_text(encoding="utf-8"))

            self.assertEqual(packet["context_admission"]["admission_decision"]["raw_projection"], "denied")
            self.assertEqual(packet["context_admission"]["opa"]["status"], "adapter_seam_not_configured")
            self.assertIn("local-deterministic-rules", manifest["detectors"]["sources"])
            self.assertEqual(report["report"]["findings"][0]["source"], "local-deterministic-rules")


if __name__ == "__main__":
    unittest.main()
