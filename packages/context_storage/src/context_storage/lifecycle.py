from pathlib import Path

from .projection import LocalContextProjectionStore


class LocalLifecycleProjectionStore(LocalContextProjectionStore):
    """Durable local replay records for typed lifecycle context projections."""

    def __init__(self, root: Path) -> None:
        super().__init__(
            root,
            namespace="lifecycle",
            route_base="/v1/context/lifecycle/projections",
        )
