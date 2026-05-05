from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from context_core.workspace import cgg_workspace, ensure_workspace


def write_heartbeat(root: Path, *, iteration: int) -> Path:
    workspace = cgg_workspace(root)
    ensure_workspace(root)
    heartbeat_path = workspace / "worker-heartbeat.json"
    heartbeat_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "component": "context-governance-gateway-worker",
                "status": "running",
                "iteration": iteration,
                "runtime_profile_state": os.environ.get("CGG_RUNTIME_PROFILE_STATE", "build-admitted"),
                "updated_at": datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return heartbeat_path


def main() -> int:
    root = Path(os.environ.get("CGG_ROOT", ".")).resolve()
    interval = int(os.environ.get("CGG_WORKER_HEARTBEAT_SECONDS", "30"))
    iteration = 0
    while True:
        iteration += 1
        write_heartbeat(root, iteration=iteration)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
