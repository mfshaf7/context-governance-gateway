from __future__ import annotations

from dataclasses import dataclass

from .authority import ensure_packet_receipt_pair


@dataclass(frozen=True)
class GovernedAiGatewayContextAdapter:
    """Build the provider-neutral context object accepted by the platform gateway."""

    def to_model_safe_packet(
        self,
        packet: dict[str, object],
        receipt: dict[str, object],
    ) -> dict[str, str]:
        artifact_id = ensure_packet_receipt_pair(packet, receipt)
        return {
            "packet_ref": f"/v1/context/packets/{artifact_id}",
            "redaction_receipt_ref": f"/v1/context/receipts/{artifact_id}",
            "content": str(packet["safe_context_excerpt"]),
        }
