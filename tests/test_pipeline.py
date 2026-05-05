from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from context_core.pipeline import ContextPipeline
from context_core.redaction.detectors import redact_text


class ContextPipelineTests(unittest.TestCase):
    def test_init_creates_local_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = ContextPipeline(Path(tmp)).init_workspace()
            self.assertTrue(Path(result["workspace_path"]).is_dir())
            self.assertTrue((Path(tmp) / ".cgg" / "artifacts" / "raw").is_dir())
            self.assertTrue((Path(tmp) / ".cgg" / "ledger.jsonl").is_file())

    def test_redaction_masks_secret_like_values(self) -> None:
        redacted, report = redact_text("API_TOKEN=abc1234567890\nBearer abcdefghijklmnopqrstuvwxyz\n10.1.2.3\n")
        self.assertIn("API_TOKEN=<redacted:secret-env-var>", redacted)
        self.assertIn("Bearer <redacted:bearer-token>", redacted)
        self.assertIn("<redacted:private-ip>", redacted)
        self.assertGreaterEqual(report["finding_count"], 3)

    def test_capture_command_generates_artifacts_packet_receipt_and_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipeline = ContextPipeline(root)
            result = pipeline.capture_command(
                [
                    sys.executable,
                    "-c",
                    "import sys; print('hello'); print('ERROR: bad token API_TOKEN=secret-value', file=sys.stderr); sys.exit(2)",
                ],
                profile_name="developer",
                budget_tokens=200,
            )

            self.assertEqual(result["command"]["exit_code"], 2)
            packet = json.loads((root / result["packet_path"]).read_text(encoding="utf-8"))
            receipt = json.loads((root / result["receipt_path"]).read_text(encoding="utf-8"))
            manifest = json.loads((root / result["manifest_path"]).read_text(encoding="utf-8"))
            ledger_lines = (root / ".cgg" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()

            self.assertEqual(packet["purpose"], "model-safe context packet")
            self.assertTrue(packet["failure_summary"]["detected"])
            self.assertEqual(packet["admission_decision"]["raw_projection"], "denied")
            self.assertIn("<redacted:secret-env-var>", packet["safe_context_excerpt"])
            self.assertEqual(receipt["artifact_digest"], result["artifact_digest"])
            self.assertEqual(manifest["artifact_digest"], result["artifact_digest"])
            self.assertEqual(len(ledger_lines), 1)

    def test_pack_directory_collapses_repeated_logs_and_budgets_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / "logs"
            logs.mkdir()
            (logs / "app.log").write_text(("same line\n" * 12) + "fatal failure\n", encoding="utf-8")
            result = ContextPipeline(root).pack_path(logs, profile_name="developer", budget_tokens=20)
            packet = json.loads((root / result["packet_path"]).read_text(encoding="utf-8"))
            redacted_text = (root / result["redacted_artifact_path"]).read_text(encoding="utf-8")

            self.assertIn("fatal failure", packet["safe_context_excerpt"])
            self.assertIn("[CGG collapsed", redacted_text)
            self.assertLessEqual(packet["budget"]["estimated_tokens"], 25)

    def test_project_existing_artifact_preserves_raw_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "raw-output.txt"
            source.write_text("Traceback: failed\n", encoding="utf-8")
            result = ContextPipeline(root).project_artifact(source, profile_name="enterprise", budget_tokens=100)

            self.assertTrue((root / result["raw_artifact_path"]).is_file())
            self.assertTrue((root / result["receipt_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
