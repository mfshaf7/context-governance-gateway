from __future__ import annotations

from dataclasses import dataclass

from context_core.pipeline import ContextPipeline
from context_core.profiles import PROFILE_NAMES

from .runtime import RuntimeSettings


class RuntimeGateError(PermissionError):
    """Raised when service-mode mutation is attempted before active admission."""


@dataclass
class ContextGatewayService:
    settings: RuntimeSettings

    def __post_init__(self) -> None:
        self.pipeline = ContextPipeline(self.settings.root)
        self.metadata_store = self.settings.storage.metadata_store(self.settings.root)
        self.artifact_custody = self.settings.storage.artifact_custody(self.settings.root)

    def health(self) -> dict[str, object]:
        return {
            "service": "context-governance-gateway",
            "status": "ok",
            "runtime_profile_state": self.settings.runtime_profile_state,
            "metadata_backend": self.metadata_store.backend,
            "artifact_backend": self.artifact_custody.backend,
        }

    def readiness(self) -> dict[str, object]:
        return {
            "ready": self.settings.mutation_allowed,
            "runtime_profile_state": self.settings.runtime_profile_state,
            "reason": (
                "profile is active"
                if self.settings.mutation_allowed
                else "profile is build-admitted for implementation but not active for runtime mutation"
            ),
        }

    def project_text(
        self,
        text: str,
        *,
        source_label: str,
        profile_name: str | None = None,
        budget_tokens: int | None = None,
    ) -> dict[str, object]:
        self._require_mutation_allowed()
        profile = profile_name or self.settings.default_profile
        if profile not in PROFILE_NAMES:
            raise ValueError(f"unknown CGG profile: {profile}")
        result = self.pipeline.project_text(
            text,
            source_label=source_label,
            profile_name=profile,
            budget_tokens=budget_tokens or self.settings.default_budget_tokens,
        )
        result["storage_record"] = self.metadata_store.record_projection(result)
        return result

    def packet(self, artifact_id: str) -> dict[str, object]:
        return self.metadata_store.get_packet(artifact_id)

    def receipt(self, artifact_id: str) -> dict[str, object]:
        return self.metadata_store.get_receipt(artifact_id)

    def manifest(self, artifact_id: str) -> dict[str, object]:
        return self.metadata_store.get_manifest(artifact_id)

    def _require_mutation_allowed(self) -> None:
        if not self.settings.mutation_allowed:
            raise RuntimeGateError(
                "CGG service-mode mutation is denied until the dev-integration profile is active."
            )
