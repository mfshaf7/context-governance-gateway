from __future__ import annotations

from dataclasses import dataclass

from .models import AdapterEnvelope, PacketReference


@dataclass(frozen=True)
class ModelSafePacketAdapter:
    consumer: str
    provider_family: str

    def to_context_payload(self, packet: dict[str, object]) -> dict[str, object]:
        packet_reference = PacketReference.from_packet(packet)
        return AdapterEnvelope(
            consumer=self.consumer,
            purpose="model-safe-context-input",
            packet_reference=packet_reference,
            payload={
                "provider_family": self.provider_family,
                "model_invocation": "not_performed",
                "gateway_role": "not_a_llm_gateway",
                "messages": [
                    {
                        "role": "system",
                        "content": "Use only the supplied CGG model-safe context. Do not request raw operational context.",
                    },
                    {
                        "role": "user",
                        "content": str(packet["safe_context_excerpt"]),
                    },
                ],
                "metadata": {
                    "artifact_digest": packet_reference.artifact_digest,
                    "policy_profile": packet_reference.policy_profile,
                    "raw_projection": packet_reference.raw_projection,
                },
            },
        ).to_dict()


class LiteLlmPacketAdapter(ModelSafePacketAdapter):
    def __init__(self) -> None:
        super().__init__(consumer="litellm", provider_family="litellm")


class OpenClawPacketAdapter(ModelSafePacketAdapter):
    def __init__(self) -> None:
        super().__init__(consumer="openclaw", provider_family="openclaw")


class OllamaPacketAdapter(ModelSafePacketAdapter):
    def __init__(self) -> None:
        super().__init__(consumer="ollama", provider_family="ollama")


class CodexStylePacketAdapter(ModelSafePacketAdapter):
    def __init__(self) -> None:
        super().__init__(consumer="codex-style-agent", provider_family="codex-style-agent")


class OperatorPacketAdapter(ModelSafePacketAdapter):
    def __init__(self) -> None:
        super().__init__(consumer="human-operator", provider_family="operator-ui")
