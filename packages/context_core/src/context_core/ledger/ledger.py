from __future__ import annotations

import json
from pathlib import Path


def append_ledger_event(ledger_path: Path, event: dict[str, object]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
