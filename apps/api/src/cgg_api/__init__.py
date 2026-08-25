"""API and service-mode contracts for Context Governance Gateway."""

from .runtime import RuntimeSettings
from .service import ContextGatewayService, RuntimeGateError
from .refinement import (
    RefinementContextProjector,
    RefinementProjectionError,
    RefinementProjectionRequest,
)
from .work_design import (
    WorkDesignContextProjector,
    WorkDesignProjectionError,
    WorkDesignProjectionRequest,
)

__all__ = [
    "ContextGatewayService",
    "RefinementContextProjector",
    "RefinementProjectionError",
    "RefinementProjectionRequest",
    "RuntimeGateError",
    "RuntimeSettings",
    "WorkDesignContextProjector",
    "WorkDesignProjectionError",
    "WorkDesignProjectionRequest",
]
