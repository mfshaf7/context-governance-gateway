from __future__ import annotations


class AdapterPolicyError(ValueError):
    """Raised when a downstream adapter is asked to project unsafe context."""


ADAPTER_AUTHORITY = {
    "may_mutate_art": False,
    "may_approve_governance": False,
    "may_route_model_traffic": False,
    "may_read_raw_artifact": False,
    "authority": "context_projection_only",
}


def ensure_model_safe_packet(packet: dict[str, object]) -> None:
    if packet.get("purpose") != "model-safe context packet":
        raise AdapterPolicyError("downstream adapters only accept model-safe CGG packets")
    if not isinstance(packet.get("safe_context_excerpt"), str):
        raise AdapterPolicyError("packet is missing a safe_context_excerpt")
    admission = packet.get("admission_decision")
    if not isinstance(admission, dict):
        raise AdapterPolicyError("packet is missing an admission_decision")
    if admission.get("raw_projection") == "allowed-raw":
        raise AdapterPolicyError("downstream adapters deny packets that allow raw projection")
