"""API and service-mode contracts for Context Governance Gateway."""

from .runtime import RuntimeSettings
from .service import ContextGatewayService, RuntimeGateError
from .work_design import (
    WorkDesignContextProjector,
    WorkDesignProjectionError,
    WorkDesignProjectionRequest,
)

__all__ = [
    "ContextGatewayService",
    "RuntimeGateError",
    "RuntimeSettings",
    "WorkDesignContextProjector",
    "WorkDesignProjectionError",
    "WorkDesignProjectionRequest",
]
