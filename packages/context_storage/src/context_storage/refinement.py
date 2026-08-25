from pathlib import Path

from .projection import LocalContextProjectionStore


class LocalRefinementProjectionStore(LocalContextProjectionStore):
    """Durable local replay records for Refinement context projections."""

    def __init__(self, root: Path) -> None:
        super().__init__(
            root,
            namespace="refinement",
            route_base="/v1/context/refinement/projections",
        )
