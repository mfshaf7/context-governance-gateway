from __future__ import annotations

from typing import Any

try:
    from fastapi import FastAPI, HTTPException, Response
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover - exercised only when running without api extras.
    raise RuntimeError(
        "FastAPI API runtime requires the api extra: pip install -e '.[api]'."
    ) from exc

from .runtime import RuntimeSettings
from .service import ContextGatewayService, RuntimeGateError


class TextAdmissionRequest(BaseModel):
    content: str = Field(min_length=1)
    source_label: str = Field(default="api-request", min_length=1)
    profile: str | None = None
    budget_tokens: int | None = Field(default=None, ge=1)


def create_app(settings: RuntimeSettings | None = None) -> FastAPI:
    service = ContextGatewayService(settings or RuntimeSettings.from_env())
    app = FastAPI(
        title="Context Governance Gateway",
        version="0.1.0",
        description="Operational Context Governance and Context Admission Control API.",
    )

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return service.health()

    @app.get("/readyz")
    def readyz() -> dict[str, Any]:
        readiness = service.readiness()
        if not readiness["ready"]:
            raise HTTPException(status_code=503, detail=readiness)
        return readiness

    @app.post("/v1/context/admissions")
    def admit_text(request: TextAdmissionRequest) -> dict[str, Any]:
        try:
            return service.project_text(
                request.content,
                source_label=request.source_label,
                profile_name=request.profile,
                budget_tokens=request.budget_tokens,
            )
        except RuntimeGateError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/context/packets/{artifact_id}")
    def packet(artifact_id: str) -> dict[str, Any]:
        try:
            return service.packet(artifact_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="packet not found") from exc

    @app.get("/v1/context/receipts/{artifact_id}")
    def receipt(artifact_id: str) -> dict[str, Any]:
        try:
            return service.receipt(artifact_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="receipt not found") from exc

    @app.get("/v1/context/manifests/{artifact_id}")
    def manifest(artifact_id: str) -> dict[str, Any]:
        try:
            return service.manifest(artifact_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="manifest not found") from exc

    @app.get("/v1/observability/admissions")
    def admission_observations() -> dict[str, Any]:
        return {
            "schema_version": 1,
            "observations": service.admission_observations(),
        }

    @app.get("/v1/observability/metrics")
    def prometheus_metrics() -> Response:
        return Response(
            service.prometheus_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get("/v1/observability/traces")
    def trace_spans() -> dict[str, Any]:
        return service.trace_spans()

    @app.get("/v1/operator/dashboard")
    def operator_dashboard() -> dict[str, Any]:
        return service.operator_dashboard()

    @app.get("/v1/operator/dashboard.txt")
    def operator_dashboard_text() -> Response:
        return Response(service.operator_dashboard_text(), media_type="text/plain; charset=utf-8")

    return app


app = create_app()
