from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from context_storage import LocalLifecycleProjectionStore

from .projection import ProjectionRequest, ReceiptBoundContextProjector


LIFECYCLE_SOURCE_CLASSES = frozenset({"art", "repository", "runtime", "validation"})
LIFECYCLE_OPERATIONS = frozenset(
    {"close", "continue", "history", "inspect", "merge", "reconstruct", "recover", "start"}
)
LIFECYCLE_SOURCE_AVAILABILITY = frozenset({"available", "unavailable"})
LIFECYCLE_UNAVAILABLE_REASONS = frozenset(
    {"expired", "not_configured", "not_found", "unauthorized", "unreachable", "unsupported"}
)
LIFECYCLE_FAILURE_CODES = frozenset(
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
_PROTOTYPE_ID = re.compile(r"^prototype:[a-z0-9][a-z0-9-]+$")
_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SOURCE_REF = re.compile(r"^repo://[a-z0-9][a-z0-9._-]*(?:/[A-Za-z0-9._-]+)*$")


class LifecycleProjectionError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        if code not in LIFECYCLE_FAILURE_CODES:
            raise ValueError(f"unregistered lifecycle projection failure code: {code}")
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
class LifecycleContextSource:
    source_id: str
    source_class: str
    source_ref: str
    source_revision: str | None
    captured_at: str
    availability: str
    content: str | None
    content_digest: str | None
    unavailable_reason: str | None

    def validate_shape(self) -> None:
        if not _STABLE_ID.fullmatch(self.source_id):
            raise _invalid("source_id must be a stable identifier")
        if self.source_class not in LIFECYCLE_SOURCE_CLASSES:
            raise _invalid("source_class is not admitted for lifecycle projection")
        if not self.source_ref or len(self.source_ref) > 1_024:
            raise _invalid("source_ref must be present and at most 1024 characters")
        if self.source_revision is not None and (
            not self.source_revision or len(self.source_revision) > 256
        ):
            raise _invalid("source_revision must be non-empty and at most 256 characters")
        _parse_timestamp(self.captured_at, field_name="sources[].captured_at")
        if self.availability not in LIFECYCLE_SOURCE_AVAILABILITY:
            raise _invalid("source availability is invalid")

        if self.availability == "available":
            if self.source_revision is None:
                raise _invalid("available sources require source_revision")
            if self.content is None or not self.content or len(self.content) > 131_072:
                raise _invalid("available sources require bounded non-empty content")
            if self.content_digest is None or not _SHA256.fullmatch(self.content_digest):
                raise _invalid("available sources require a sha256 content_digest")
            if self.content_digest != _digest_text(self.content):
                raise _invalid("source content_digest does not match content")
            if self.unavailable_reason is not None:
                raise _invalid("available sources cannot carry unavailable_reason")
            return

        if self.content is not None or self.content_digest is not None:
            raise _invalid("unavailable sources cannot carry content or content_digest")
        if self.unavailable_reason not in LIFECYCLE_UNAVAILABLE_REASONS:
            raise _invalid("unavailable sources require a bounded unavailable_reason")

    def canonical_value(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_class": self.source_class,
            "source_ref": self.source_ref,
            "source_revision": self.source_revision,
            "captured_at": self.captured_at,
            "availability": self.availability,
            "content": self.content,
            "content_digest": self.content_digest,
            "unavailable_reason": self.unavailable_reason,
        }

    def safe_binding(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_class": self.source_class,
            "source_ref": self.source_ref,
            "source_revision": self.source_revision,
            "captured_at": self.captured_at,
            "availability": self.availability,
            "content_digest": self.content_digest,
            "unavailable_reason": self.unavailable_reason,
        }


@dataclass(frozen=True)
class PrototypeLifecycleSubject:
    """An identity binding, not registry readback or source-action authority."""

    prototype_id: str
    registry_ref: str
    registry_revision: str
    source_ref: str
    source_revision: str
    kind: str = "prototype"

    def validate_shape(self) -> None:
        if (
            self.kind != "prototype"
            or not isinstance(self.prototype_id, str)
            or len(self.prototype_id) > 256
            or not _PROTOTYPE_ID.fullmatch(self.prototype_id)
        ):
            raise _invalid("subject must identify a Prototype")
        slug = self.prototype_id.removeprefix("prototype:")
        if self.registry_ref != f"record://prototypes/{slug}":
            raise _invalid("subject registry_ref must identify the same Prototype")
        for revision in (self.registry_revision, self.source_revision):
            if not isinstance(revision, str) or not _GIT_REVISION.fullmatch(revision):
                raise _invalid("subject revisions must be exact Git commits")
        if (
            not isinstance(self.source_ref, str)
            or len(self.source_ref) > 1_024
            or not _SOURCE_REF.fullmatch(self.source_ref)
            or any(part in {".", ".."} for part in self.source_ref[7:].split("/"))
        ):
            raise _invalid("subject source_ref must be a bounded repository reference")

    def binding(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "prototype_id": self.prototype_id,
            "registry_ref": self.registry_ref,
            "registry_revision": self.registry_revision,
            "source_ref": self.source_ref,
            "source_revision": self.source_revision,
        }


@dataclass(frozen=True)
class LifecycleContextProjectionRequest:
    request_id: str
    correlation_id: str
    idempotency_key: str
    workflow_session_id: str
    execution_id: str
    delivery_id: str | None
    work_item_ref: str | None
    landing_unit_id: str
    operator_id: str
    operation: str
    lifecycle_state: str
    next_action: str | None
    requested_at: str
    sources: tuple[LifecycleContextSource, ...]
    sources_digest: str
    budget_tokens: int
    subject: PrototypeLifecycleSubject | None = None

    @property
    def source_scope(self) -> str:
        if self.subject is not None:
            return self.subject.prototype_id
        return self.delivery_id

    @property
    def package_ref(self) -> str:
        if self.subject is not None:
            return self.subject.registry_ref
        return self.work_item_ref

    @property
    def context(self) -> str:
        return _canonical_json({"sources": [source.canonical_value() for source in self.sources]})

    @property
    def context_digest(self) -> str:
        return self.sources_digest

    def validate_shape(self) -> None:
        for name, value in {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "workflow_session_id": self.workflow_session_id,
            "execution_id": self.execution_id,
            "landing_unit_id": self.landing_unit_id,
            "operator_id": self.operator_id,
            "lifecycle_state": self.lifecycle_state,
        }.items():
            if not _STABLE_ID.fullmatch(value):
                raise _invalid(f"{name} must be a stable identifier")
        if self.subject is not None:
            if not isinstance(self.subject, PrototypeLifecycleSubject):
                raise _invalid("subject must use the Prototype identity contract")
            self.subject.validate_shape()
            if self.delivery_id is not None or self.work_item_ref is not None:
                raise _invalid("Prototype context cannot claim a Delivery identity")
        else:
            if not isinstance(self.delivery_id, str) or not _DELIVERY_ID.fullmatch(self.delivery_id):
                raise _invalid("delivery_id must use the delivery-<number> form")
            if (
                not isinstance(self.work_item_ref, str)
                or not self.work_item_ref
                or len(self.work_item_ref) > 512
            ):
                raise _invalid("work_item_ref must be present and at most 512 characters")
        if self.operation not in LIFECYCLE_OPERATIONS:
            raise _invalid("operation is not admitted for lifecycle projection")
        if self.next_action is not None and not _STABLE_ID.fullmatch(self.next_action):
            raise _invalid("next_action must be a stable identifier when present")
        requested_at = _parse_timestamp(self.requested_at, field_name="requested_at")
        if not 1 <= len(self.sources) <= 16:
            raise _invalid("sources must contain between 1 and 16 entries")
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise _invalid("source_id values must be unique")
        for source in self.sources:
            source.validate_shape()
            captured_at = _parse_timestamp(
                source.captured_at, field_name="sources[].captured_at"
            )
            if captured_at > requested_at:
                raise _invalid("source captured_at cannot be later than requested_at")
        if not _SHA256.fullmatch(self.sources_digest):
            raise _invalid("sources_digest must be a sha256 digest")
        expected_digest = _digest_text(
            _canonical_json([source.canonical_value() for source in self.sources])
        )
        if self.sources_digest != expected_digest:
            raise _invalid("sources_digest does not match the canonical source list")
        if self.budget_tokens < 1:
            raise _invalid("budget_tokens must be positive")

    def binding(self, caller_id: str) -> dict[str, object]:
        binding = {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "workflow_session_id": self.workflow_session_id,
            "execution_id": self.execution_id,
            "delivery_id": self.delivery_id,
            "work_item_ref": self.work_item_ref,
            "landing_unit_id": self.landing_unit_id,
            "caller_id": caller_id,
            "operator_id": self.operator_id,
            "lifecycle": {
                "operation": self.operation,
                "state": self.lifecycle_state,
                "next_action": self.next_action,
            },
            "requested_at": self.requested_at,
            "sources_digest": self.sources_digest,
            "budget_tokens": self.budget_tokens,
        }
        if self.subject is not None:
            del binding["delivery_id"]
            del binding["work_item_ref"]
            binding["subject"] = self.subject.binding()
        return binding

    def canonical_projection_text(self, caller_id: str) -> str:
        return _canonical_json(
            {
                "binding": self.binding(caller_id),
                "lifecycle_sources": [source.canonical_value() for source in self.sources],
            }
        )

    def request_digest(self, caller_id: str) -> str:
        return _digest_text(self.canonical_projection_text(caller_id))


class LifecycleContextProjector(ReceiptBoundContextProjector):
    def __init__(
        self,
        *,
        store: LocalLifecycleProjectionStore,
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
            surface_name="lifecycle context",
            source_label="lifecycle",
            source_type="lifecycle-context",
            error_type=LifecycleProjectionError,
        )

    def _response_fields(
        self,
        *,
        request: ProjectionRequest,
        caller_id: str,
        packet: dict[str, object],
        receipt: dict[str, object],
    ) -> dict[str, object]:
        if not isinstance(request, LifecycleContextProjectionRequest):
            raise LifecycleProjectionError(
                "context_projection_failed",
                "lifecycle projector received an unsupported request type",
                retryable=True,
            )
        budget = dict(packet.get("budget") or {})
        redactions = packet.get("redactions_applied")
        source_bindings = [source.safe_binding() for source in request.sources]
        available = sum(source.availability == "available" for source in request.sources)
        unavailable = len(request.sources) - available
        return {
            "lifecycle_context": {
                "operation": request.operation,
                "state": request.lifecycle_state,
                "next_action": request.next_action,
            },
            "source_bindings": source_bindings,
            "source_summary": {
                "total": len(request.sources),
                "available": available,
                "unavailable": unavailable,
                "classes": sorted({source.source_class for source in request.sources}),
            },
            "classification": {
                "context_type": "lifecycle",
                "source_classes": sorted(
                    {source.source_class for source in request.sources}
                ),
                "signal_ids": list(packet.get("key_relevant_signals") or []),
            },
            "budget": {
                "requested_tokens": budget.get("requested_tokens"),
                "estimated_tokens": budget.get("estimated_tokens"),
                "truncated": budget.get("truncated"),
            },
            "projection_safety": {
                "raw_context_exposed": False,
                "redaction_applied": bool(redactions),
                "custody_bound": bool(receipt.get("artifact_digest")),
            },
            "lifecycle_authority": {
                "may_choose_action": False,
                "may_mutate_art": False,
                "may_mutate_source": False,
                "may_invoke_model": False,
                "may_choose_raw_fallback": False,
            },
        }


def canonical_sources_digest(sources: tuple[LifecycleContextSource, ...]) -> str:
    return _digest_text(_canonical_json([source.canonical_value() for source in sources]))


def _invalid(message: str) -> LifecycleProjectionError:
    return LifecycleProjectionError("context_projection_invalid", message)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _digest_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _parse_timestamp(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise _invalid(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)
