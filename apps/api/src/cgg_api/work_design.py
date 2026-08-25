from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from context_storage import LocalWorkDesignProjectionStore

from .projection import ReceiptBoundContextProjector


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
                    "context_projection_invalid",
                    f"{name} must be present and at most {limit} characters",
                )
        if self.task_kind not in WORK_DESIGN_TASK_KINDS:
            raise WorkDesignProjectionError(
                "context_projection_invalid", "task_kind is not admitted for Work Design"
            )
        if self.task_contract_ref != WORK_DESIGN_TASK_CONTRACT:
            raise WorkDesignProjectionError(
                "context_projection_invalid",
                "task_contract_ref does not match the admitted contract",
            )
        if self.task_version != WORK_DESIGN_TASK_VERSION:
            raise WorkDesignProjectionError(
                "context_projection_invalid", "task_version does not match the admitted contract"
            )
        if self.model_profile_id != WORK_DESIGN_MODEL_PROFILE:
            raise WorkDesignProjectionError(
                "context_projection_invalid",
                "model_profile_id does not match the admitted logical profile",
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
            {"binding": self.binding(caller_id), "work_design_context": context}
        )

    def request_digest(self, caller_id: str) -> str:
        return _digest_text(self.canonical_projection_text(caller_id))


class WorkDesignContextProjector(ReceiptBoundContextProjector):
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
        super().__init__(
            store=store,
            project_text=project_text,
            load_packet=load_packet,
            load_receipt=load_receipt,
            allowed_callers=allowed_callers,
            caller_shared_secret=caller_shared_secret,
            max_context_bytes=max_context_bytes,
            max_budget_tokens=max_budget_tokens,
            max_request_age_seconds=max_request_age_seconds,
            pending_timeout_seconds=pending_timeout_seconds,
            surface_name="Work Design",
            source_label="work-design",
            source_type="work-design-assist",
            error_type=WorkDesignProjectionError,
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
