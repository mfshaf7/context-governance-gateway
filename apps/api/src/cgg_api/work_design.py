from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from context_storage import LocalWorkDesignProjectionStore

from context_adapters import AdapterPolicyError, GovernedAiGatewayContextAdapter


WORK_DESIGN_TASK_CONTRACT = "oos.delivery-work-design.v1"
WORK_DESIGN_TASK_VERSION = "1.0"
WORK_DESIGN_MODEL_PROFILE = "delivery-work-design-advisor-v1"
WORK_DESIGN_TASK_KINDS = frozenset({"context_advice", "tree_advice"})
WORK_DESIGN_FAILURE_CODES = frozenset(
    {
        "context_projection_failed",
        "context_projection_in_progress",
        "context_projection_invalid",
        "context_projection_oversized",
        "context_projection_replay_conflict",
        "context_projection_stale",
        "context_projection_unauthorized",
        "context_projection_unsafe",
    }
)

_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_DELIVERY_ID = re.compile(r"^delivery-[1-9][0-9]*$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class WorkDesignProjectionError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        if code not in WORK_DESIGN_FAILURE_CODES:
            raise ValueError(f"unregistered Work Design projection failure code: {code}")
        super().__init__(message)
        self.code = code
        self.retryable = retryable

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "status": "denied",
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class WorkDesignProjectionRequest:
    request_id: str
    correlation_id: str
    idempotency_key: str
    workflow_session_id: str
    execution_id: str
    delivery_id: str
    package_ref: str
    source_ref: str
    source_revision: str
    operator_id: str
    task_kind: str
    task_contract_ref: str
    task_version: str
    output_schema_ref: str
    model_profile_id: str
    requested_at: str
    context: str
    context_digest: str
    budget_tokens: int

    def validate_shape(self) -> None:
        for name, value in {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "workflow_session_id": self.workflow_session_id,
            "execution_id": self.execution_id,
            "operator_id": self.operator_id,
        }.items():
            if not _STABLE_ID.fullmatch(value):
                raise WorkDesignProjectionError(
                    "context_projection_invalid", f"{name} must be a stable identifier"
                )
        if not _DELIVERY_ID.fullmatch(self.delivery_id):
            raise WorkDesignProjectionError(
                "context_projection_invalid", "delivery_id must use the delivery-<number> form"
            )
        for name, value, limit in (
            ("package_ref", self.package_ref, 512),
            ("source_ref", self.source_ref, 512),
            ("source_revision", self.source_revision, 256),
            ("output_schema_ref", self.output_schema_ref, 512),
        ):
            if not value or len(value) > limit:
                raise WorkDesignProjectionError(
                    "context_projection_invalid", f"{name} must be present and at most {limit} characters"
                )
        if self.task_kind not in WORK_DESIGN_TASK_KINDS:
            raise WorkDesignProjectionError(
                "context_projection_invalid", "task_kind is not admitted for Work Design"
            )
        if self.task_contract_ref != WORK_DESIGN_TASK_CONTRACT:
            raise WorkDesignProjectionError(
                "context_projection_invalid", "task_contract_ref does not match the admitted contract"
            )
        if self.task_version != WORK_DESIGN_TASK_VERSION:
            raise WorkDesignProjectionError(
                "context_projection_invalid", "task_version does not match the admitted contract"
            )
        if self.model_profile_id != WORK_DESIGN_MODEL_PROFILE:
            raise WorkDesignProjectionError(
                "context_projection_invalid", "model_profile_id does not match the admitted logical profile"
            )
        if not self.context:
            raise WorkDesignProjectionError(
                "context_projection_invalid", "context must not be empty"
            )
        if not _SHA256.fullmatch(self.context_digest):
            raise WorkDesignProjectionError(
                "context_projection_invalid", "context_digest must be a sha256 digest"
            )
        if self.context_digest != _digest_text(self.context):
            raise WorkDesignProjectionError(
                "context_projection_invalid", "context_digest does not match context"
            )
        if self.budget_tokens < 1:
            raise WorkDesignProjectionError(
                "context_projection_invalid", "budget_tokens must be positive"
            )
        _parse_timestamp(self.requested_at)

    def binding(self, caller_id: str) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "workflow_session_id": self.workflow_session_id,
            "execution_id": self.execution_id,
            "delivery_id": self.delivery_id,
            "package_ref": self.package_ref,
            "source_ref": self.source_ref,
            "source_revision": self.source_revision,
            "caller_id": caller_id,
            "operator_id": self.operator_id,
            "task": {
                "kind": self.task_kind,
                "contract_ref": self.task_contract_ref,
                "version": self.task_version,
                "output_schema_ref": self.output_schema_ref,
                "model_profile_id": self.model_profile_id,
            },
            "requested_at": self.requested_at,
            "context_digest": self.context_digest,
            "budget_tokens": self.budget_tokens,
        }

    def canonical_projection_text(self, caller_id: str) -> str:
        try:
            context: object = json.loads(self.context)
        except json.JSONDecodeError:
            context = self.context
        return _canonical_json(
            {
                "binding": self.binding(caller_id),
                "work_design_context": context,
            }
        )

    def request_digest(self, caller_id: str) -> str:
        return _digest_text(self.canonical_projection_text(caller_id))


class WorkDesignContextProjector:
    def __init__(
        self,
        *,
        store: LocalWorkDesignProjectionStore,
        project_text: Callable[..., dict[str, object]],
        load_packet: Callable[[str], dict[str, object]],
        load_receipt: Callable[[str], dict[str, object]],
        allowed_callers: frozenset[str],
        caller_shared_secret: str | None,
        max_context_bytes: int,
        max_budget_tokens: int,
        max_request_age_seconds: int,
        pending_timeout_seconds: int,
    ) -> None:
        self.store = store
        self.project_text = project_text
        self.load_packet = load_packet
        self.load_receipt = load_receipt
        self.allowed_callers = allowed_callers
        self.caller_shared_secret = caller_shared_secret
        self.max_context_bytes = max_context_bytes
        self.max_budget_tokens = max_budget_tokens
        self.max_request_age_seconds = max_request_age_seconds
        self.pending_timeout_seconds = pending_timeout_seconds

    def project(
        self,
        request: WorkDesignProjectionRequest,
        *,
        caller_id: str,
        caller_secret: str,
        now: datetime | None = None,
    ) -> dict[str, object]:
        current = now or datetime.now(timezone.utc)
        try:
            request.validate_shape()
            self._validate_admission(
                request,
                caller_id=caller_id,
                caller_secret=caller_secret,
                now=current,
            )
        except WorkDesignProjectionError as exc:
            self._record_denial(request, caller_id=caller_id, error=exc, now=current)
            raise

        request_digest = request.request_digest(caller_id)
        existing = self.store.read(request.idempotency_key)
        if existing is not None:
            replay = self._resolve_existing(
                existing,
                request=request,
                caller_id=caller_id,
                request_digest=request_digest,
                now=current,
            )
            if replay is not None:
                return replay

        pending = {
            "schema_version": 1,
            "status": "pending",
            "idempotency_key": request.idempotency_key,
            "request_digest": request_digest,
            "binding": request.binding(caller_id),
            "started_at": _format_timestamp(current),
            "attempt": int(existing.get("attempt", 0)) + 1 if existing else 1,
        }
        created = self.store.create(request.idempotency_key, pending) if existing is None else False
        if not created:
            if existing is None:
                race = self.store.read(request.idempotency_key)
                if race is None:
                    raise WorkDesignProjectionError(
                        "context_projection_failed",
                        "projection replay record could not be read after reservation",
                        retryable=True,
                    )
                replay = self._resolve_existing(
                    race,
                    request=request,
                    caller_id=caller_id,
                    request_digest=request_digest,
                    now=current,
                )
                if replay is not None:
                    return replay
                pending["attempt"] = int(race.get("attempt", 0)) + 1
            self.store.replace(request.idempotency_key, pending)

        try:
            result = self.project_text(
                request.canonical_projection_text(caller_id),
                source_label=f"work-design:{request.delivery_id}:{request.package_ref}",
                profile_name="developer",
                budget_tokens=request.budget_tokens,
                source_type="work-design-assist",
            )
            artifact_id = str(result["artifact_id"])
            packet = self.load_packet(artifact_id)
            receipt = self.load_receipt(artifact_id)
            handoff = GovernedAiGatewayContextAdapter().to_model_safe_packet(packet, receipt)
            admission = dict(packet["admission_decision"])
            if not admission.get("redaction_safe") or admission.get("raw_projection") == "allowed-raw":
                raise WorkDesignProjectionError(
                    "context_projection_unsafe",
                    "CGG denied Work Design projection because the admitted packet is not model-safe",
                )
            projected_at = str(packet["captured_at"])
            try:
                projected_time = _parse_timestamp(projected_at)
            except WorkDesignProjectionError as exc:
                raise WorkDesignProjectionError(
                    "context_projection_failed",
                    "CGG projection returned an invalid timeline",
                    retryable=True,
                ) from exc
            if projected_time + timedelta(seconds=1) < _parse_timestamp(request.requested_at):
                raise WorkDesignProjectionError(
                    "context_projection_failed",
                    "CGG projection timeline precedes the bound request",
                    retryable=True,
                )
            completed_at = max(datetime.now(timezone.utc), projected_time)
            response = {
                "schema_version": 1,
                "status": "ready",
                "replayed": False,
                "request_id": request.request_id,
                "correlation_id": request.correlation_id,
                "idempotency_key": request.idempotency_key,
                "request_digest": request_digest,
                "binding": request.binding(caller_id),
                "artifact_id": artifact_id,
                "artifact_digest": str(result["artifact_digest"]),
                "packet_ref": handoff["packet_ref"],
                "redaction_receipt_ref": handoff["redaction_receipt_ref"],
                "projection_receipt_ref": self.store.reference(request.idempotency_key),
                "content": handoff["content"],
                "admission_decision": {
                    "profile": admission.get("profile"),
                    "raw_projection": admission.get("raw_projection"),
                    "redaction_safe": admission.get("redaction_safe"),
                },
                "timeline": {
                    "requested_at": request.requested_at,
                    "projected_at": projected_at,
                },
                "authority": {
                    "may_select_or_invoke_model": False,
                    "may_approve_suggestion": False,
                    "may_mutate_delivery": False,
                },
            }
            self.store.replace(
                request.idempotency_key,
                {
                    **pending,
                    "status": "ready",
                    "completed_at": _format_timestamp(completed_at),
                    "response": response,
                },
            )
            return response
        except WorkDesignProjectionError as error:
            self.store.replace(
                request.idempotency_key,
                {
                    **pending,
                    "status": "failed" if error.retryable else "denied",
                    "failed_at": _format_timestamp(current),
                    "error": error.to_dict(),
                },
            )
            raise
        except (AdapterPolicyError, KeyError, OSError, TypeError, ValueError) as exc:
            error = WorkDesignProjectionError(
                "context_projection_failed",
                "CGG could not produce a complete receipt-bound Work Design projection",
                retryable=True,
            )
            self.store.replace(
                request.idempotency_key,
                {
                    **pending,
                    "status": "failed",
                    "failed_at": _format_timestamp(current),
                    "error": error.to_dict(),
                },
            )
            raise error from exc

    def read(
        self,
        idempotency_key: str,
        *,
        caller_id: str,
        caller_secret: str,
    ) -> dict[str, object]:
        if not _STABLE_ID.fullmatch(idempotency_key):
            raise WorkDesignProjectionError(
                "context_projection_invalid", "idempotency_key must be a stable identifier"
            )
        record = self.store.read(idempotency_key)
        if record is None:
            raise FileNotFoundError(idempotency_key)
        binding = dict(record.get("binding") or {})
        if (
            not self._caller_authorized(caller_id, caller_secret)
            or binding.get("caller_id") != caller_id
        ):
            raise WorkDesignProjectionError(
                "context_projection_unauthorized", "caller cannot read this Work Design projection"
            )
        return record

    def _validate_admission(
        self,
        request: WorkDesignProjectionRequest,
        *,
        caller_id: str,
        caller_secret: str,
        now: datetime,
    ) -> None:
        if not self._caller_authorized(caller_id, caller_secret):
            raise WorkDesignProjectionError(
                "context_projection_unauthorized", "caller is not admitted for Work Design projection"
            )
        context_bytes = len(request.context.encode("utf-8"))
        if context_bytes > self.max_context_bytes or request.budget_tokens > self.max_budget_tokens:
            raise WorkDesignProjectionError(
                "context_projection_oversized", "Work Design context exceeds the admitted projection budget"
            )
        requested_at = _parse_timestamp(request.requested_at)
        age_seconds = (now - requested_at).total_seconds()
        if age_seconds > self.max_request_age_seconds or age_seconds < -30:
            raise WorkDesignProjectionError(
                "context_projection_stale", "Work Design projection request is outside the admitted time window"
            )

    def _caller_authorized(self, caller_id: str, caller_secret: str) -> bool:
        expected = self.caller_shared_secret
        return bool(
            caller_id in self.allowed_callers
            and expected
            and caller_secret
            and hmac.compare_digest(caller_secret, expected)
        )

    def _resolve_existing(
        self,
        existing: dict[str, object],
        *,
        request: WorkDesignProjectionRequest,
        caller_id: str,
        request_digest: str,
        now: datetime,
    ) -> dict[str, object] | None:
        if existing.get("request_digest") != request_digest:
            error = WorkDesignProjectionError(
                "context_projection_replay_conflict",
                "idempotency_key is already bound to different Work Design context",
            )
            self._record_denial(request, caller_id=caller_id, error=error, now=now)
            raise error
        status = existing.get("status")
        if status == "ready" and isinstance(existing.get("response"), dict):
            return {**dict(existing["response"]), "replayed": True}
        if status == "pending":
            started_at = _parse_timestamp(str(existing.get("started_at") or request.requested_at))
            if (now - started_at).total_seconds() <= self.pending_timeout_seconds:
                raise WorkDesignProjectionError(
                    "context_projection_in_progress",
                    "an identical Work Design projection is already in progress",
                    retryable=True,
                )
        if status == "denied" and isinstance(existing.get("error"), dict):
            error = dict(existing["error"])
            raise WorkDesignProjectionError(
                str(error.get("code") or "context_projection_unsafe"),
                str(error.get("message") or "Work Design projection was denied"),
                retryable=bool(error.get("retryable")),
            )
        if status not in {"pending", "failed"}:
            raise WorkDesignProjectionError(
                "context_projection_failed",
                "stored Work Design projection has an unsupported recovery state",
                retryable=True,
            )
        return None

    def _record_denial(
        self,
        request: WorkDesignProjectionRequest,
        *,
        caller_id: str,
        error: WorkDesignProjectionError,
        now: datetime,
    ) -> None:
        binding = {
            "request_id": request.request_id,
            "correlation_id": request.correlation_id,
            "idempotency_key": request.idempotency_key,
            "caller_id": caller_id,
            "context_digest": request.context_digest,
        }
        self.store.record_denial(
            {
                "schema_version": 1,
                "status": "denied",
                "recorded_at": _format_timestamp(now),
                "binding": binding,
                "error": error.to_dict(),
            }
        )


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _digest_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WorkDesignProjectionError(
            "context_projection_invalid", "requested_at must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise WorkDesignProjectionError(
            "context_projection_invalid", "requested_at must include a timezone"
        )
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
