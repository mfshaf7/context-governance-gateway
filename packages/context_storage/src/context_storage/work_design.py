from pathlib import Path

from .projection import LocalContextProjectionStore


class LocalWorkDesignProjectionStore(LocalContextProjectionStore):
    """Durable local replay records for Work Design context projections."""

    def __init__(self, root: Path) -> None:
        super().__init__(
            root,
            namespace="work-design",
            route_base="/v1/context/work-design/projections",
        )
