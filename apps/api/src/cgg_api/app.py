from __future__ import annotations

from typing import Any, Literal

try:
    from fastapi import FastAPI, Header, HTTPException, Request, Response
    from fastapi.exception_handlers import request_validation_exception_handler
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover - exercised only when running without api extras.
    raise RuntimeError(
        "FastAPI API runtime requires the api extra: pip install -e '.[api]'."
    ) from exc

from .runtime import RuntimeSettings
from .service import ContextGatewayService, RuntimeGateError
from .refinement import RefinementProjectionError, RefinementProjectionRequest
from .work_design import WorkDesignProjectionError, WorkDesignProjectionRequest


class TextAdmissionRequest(BaseModel):
    content: str = Field(min_length=1)
    source_label: str = Field(default="api-request", min_length=1)
    profile: str | None = None
    budget_tokens: int | None = Field(default=None, ge=1)


class WorkDesignOperatorBinding(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


class WorkDesignTaskBinding(BaseModel):
    model_config = {"extra": "forbid"}

    kind: Literal["context_advice", "tree_advice"]
    contract_ref: Literal["oos.delivery-work-design.v1"]
    version: Literal["1.0"]
    output_schema_ref: str = Field(min_length=1, max_length=512)
    model_profile_id: Literal["delivery-work-design-advisor-v1"]


class WorkDesignContextProjectionRequest(BaseModel):
    model_config = {"extra": "forbid"}

    schema_version: Literal[1]
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    correlation_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    workflow_session_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    execution_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    delivery_id: str = Field(pattern=r"^delivery-[1-9][0-9]*$")
    package_ref: str = Field(min_length=1, max_length=512)
    source_ref: str = Field(min_length=1, max_length=512)
    source_revision: str = Field(min_length=1, max_length=256)
    operator: WorkDesignOperatorBinding
    task: WorkDesignTaskBinding
    requested_at: str = Field(min_length=1, max_length=64)
    context: str = Field(min_length=1, max_length=262_144)
    context_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    budget_tokens: int = Field(default=4_000, ge=1, le=8_000)


class RefinementOperatorBinding(BaseModel):
    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1, max_length=256)
    handle: str | None = Field(default=None, min_length=1, max_length=256)


class RefinementTaskBinding(BaseModel):
    model_config = {"extra": "forbid"}

    kind: Literal["metadata_advice"]
    contract_ref: Literal["oos.delivery-refinement.v1"]
    version: Literal["1.0"]


class RefinementPacketBinding(BaseModel):
    model_config = {"extra": "forbid"}

    packet_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    packet_revision: str = Field(min_length=1, max_length=256)
    source_work_design_receipt_id: str = Field(min_length=1, max_length=512)


class RefinementTargetBinding(BaseModel):
    model_config = {"extra": "forbid"}

    field_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    field_label: str = Field(min_length=1, max_length=256)
    field_kind: Literal["long_text", "number", "select", "short_text"]
    required: bool
    source_value: str = Field(max_length=64_000)
    draft_value: str = Field(max_length=64_000)
    selected_node_ids: list[str] = Field(min_length=1)
    allowed_values: list[str]


class RefinementAssistRequest(BaseModel):
    model_config = {"extra": "forbid"}

    schema_version: Literal[1]
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    correlation_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    delivery_id: str = Field(pattern=r"^delivery-[1-9][0-9]*$")
    package_ref: str = Field(min_length=1, max_length=512)
    source_ref: str = Field(min_length=1, max_length=512)
    source_revision: str = Field(min_length=1, max_length=256)
    operator: RefinementOperatorBinding
    task: RefinementTaskBinding
    packet: RefinementPacketBinding
    target: RefinementTargetBinding
    operator_prompt: str = Field(min_length=1, max_length=4_000)


class RefinementContextProjectionRequest(BaseModel):
    model_config = {"extra": "forbid"}

    schema_version: Literal[1]
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    workflow_session_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    execution_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    requested_at: str = Field(min_length=1, max_length=64)
    assist_request: RefinementAssistRequest
    assist_request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    budget_tokens: int = Field(default=4_000, ge=1, le=8_000)


def create_app(settings: RuntimeSettings | None = None) -> FastAPI:
    service = ContextGatewayService(settings or RuntimeSettings.from_env())
    app = FastAPI(
        title="Context Governance Gateway",
        version="0.1.0",
        description="Operational Context Governance and Context Admission Control API.",
    )

    @app.exception_handler(RequestValidationError)
    async def bounded_validation_error(
        request: Request, exc: RequestValidationError
    ) -> Response:
        projection_surface = next(
            (
                label
                for prefix, label in (
                    ("/v1/context/work-design/projections", "Work Design"),
                    ("/v1/context/refinement/projections", "Refinement"),
                )
                if request.url.path.startswith(prefix)
            ),
            None,
        )
        if projection_surface:
            oversized = any(
                error.get("type") in {"string_too_long", "less_than_equal"}
                and tuple(error.get("loc") or ())[-1:] in {("context",), ("budget_tokens",)}
                for error in exc.errors()
            )
            code = "context_projection_oversized" if oversized else "context_projection_invalid"
            return JSONResponse(
                status_code=413 if oversized else 422,
                content={
                    "detail": {
                        "schema_version": 1,
                        "status": "denied",
                        "code": code,
                        "message": f"{projection_surface} projection request failed contract validation",
                        "retryable": False,
                    }
                },
            )
        return await request_validation_exception_handler(request, exc)

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

    @app.post("/v1/context/work-design/projections")
    def project_work_design(
        request: WorkDesignContextProjectionRequest,
        caller_id: str = Header(
            alias="x-cgg-caller-id",
            min_length=1,
            max_length=256,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
        ),
        caller_secret: str = Header(
            alias="x-cgg-caller-secret", min_length=1, max_length=1024
        ),
    ) -> dict[str, Any]:
        task = request.task
        projection_request = WorkDesignProjectionRequest(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            workflow_session_id=request.workflow_session_id,
            execution_id=request.execution_id,
            delivery_id=request.delivery_id,
            package_ref=request.package_ref,
            source_ref=request.source_ref,
            source_revision=request.source_revision,
            operator_id=request.operator.id,
            task_kind=task.kind,
            task_contract_ref=task.contract_ref,
            task_version=task.version,
            output_schema_ref=task.output_schema_ref,
            model_profile_id=task.model_profile_id,
            requested_at=request.requested_at,
            context=request.context,
            context_digest=request.context_digest,
            budget_tokens=request.budget_tokens,
        )
        try:
            return service.project_work_design(
                projection_request,
                caller_id=caller_id,
                caller_secret=caller_secret,
            )
        except RuntimeGateError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except WorkDesignProjectionError as exc:
            status_code = {
                "context_projection_unauthorized": 403,
                "context_projection_replay_conflict": 409,
                "context_projection_in_progress": 409,
                "context_projection_oversized": 413,
                "context_projection_failed": 503,
            }.get(exc.code, 400)
            raise HTTPException(status_code=status_code, detail=exc.to_dict()) from exc

    @app.get("/v1/context/work-design/projections/{idempotency_key}")
    def work_design_projection(
        idempotency_key: str,
        caller_id: str = Header(
            alias="x-cgg-caller-id",
            min_length=1,
            max_length=256,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
        ),
        caller_secret: str = Header(
            alias="x-cgg-caller-secret", min_length=1, max_length=1024
        ),
    ) -> dict[str, Any]:
        try:
            return service.work_design_projection(
                idempotency_key,
                caller_id=caller_id,
                caller_secret=caller_secret,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Work Design projection not found") from exc
        except WorkDesignProjectionError as exc:
            raise HTTPException(status_code=403, detail=exc.to_dict()) from exc

    @app.post("/v1/context/refinement/projections")
    def project_refinement(
        request: RefinementContextProjectionRequest,
        caller_id: str = Header(
            alias="x-cgg-caller-id",
            min_length=1,
            max_length=256,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
        ),
        caller_secret: str = Header(
            alias="x-cgg-caller-secret", min_length=1, max_length=1024
        ),
    ) -> dict[str, Any]:
        projection_request = RefinementProjectionRequest(
            idempotency_key=request.idempotency_key,
            workflow_session_id=request.workflow_session_id,
            execution_id=request.execution_id,
            requested_at=request.requested_at,
            assist_request=request.assist_request.model_dump(exclude_none=True),
            assist_request_digest=request.assist_request_digest,
            budget_tokens=request.budget_tokens,
        )
        try:
            return service.project_refinement(
                projection_request,
                caller_id=caller_id,
                caller_secret=caller_secret,
            )
        except RuntimeGateError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RefinementProjectionError as exc:
            status_code = {
                "context_projection_unauthorized": 403,
                "context_projection_replay_conflict": 409,
                "context_projection_in_progress": 409,
                "context_projection_oversized": 413,
                "context_projection_failed": 503,
            }.get(exc.code, 400)
            raise HTTPException(status_code=status_code, detail=exc.to_dict()) from exc

    @app.get("/v1/context/refinement/projections/{idempotency_key}")
    def refinement_projection(
        idempotency_key: str,
        caller_id: str = Header(
            alias="x-cgg-caller-id",
            min_length=1,
            max_length=256,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$",
        ),
        caller_secret: str = Header(
            alias="x-cgg-caller-secret", min_length=1, max_length=1024
        ),
    ) -> dict[str, Any]:
        try:
            return service.refinement_projection(
                idempotency_key,
                caller_id=caller_id,
                caller_secret=caller_secret,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Refinement projection not found") from exc
        except RefinementProjectionError as exc:
            raise HTTPException(status_code=403, detail=exc.to_dict()) from exc

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
