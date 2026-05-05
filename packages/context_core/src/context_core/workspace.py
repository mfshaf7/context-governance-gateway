from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


WORKSPACE_DIRS = (
    "artifacts/raw",
    "artifacts/redacted",
    "manifests",
    "packets",
    "receipts",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_artifact_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}-{uuid4().hex[:10]}"


def cgg_workspace(root: Path) -> Path:
    return root / ".cgg"


def ensure_workspace(root: Path) -> dict[str, str]:
    base = cgg_workspace(root)
    for relative in WORKSPACE_DIRS:
        (base / relative).mkdir(parents=True, exist_ok=True)
    ledger = base / "ledger.jsonl"
    ledger.touch(exist_ok=True)
    return {
        "workspace_path": str(base),
        "raw_artifacts": str(base / "artifacts" / "raw"),
        "redacted_artifacts": str(base / "artifacts" / "redacted"),
        "manifests": str(base / "manifests"),
        "packets": str(base / "packets"),
        "receipts": str(base / "receipts"),
        "ledger": str(ledger),
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())
