from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from context_adapters import (
    AdapterPolicyError,
    GovernedAiGatewayContextAdapter,
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

    def test_gateway_and_operator_adapters_project_safe_context_without_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packet, receipt = _packet_and_receipt(Path(tmp))
            gateway = GovernedAiGatewayContextAdapter().to_model_safe_packet(packet, receipt)
            operator = OperatorPacketAdapter().to_context_payload(packet)

            self.assertEqual(
                set(gateway),
                {"packet_ref", "redaction_receipt_ref", "content"},
            )
            self.assertTrue(gateway["packet_ref"].startswith("/v1/context/packets/"))
            self.assertTrue(
                gateway["redaction_receipt_ref"].startswith("/v1/context/receipts/")
            )
            self.assertIn("<redacted:secret-env-var>", gateway["content"])
            self.assertIn("<redacted:secret-env-var>", operator["payload"]["content"])
            self.assertFalse(operator["authority"]["may_route_model_traffic"])
            self.assertNotIn("artifacts/raw", json.dumps(operator))

    def test_adapter_denies_non_model_safe_or_raw_projection_packets(self) -> None:
        with self.assertRaises(AdapterPolicyError):
            GovernedAiGatewayContextAdapter().to_model_safe_packet(
                {"purpose": "raw log"},
                {},
            )
        with tempfile.TemporaryDirectory() as tmp:
            packet, receipt = _packet_and_receipt(Path(tmp))
            packet["admission_decision"]["raw_projection"] = "allowed-raw"
            with self.assertRaises(AdapterPolicyError):
                GovernedAiGatewayContextAdapter().to_model_safe_packet(packet, receipt)

    def test_adapters_reject_packet_and_receipt_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packet, receipt = _packet_and_receipt(Path(tmp))
            receipt["artifact_digest"] = f"sha256:{'0' * 64}"

            with self.assertRaisesRegex(AdapterPolicyError, "digests do not match"):
                GovernedAiGatewayContextAdapter().to_model_safe_packet(packet, receipt)
            with self.assertRaisesRegex(AdapterPolicyError, "digests do not match"):
                WgcfReceiptAdapter().to_evidence_input(packet, receipt)

    def test_gateway_rejects_incomplete_or_inconsistent_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packet, receipt = _packet_and_receipt(Path(tmp))
            receipt_without_id = dict(receipt)
            receipt_without_id.pop("artifact_id")
            with self.assertRaisesRegex(AdapterPolicyError, "artifact_id"):
                GovernedAiGatewayContextAdapter().to_model_safe_packet(
                    packet,
                    receipt_without_id,
                )

            receipt_with_wrong_profile = dict(receipt)
            receipt_with_wrong_profile["policy_profile_decision"] = {
                **dict(receipt["policy_profile_decision"]),
                "profile": "enterprise",
            }
            with self.assertRaisesRegex(AdapterPolicyError, "policy profiles"):
                GovernedAiGatewayContextAdapter().to_model_safe_packet(
                    packet,
                    receipt_with_wrong_profile,
                )

    def test_adapter_references_do_not_expose_raw_source_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packet, receipt = _packet_and_receipt(Path(tmp))
            envelope = OosReceiptAdapter().to_workflow_context(packet, receipt)

            self.assertNotIn("source", envelope["packet_reference"])
            self.assertNotIn('"source"', json.dumps(envelope))

    def test_default_adapter_registry_lists_governance_and_context_consumers(self) -> None:
        registry = build_default_adapter_registry()

        self.assertIn("wgcf", registry["governance"])
        self.assertIn("oos", registry["governance"])
        self.assertIn("governed_ai_gateway", registry["context_consumers"])
        self.assertIn("operator", registry["context_consumers"])
        self.assertNotIn("ai_operator", registry)
        self.assertEqual(registry["authority"]["mutation_authority"], "none")


if __name__ == "__main__":
    unittest.main()
