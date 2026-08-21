from __future__ import annotations

from .gateway import GovernedAiGatewayContextAdapter
from .governance import OosReceiptAdapter, WgcfReceiptAdapter
from .operator import OperatorPacketAdapter


def build_default_adapter_registry() -> dict[str, object]:
    return {
        "governance": {
            "wgcf": WgcfReceiptAdapter(),
            "oos": OosReceiptAdapter(),
        },
        "context_consumers": {
            "governed_ai_gateway": GovernedAiGatewayContextAdapter(),
            "operator": OperatorPacketAdapter(),
        },
        "authority": {
            "mutation_authority": "none",
            "model_gateway_authority": "none",
        },
    }
