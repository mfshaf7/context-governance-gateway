from __future__ import annotations

from .ai import (
    CodexStylePacketAdapter,
    LiteLlmPacketAdapter,
    OllamaPacketAdapter,
    OpenClawPacketAdapter,
    OperatorPacketAdapter,
)
from .governance import OosReceiptAdapter, WgcfReceiptAdapter


def build_default_adapter_registry() -> dict[str, object]:
    return {
        "governance": {
            "wgcf": WgcfReceiptAdapter(),
            "oos": OosReceiptAdapter(),
        },
        "ai_operator": {
            "litellm": LiteLlmPacketAdapter(),
            "openclaw": OpenClawPacketAdapter(),
            "ollama": OllamaPacketAdapter(),
            "codex_style_agent": CodexStylePacketAdapter(),
            "operator": OperatorPacketAdapter(),
        },
        "authority": {
            "mutation_authority": "none",
            "model_gateway_authority": "none",
        },
    }
