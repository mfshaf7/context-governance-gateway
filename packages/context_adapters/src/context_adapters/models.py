from __future__ import annotations

from dataclasses import dataclass, field

from .authority import ADAPTER_AUTHORITY, ensure_model_safe_packet


@dataclass(frozen=True)
class PacketReference:
    artifact_digest: str
    captured_at: str
    policy_profile: str
    raw_projection: str
    redaction_count: int
    source: dict[str, object]

    @classmethod
    def from_packet(cls, packet: dict[str, object]) -> "PacketReference":
        ensure_model_safe_packet(packet)
        admission = dict(packet["admission_decision"])
        return cls(
            artifact_digest=str(packet["artifact_digest"]),
            captured_at=str(packet["captured_at"]),
            policy_profile=str(packet["policy_profile"]),
            raw_projection=str(admission.get("raw_projection")),
            redaction_count=len(list(packet.get("redactions_applied") or [])),
            source=dict(packet["source"]),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_digest": self.artifact_digest,
            "captured_at": self.captured_at,
            "policy_profile": self.policy_profile,
            "raw_projection": self.raw_projection,
            "redaction_count": self.redaction_count,
            "source": self.source,
        }


@dataclass(frozen=True)
class ReceiptReference:
    artifact_id: str
    artifact_digest: str
    raw_projection: str
    budget_truncated: bool

    @classmethod
    def from_receipt(cls, receipt: dict[str, object]) -> "ReceiptReference":
        decision = dict(receipt["policy_profile_decision"])
        denied = dict(receipt.get("what_was_denied_or_suppressed") or {})
        return cls(
            artifact_id=str(receipt["artifact_id"]),
            artifact_digest=str(receipt["artifact_digest"]),
            raw_projection=str(decision.get("raw_projection")),
            budget_truncated=bool(denied.get("budget_truncated")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_digest": self.artifact_digest,
            "raw_projection": self.raw_projection,
            "budget_truncated": self.budget_truncated,
        }


@dataclass(frozen=True)
class AdapterEnvelope:
    consumer: str
    purpose: str
    packet_reference: PacketReference
    receipt_reference: ReceiptReference | None = None
    payload: dict[str, object] = field(default_factory=dict)
    authority: dict[str, object] = field(default_factory=lambda: dict(ADAPTER_AUTHORITY))

    def to_dict(self) -> dict[str, object]:
        data = {
            "schema_version": 1,
            "consumer": self.consumer,
            "purpose": self.purpose,
            "packet_reference": self.packet_reference.to_dict(),
            "authority": self.authority,
            "payload": self.payload,
        }
        if self.receipt_reference is not None:
            data["receipt_reference"] = self.receipt_reference.to_dict()
        return data
