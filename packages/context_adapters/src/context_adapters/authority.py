from __future__ import annotations

import re


class AdapterPolicyError(ValueError):
    """Raised when a downstream adapter is asked to project unsafe context."""


ADAPTER_AUTHORITY = {
    "may_mutate_art": False,
    "may_approve_governance": False,
    "may_route_model_traffic": False,
    "may_read_raw_artifact": False,
    "authority": "context_projection_only",
}

_ARTIFACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def ensure_model_safe_packet(packet: dict[str, object]) -> None:
    if packet.get("purpose") != "model-safe context packet":
        raise AdapterPolicyError("downstream adapters only accept model-safe CGG packets")
    if not isinstance(packet.get("safe_context_excerpt"), str) or not packet.get(
        "safe_context_excerpt"
    ):
        raise AdapterPolicyError("packet is missing a safe_context_excerpt")
    admission = packet.get("admission_decision")
    if not isinstance(admission, dict):
        raise AdapterPolicyError("packet is missing an admission_decision")
    if admission.get("raw_projection") == "allowed-raw":
        raise AdapterPolicyError("downstream adapters deny packets that allow raw projection")
    if not _DIGEST_PATTERN.fullmatch(str(packet.get("artifact_digest") or "")):
        raise AdapterPolicyError("packet is missing a valid artifact_digest")
    if not isinstance(packet.get("captured_at"), str) or not packet.get("captured_at"):
        raise AdapterPolicyError("packet is missing captured_at")
    if packet.get("policy_profile") not in {"casual", "developer", "enterprise"}:
        raise AdapterPolicyError("packet is missing a valid policy_profile")


def ensure_packet_receipt_pair(
    packet: dict[str, object],
    receipt: dict[str, object],
) -> str:
    ensure_model_safe_packet(packet)
    artifact_id = receipt.get("artifact_id")
    packet_digest = packet.get("artifact_digest")
    receipt_digest = receipt.get("artifact_digest")
    if not isinstance(artifact_id, str) or not _ARTIFACT_ID_PATTERN.fullmatch(artifact_id):
        raise AdapterPolicyError("receipt is missing an artifact_id")
    if not _DIGEST_PATTERN.fullmatch(str(receipt_digest or "")):
        raise AdapterPolicyError("receipt is missing a valid artifact_digest")
    if packet_digest != receipt_digest:
        raise AdapterPolicyError("packet and receipt artifact digests do not match")
    decision = receipt.get("policy_profile_decision")
    if not isinstance(decision, dict):
        raise AdapterPolicyError("receipt is missing a policy_profile_decision")
    packet_decision = dict(packet["admission_decision"])
    if decision.get("raw_projection") != packet_decision.get("raw_projection"):
        raise AdapterPolicyError("packet and receipt raw-projection decisions do not match")
    if decision.get("profile") != packet.get("policy_profile"):
        raise AdapterPolicyError("packet and receipt policy profiles do not match")
    return artifact_id
