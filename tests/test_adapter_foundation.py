from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from context_adapters import (
    AdapterPolicyError,
    CodexStylePacketAdapter,
    LiteLlmPacketAdapter,
    OosReceiptAdapter,
    OperatorPacketAdapter,
    WgcfReceiptAdapter,
    build_default_adapter_registry,
)
from context_core.pipeline import ContextPipeline


def _packet_and_receipt(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    result = ContextPipeline(root).project_text(
        "ERROR failed with API_TOKEN=secret-value\n",
        source_label="adapter-test",
        profile_name="developer",
        budget_tokens=200,
    )
    packet = json.loads((root / result["packet_path"]).read_text(encoding="utf-8"))
    receipt = json.loads((root / result["receipt_path"]).read_text(encoding="utf-8"))
    return packet, receipt


class AdapterFoundationTests(unittest.TestCase):
    def test_wgcf_and_oos_adapters_are_read_only_evidence_contexts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packet, receipt = _packet_and_receipt(Path(tmp))
            wgcf = WgcfReceiptAdapter().to_evidence_input(packet, receipt)
            oos = OosReceiptAdapter().to_workflow_context(packet, receipt)

            self.assertFalse(wgcf["authority"]["may_mutate_art"])
            self.assertFalse(oos["authority"]["may_mutate_art"])
            self.assertEqual(wgcf["payload"]["evidence_kind"], "cgg_model_safe_context_packet")
            self.assertEqual(oos["payload"]["workflow_context_kind"], "cgg_packet_receipt_reference")
            self.assertNotIn("raw_artifact_path", json.dumps(wgcf))
            self.assertNotIn("full_artifact_location", json.dumps(oos))
            self.assertEqual(wgcf["schema_version"], 1)

    def test_ai_and_operator_adapters_project_safe_context_without_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packet, _ = _packet_and_receipt(Path(tmp))
            litellm = LiteLlmPacketAdapter().to_context_payload(packet)
            codex = CodexStylePacketAdapter().to_context_payload(packet)
            operator = OperatorPacketAdapter().to_context_payload(packet)

            self.assertEqual(litellm["payload"]["model_invocation"], "not_performed")
            self.assertEqual(codex["payload"]["gateway_role"], "not_a_llm_gateway")
            self.assertIn("<redacted:secret-env-var>", operator["payload"]["messages"][1]["content"])
            self.assertFalse(litellm["authority"]["may_route_model_traffic"])
            self.assertNotIn("raw_artifact_path", json.dumps(litellm))

    def test_adapter_denies_non_model_safe_or_raw_projection_packets(self) -> None:
        with self.assertRaises(AdapterPolicyError):
            LiteLlmPacketAdapter().to_context_payload({"purpose": "raw log"})
        with tempfile.TemporaryDirectory() as tmp:
            packet, _ = _packet_and_receipt(Path(tmp))
            packet["admission_decision"]["raw_projection"] = "allowed-raw"
            with self.assertRaises(AdapterPolicyError):
                CodexStylePacketAdapter().to_context_payload(packet)

    def test_default_adapter_registry_lists_governance_and_ai_consumers(self) -> None:
        registry = build_default_adapter_registry()

        self.assertIn("wgcf", registry["governance"])
        self.assertIn("oos", registry["governance"])
        self.assertIn("litellm", registry["ai_operator"])
        self.assertIn("openclaw", registry["ai_operator"])
        self.assertIn("ollama", registry["ai_operator"])
        self.assertEqual(registry["authority"]["mutation_authority"], "none")


if __name__ == "__main__":
    unittest.main()
