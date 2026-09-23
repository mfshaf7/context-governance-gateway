"""API and service-mode contracts for Context Governance Gateway."""

from .runtime import RuntimeSettings
from .lifecycle import (
    LifecycleContextProjectionRequest,
    LifecycleContextProjector,
    LifecycleContextSource,
    LifecycleProjectionError,
    canonical_sources_digest,
)
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
    "LifecycleContextProjectionRequest",
    "LifecycleContextProjector",
    "LifecycleContextSource",
    "LifecycleProjectionError",
    "RefinementContextProjector",
    "RefinementProjectionError",
    "RefinementProjectionRequest",
    "RuntimeGateError",
    "RuntimeSettings",
    "WorkDesignContextProjector",
    "WorkDesignProjectionError",
    "WorkDesignProjectionRequest",
    "canonical_sources_digest",
]
