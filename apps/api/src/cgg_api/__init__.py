"""API and service-mode contracts for Context Governance Gateway."""

from .runtime import RuntimeSettings
from .service import ContextGatewayService, RuntimeGateError

__all__ = ["ContextGatewayService", "RuntimeGateError", "RuntimeSettings"]
