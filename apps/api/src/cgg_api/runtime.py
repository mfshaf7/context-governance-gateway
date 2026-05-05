from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from context_storage import StorageSettings


@dataclass(frozen=True)
class RuntimeSettings:
    root: Path
    runtime_profile_state: str = "build-admitted"
    default_profile: str = "developer"
    default_budget_tokens: int = 2000
    storage: StorageSettings = StorageSettings()

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        root = Path(os.environ.get("CGG_ROOT", ".")).resolve()
        state = os.environ.get("CGG_RUNTIME_PROFILE_STATE", "build-admitted").strip() or "build-admitted"
        profile = os.environ.get("CGG_DEFAULT_PROFILE", "developer").strip() or "developer"
        raw_budget = os.environ.get("CGG_DEFAULT_BUDGET_TOKENS", "2000").strip()
        return cls(
            root=root,
            runtime_profile_state=state,
            default_profile=profile,
            default_budget_tokens=int(raw_budget),
            storage=StorageSettings.from_env(),
        )

    @property
    def mutation_allowed(self) -> bool:
        return self.runtime_profile_state == "active"
