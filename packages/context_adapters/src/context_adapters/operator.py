from __future__ import annotations

from dataclasses import dataclass

from .models import AdapterEnvelope, PacketReference


@dataclass(frozen=True)
class OperatorPacketAdapter:
    consumer: str = "human-operator"

    def to_context_payload(self, packet: dict[str, object]) -> dict[str, object]:
        packet_reference = PacketReference.from_packet(packet)
        return AdapterEnvelope(
            consumer=self.consumer,
            purpose="operator-safe-context",
            packet_reference=packet_reference,
            payload={
                "content": str(packet["safe_context_excerpt"]),
            },
        ).to_dict()
