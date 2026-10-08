from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from context_storage import LocalAgentConsoleProjectionStore

from .projection import ProjectionRequest, ReceiptBoundContextProjector


AGENT_CONSOLE_INTERACTION_MODES = frozenset({"focused", "workspace"})
AGENT_CONSOLE_SCOPES = frozenset({"page", "workspace"})
AGENT_CONSOLE_SOURCE_MODES = frozenset({"live", "source-projected", "synthetic"})
AGENT_CONSOLE_FAILURE_CODES = frozenset(
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
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class AgentConsoleProjectionError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        if code not in AGENT_CONSOLE_FAILURE_CODES:
            raise ValueError(f"unregistered Agent Console projection failure code: {code}")
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
class AgentConsoleContextCandidate:
    candidate_id: str
    scope: str
    source_authority: str
    source_mode: str
    source_ref: str
    source_revision: str
    captured_at: str
    content: str
    content_digest: str

    def validate_shape(self) -> None:
        for name, value in {
            "candidate_id": self.candidate_id,
            "source_authority": self.source_authority,
        }.items():
            if not _STABLE_ID.fullmatch(value):
                raise _invalid(f"candidate.{name} must be a stable identifier")
        if self.scope not in AGENT_CONSOLE_SCOPES:
            raise _invalid("candidate.scope is not admitted")
        if self.source_mode not in AGENT_CONSOLE_SOURCE_MODES:
            raise _invalid("candidate.source_mode is not admitted")
        if not self.source_ref or len(self.source_ref) > 1_024:
            raise _invalid("candidate.source_ref must be present and bounded")
        if not self.source_revision or len(self.source_revision) > 256:
            raise _invalid("candidate.source_revision must be present and bounded")
        _parse_timestamp(self.captured_at, field_name="candidate.captured_at")
        if not self.content or len(self.content) > 131_072:
            raise _invalid("candidate.content must be present and bounded")
        if not _SHA256.fullmatch(self.content_digest):
            raise _invalid("candidate.content_digest must be a sha256 digest")
        if self.content_digest != _digest_text(self.content):
            raise _invalid("candidate.content_digest does not match content")

    def canonical_value(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "scope": self.scope,
            "source_authority": self.source_authority,
            "source_mode": self.source_mode,
            "source_ref": self.source_ref,
            "source_revision": self.source_revision,
            "captured_at": self.captured_at,
            "content": self.content,
            "content_digest": self.content_digest,
        }

    def safe_binding(self) -> dict[str, object]:
        value = self.canonical_value()
        value.pop("content")
        return value


@dataclass(frozen=True)
class AgentConsoleContextProjectionRequest:
    request_id: str
    correlation_id: str
    idempotency_key: str
    session_id: str
    invocation_id: str
    operator_id: str
    interaction_mode: str
    requested_at: str
    candidate: AgentConsoleContextCandidate
    budget_tokens: int

    @property
    def source_scope(self) -> str:
        return self.session_id

    @property
    def package_ref(self) -> str:
        return self.candidate.source_ref

    @property
    def context(self) -> str:
        return _canonical_json({"candidate": self.candidate.canonical_value()})

    @property
    def context_digest(self) -> str:
        return self.candidate.content_digest

    def validate_shape(self) -> None:
        for name, value in {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "session_id": self.session_id,
            "invocation_id": self.invocation_id,
            "operator_id": self.operator_id,
        }.items():
            if not _STABLE_ID.fullmatch(value):
                raise _invalid(f"{name} must be a stable identifier")
        if self.interaction_mode not in AGENT_CONSOLE_INTERACTION_MODES:
            raise _invalid("interaction_mode must be focused or workspace")
        requested_at = _parse_timestamp(self.requested_at, field_name="requested_at")
        self.candidate.validate_shape()
        captured_at = _parse_timestamp(
            self.candidate.captured_at, field_name="candidate.captured_at"
        )
        if captured_at > requested_at:
            raise _invalid("candidate.captured_at cannot be later than requested_at")
        if self.interaction_mode == "workspace" and self.candidate.scope != "workspace":
            raise _invalid("workspace interaction requires a workspace-scoped candidate")
        if self.budget_tokens < 1:
            raise _invalid("budget_tokens must be positive")

    def binding(self, caller_id: str) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "session_id": self.session_id,
            "invocation_id": self.invocation_id,
            "operator_id": self.operator_id,
            "caller_id": caller_id,
            "interaction_mode": self.interaction_mode,
            "requested_at": self.requested_at,
            "candidate": self.candidate.safe_binding(),
            "budget_tokens": self.budget_tokens,
        }

    def canonical_projection_text(self, caller_id: str) -> str:
        return _canonical_json(
            {
                "binding": self.binding(caller_id),
                "agent_context": self.candidate.canonical_value(),
            }
        )

    def request_digest(self, caller_id: str) -> str:
        return _digest_text(self.canonical_projection_text(caller_id))


class AgentConsoleContextProjector(ReceiptBoundContextProjector):
    def __init__(
        self,
        *,
        store: LocalAgentConsoleProjectionStore,
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
            surface_name="Agent Console context",
            source_label="agent-console",
            source_type="agent-console-context",
            error_type=AgentConsoleProjectionError,
        )

    def _response_fields(
        self,
        *,
        request: ProjectionRequest,
        caller_id: str,
        packet: dict[str, object],
        receipt: dict[str, object],
    ) -> dict[str, object]:
        if not isinstance(request, AgentConsoleContextProjectionRequest):
            raise AgentConsoleProjectionError(
                "context_projection_failed",
                "Agent Console projector received an unsupported request type",
                retryable=True,
            )
        budget = dict(packet.get("budget") or {})
        redactions = packet.get("redactions_applied")
        return {
            "agent_context": {
                "session_id": request.session_id,
                "invocation_id": request.invocation_id,
                "interaction_mode": request.interaction_mode,
                "candidate": request.candidate.safe_binding(),
            },
            "classification": {
                "context_type": "agent-console",
                "scope": request.candidate.scope,
                "source_mode": request.candidate.source_mode,
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
            "agent_context_authority": {
                "may_select_or_invoke_model": False,
                "may_authorize_action": False,
                "may_mutate_owner_state": False,
                "may_choose_raw_fallback": False,
            },
        }


def _invalid(message: str) -> AgentConsoleProjectionError:
    return AgentConsoleProjectionError("context_projection_invalid", message)


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
