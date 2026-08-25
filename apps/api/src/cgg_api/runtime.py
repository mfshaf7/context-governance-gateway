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
    work_design_allowed_callers: frozenset[str] = frozenset({"operator-orchestration-service"})
    work_design_caller_shared_secret: str | None = None
    work_design_max_context_bytes: int = 262_144
    work_design_max_budget_tokens: int = 8_000
    work_design_max_request_age_seconds: int = 300
    work_design_pending_timeout_seconds: int = 120
    storage: StorageSettings = StorageSettings()

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        root = Path(os.environ.get("CGG_ROOT", ".")).resolve()
        state = os.environ.get("CGG_RUNTIME_PROFILE_STATE", "build-admitted").strip() or "build-admitted"
        profile = os.environ.get("CGG_DEFAULT_PROFILE", "developer").strip() or "developer"
        raw_budget = os.environ.get("CGG_DEFAULT_BUDGET_TOKENS", "2000").strip()
        callers = frozenset(
            caller.strip()
            for caller in os.environ.get(
                "CGG_WORK_DESIGN_ALLOWED_CALLERS", "operator-orchestration-service"
            ).split(",")
            if caller.strip()
        )
        return cls(
            root=root,
            runtime_profile_state=state,
            default_profile=profile,
            default_budget_tokens=int(raw_budget),
            work_design_allowed_callers=callers,
            work_design_caller_shared_secret=os.environ.get(
                "CGG_WORK_DESIGN_CALLER_SHARED_SECRET"
            ),
            work_design_max_context_bytes=int(
                os.environ.get("CGG_WORK_DESIGN_MAX_CONTEXT_BYTES", "262144")
            ),
            work_design_max_budget_tokens=int(
                os.environ.get("CGG_WORK_DESIGN_MAX_BUDGET_TOKENS", "8000")
            ),
            work_design_max_request_age_seconds=int(
                os.environ.get("CGG_WORK_DESIGN_MAX_REQUEST_AGE_SECONDS", "300")
            ),
            work_design_pending_timeout_seconds=int(
                os.environ.get("CGG_WORK_DESIGN_PENDING_TIMEOUT_SECONDS", "120")
            ),
            storage=StorageSettings.from_env(),
        )

    @property
    def mutation_allowed(self) -> bool:
        return self.runtime_profile_state == "active"

    @property
    def work_design_projection_auth_configured(self) -> bool:
        return bool(
            self.work_design_allowed_callers and self.work_design_caller_shared_secret
        )
