from __future__ import annotations

from dataclasses import dataclass

from context_core.pipeline import ContextPipeline
from context_core.profiles import PROFILE_NAMES
from context_observability import (
    AdmissionObservation,
    build_dashboard_snapshot,
    build_prometheus_metrics,
    build_trace_spans,
    render_dashboard_text,
    render_prometheus,
)

from .runtime import RuntimeSettings
from .work_design import WorkDesignContextProjector, WorkDesignProjectionRequest


class RuntimeGateError(PermissionError):
    """Raised when service-mode mutation is attempted before active admission."""


@dataclass
class ContextGatewayService:
    settings: RuntimeSettings

    def __post_init__(self) -> None:
        self.pipeline = ContextPipeline(self.settings.root)
        self.metadata_store = self.settings.storage.metadata_store(self.settings.root)
        self.artifact_custody = self.settings.storage.artifact_custody(self.settings.root)
        self.work_design_projector = WorkDesignContextProjector(
            store=self.settings.storage.work_design_projection_store(self.settings.root),
            project_text=self.project_text,
            load_packet=self.packet,
            load_receipt=self.receipt,
            allowed_callers=self.settings.work_design_allowed_callers,
            caller_shared_secret=self.settings.work_design_caller_shared_secret,
            max_context_bytes=self.settings.work_design_max_context_bytes,
            max_budget_tokens=self.settings.work_design_max_budget_tokens,
            max_request_age_seconds=self.settings.work_design_max_request_age_seconds,
            pending_timeout_seconds=self.settings.work_design_pending_timeout_seconds,
        )

    def health(self) -> dict[str, object]:
        return {
            "service": "context-governance-gateway",
            "status": "ok",
            "runtime_profile_state": self.settings.runtime_profile_state,
            "metadata_backend": self.metadata_store.backend,
            "artifact_backend": self.artifact_custody.backend,
            "capabilities": {
                "work_design_projection": {
                    "auth_configured": self.settings.work_design_projection_auth_configured,
                    "model_invocation": False,
                    "delivery_mutation": False,
                }
            },
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
            "capabilities": {
                "work_design_projection": {
                    "ready": bool(
                        self.settings.mutation_allowed
                        and self.settings.work_design_projection_auth_configured
                    )
                }
            },
        }

    def project_text(
        self,
        text: str,
        *,
        source_label: str,
        profile_name: str | None = None,
        budget_tokens: int | None = None,
        source_type: str = "api-text",
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
            source_type=source_type,
        )
        result["storage_record"] = self.metadata_store.record_projection(result)
        return result

    def packet(self, artifact_id: str) -> dict[str, object]:
        return self.metadata_store.get_packet(artifact_id)

    def receipt(self, artifact_id: str) -> dict[str, object]:
        return self.metadata_store.get_receipt(artifact_id)

    def manifest(self, artifact_id: str) -> dict[str, object]:
        return self.metadata_store.get_manifest(artifact_id)

    def project_work_design(
        self,
        request: WorkDesignProjectionRequest,
        *,
        caller_id: str,
        caller_secret: str,
    ) -> dict[str, object]:
        self._require_mutation_allowed()
        return self.work_design_projector.project(
            request,
            caller_id=caller_id,
            caller_secret=caller_secret,
        )

    def work_design_projection(
        self,
        idempotency_key: str,
        *,
        caller_id: str,
        caller_secret: str,
    ) -> dict[str, object]:
        return self.work_design_projector.read(
            idempotency_key,
            caller_id=caller_id,
            caller_secret=caller_secret,
        )

    def admission_observations(self) -> list[dict[str, object]]:
        return [observation.to_dict() for observation in self._admission_observations()]

    def prometheus_metrics(self) -> str:
        return render_prometheus(build_prometheus_metrics(self._admission_observations()))

    def trace_spans(self) -> dict[str, object]:
        spans = build_trace_spans(self._admission_observations())
        return {
            "schema_version": 1,
            "purpose": "otel-compatible-context-admission-spans",
            "otel_exporter": "seam_not_configured",
            "spans": [span.to_dict() for span in spans],
        }

    def operator_dashboard(self) -> dict[str, object]:
        return build_dashboard_snapshot(self._admission_observations())

    def operator_dashboard_text(self) -> str:
        return render_dashboard_text(self.operator_dashboard())

    def _require_mutation_allowed(self) -> None:
        if not self.settings.mutation_allowed:
            raise RuntimeGateError(
                "CGG service-mode mutation is denied until the dev-integration profile is active."
            )

    def _admission_observations(self) -> list[AdmissionObservation]:
        if not hasattr(self.metadata_store, "list_artifact_ids"):
            return []

        observations: list[AdmissionObservation] = []
        for artifact_id in self.metadata_store.list_artifact_ids():
            packet = self.metadata_store.get_packet(artifact_id)
            try:
                manifest = self.metadata_store.get_manifest(artifact_id)
            except FileNotFoundError:
                manifest = None
            try:
                receipt = self.metadata_store.get_receipt(artifact_id)
            except FileNotFoundError:
                receipt = None
            try:
                redaction_report = self.metadata_store.get_redaction_report(artifact_id)
            except (AttributeError, FileNotFoundError):
                redaction_report = None
            observations.append(
                AdmissionObservation.from_artifacts(
                    manifest=manifest,
                    packet=packet,
                    receipt=receipt,
                    redaction_report=redaction_report,
                )
            )
        return observations
