from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from context_adapters import AdapterPolicyError, GovernedAiGatewayContextAdapter
from context_storage import LocalContextProjectionStore


class ProjectionRequest(Protocol):
    request_id: str
    correlation_id: str
    idempotency_key: str
    delivery_id: str
    package_ref: str
    requested_at: str
    context: str
    context_digest: str
    budget_tokens: int

    def validate_shape(self) -> None: ...

    def binding(self, caller_id: str) -> dict[str, object]: ...

    def canonical_projection_text(self, caller_id: str) -> str: ...

    def request_digest(self, caller_id: str) -> str: ...


class ProjectionError(Protocol):
    code: str
    retryable: bool

    def to_dict(self) -> dict[str, object]: ...


class ReceiptBoundContextProjector:
    """Shared replay, custody, and admission mechanics for bounded projections."""

    def __init__(
        self,
        *,
        store: LocalContextProjectionStore,
        project_text: Callable[..., dict[str, object]],
        load_packet: Callable[[str], dict[str, object]],
        load_receipt: Callable[[str], dict[str, object]],
        allowed_callers: frozenset[str],
        caller_shared_secret: str | None,
        max_context_bytes: int,
        max_budget_tokens: int,
        max_request_age_seconds: int,
        pending_timeout_seconds: int,
        surface_name: str,
        source_label: str,
        source_type: str,
        error_type: type[Exception],
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
        self.surface_name = surface_name
        self.source_label = source_label
        self.source_type = source_type
        self.error_type = error_type

    def project(
        self,
        request: ProjectionRequest,
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
        except self.error_type as exc:
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
                    raise self._error(
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
                source_label=f"{self.source_label}:{request.delivery_id}:{request.package_ref}",
                profile_name="developer",
                budget_tokens=request.budget_tokens,
                source_type=self.source_type,
            )
            artifact_id = str(result["artifact_id"])
            packet = self.load_packet(artifact_id)
            receipt = self.load_receipt(artifact_id)
            handoff = GovernedAiGatewayContextAdapter().to_model_safe_packet(packet, receipt)
            admission = dict(packet["admission_decision"])
            if not admission.get("redaction_safe") or admission.get("raw_projection") == "allowed-raw":
                raise self._error(
                    "context_projection_unsafe",
                    f"CGG denied {self.surface_name} projection because the admitted packet is not model-safe",
                )
            projected_at = str(packet["captured_at"])
            try:
                projected_time = self._parse_timestamp(projected_at)
            except self.error_type as exc:
                raise self._error(
                    "context_projection_failed",
                    "CGG projection returned an invalid timeline",
                    retryable=True,
                ) from exc
            if projected_time + timedelta(seconds=1) < self._parse_timestamp(request.requested_at):
                raise self._error(
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
        except self.error_type as error:
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
            error = self._error(
                "context_projection_failed",
                f"CGG could not produce a complete receipt-bound {self.surface_name} projection",
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
        if not _stable_identifier(idempotency_key):
            raise self._error(
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
            raise self._error(
                "context_projection_unauthorized",
                f"caller cannot read this {self.surface_name} projection",
            )
        return record

    def _validate_admission(
        self,
        request: ProjectionRequest,
        *,
        caller_id: str,
        caller_secret: str,
        now: datetime,
    ) -> None:
        if not self._caller_authorized(caller_id, caller_secret):
            raise self._error(
                "context_projection_unauthorized",
                f"caller is not admitted for {self.surface_name} projection",
            )
        context_bytes = len(request.context.encode("utf-8"))
        if context_bytes > self.max_context_bytes or request.budget_tokens > self.max_budget_tokens:
            raise self._error(
                "context_projection_oversized",
                f"{self.surface_name} context exceeds the admitted projection budget",
            )
        requested_at = self._parse_timestamp(request.requested_at)
        age_seconds = (now - requested_at).total_seconds()
        if age_seconds > self.max_request_age_seconds or age_seconds < -30:
            raise self._error(
                "context_projection_stale",
                f"{self.surface_name} projection request is outside the admitted time window",
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
        request: ProjectionRequest,
        caller_id: str,
        request_digest: str,
        now: datetime,
    ) -> dict[str, object] | None:
        if existing.get("request_digest") != request_digest:
            error = self._error(
                "context_projection_replay_conflict",
                f"idempotency_key is already bound to different {self.surface_name} context",
            )
            self._record_denial(request, caller_id=caller_id, error=error, now=now)
            raise error
        status = existing.get("status")
        if status == "ready" and isinstance(existing.get("response"), dict):
            return {**dict(existing["response"]), "replayed": True}
        if status == "pending":
            started_at = self._parse_timestamp(
                str(existing.get("started_at") or request.requested_at)
            )
            if (now - started_at).total_seconds() <= self.pending_timeout_seconds:
                raise self._error(
                    "context_projection_in_progress",
                    f"an identical {self.surface_name} projection is already in progress",
                    retryable=True,
                )
        if status == "denied" and isinstance(existing.get("error"), dict):
            error = dict(existing["error"])
            raise self._error(
                str(error.get("code") or "context_projection_unsafe"),
                str(error.get("message") or f"{self.surface_name} projection was denied"),
                retryable=bool(error.get("retryable")),
            )
        if status not in {"pending", "failed"}:
            raise self._error(
                "context_projection_failed",
                f"stored {self.surface_name} projection has an unsupported recovery state",
                retryable=True,
            )
        return None

    def _record_denial(
        self,
        request: ProjectionRequest,
        *,
        caller_id: str,
        error: ProjectionError,
        now: datetime,
    ) -> None:
        self.store.record_denial(
            {
                "schema_version": 1,
                "status": "denied",
                "recorded_at": _format_timestamp(now),
                "binding": {
                    "request_id": request.request_id,
                    "correlation_id": request.correlation_id,
                    "idempotency_key": request.idempotency_key,
                    "caller_id": caller_id,
                    "context_digest": request.context_digest,
                },
                "error": error.to_dict(),
            }
        )

    def _parse_timestamp(self, value: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise self._error(
                "context_projection_invalid", "requested_at must be an ISO-8601 timestamp"
            ) from exc
        if parsed.tzinfo is None:
            raise self._error(
                "context_projection_invalid", "requested_at must include a timezone"
            )
        return parsed.astimezone(timezone.utc)

    def _error(self, code: str, message: str, *, retryable: bool = False) -> ProjectionError:
        return self.error_type(code, message, retryable=retryable)


def _stable_identifier(value: str) -> bool:
    return bool(value) and len(value) <= 256 and value[0].isalnum() and all(
        character.isalnum() or character in "._:-" for character in value
    )


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
