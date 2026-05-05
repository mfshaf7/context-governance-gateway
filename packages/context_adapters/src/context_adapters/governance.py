from __future__ import annotations

from dataclasses import dataclass

from .models import AdapterEnvelope, PacketReference, ReceiptReference


@dataclass(frozen=True)
class WgcfReceiptAdapter:
    consumer: str = "workspace-governance-control-fabric"

    def to_evidence_input(self, packet: dict[str, object], receipt: dict[str, object]) -> dict[str, object]:
        packet_reference = PacketReference.from_packet(packet)
        receipt_reference = ReceiptReference.from_receipt(receipt)
        return AdapterEnvelope(
            consumer=self.consumer,
            purpose="governance-evidence-context",
            packet_reference=packet_reference,
            receipt_reference=receipt_reference,
            payload={
                "evidence_kind": "cgg_model_safe_context_packet",
                "recommended_use": "read-only readiness, audit, or validation context",
                "denied_actions": ["art_mutation", "governance_approval", "raw_context_projection"],
            },
        ).to_dict()


@dataclass(frozen=True)
class OosReceiptAdapter:
    consumer: str = "operator-orchestration-service"

    def to_workflow_context(self, packet: dict[str, object], receipt: dict[str, object]) -> dict[str, object]:
        packet_reference = PacketReference.from_packet(packet)
        receipt_reference = ReceiptReference.from_receipt(receipt)
        return AdapterEnvelope(
            consumer=self.consumer,
            purpose="operator-workflow-context",
            packet_reference=packet_reference,
            receipt_reference=receipt_reference,
            payload={
                "workflow_context_kind": "cgg_packet_receipt_reference",
                "recommended_use": "attach or reference model-safe context in operator workflows",
                "denied_actions": ["art_mutation", "work_item_completion", "approval_decision"],
            },
        ).to_dict()
