from pathlib import Path

from .projection import LocalContextProjectionStore


class LocalAgentConsoleProjectionStore(LocalContextProjectionStore):
    """Durable local replay records for Agent Console context projections."""

    def __init__(self, root: Path) -> None:
        super().__init__(
            root,
            namespace="agent-console",
            route_base="/v1/context/agent-console/projections",
        )
