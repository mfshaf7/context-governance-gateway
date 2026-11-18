from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from context_storage import LocalRefinementProjectionStore

from .projection import ReceiptBoundContextProjector


REFINEMENT_TASK_CONTRACT = "oos.delivery-refinement.v1"
REFINEMENT_TASK_VERSION = "1.0"
REFINEMENT_TASK_KIND = "metadata_advice"
REFINEMENT_FIELD_KINDS = frozenset({"long_text", "number", "select", "short_text"})
REFINEMENT_FAILURE_CODES = frozenset(
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


class RefinementProjectionError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        if code not in REFINEMENT_FAILURE_CODES:
            raise ValueError(f"unregistered Refinement projection failure code: {code}")
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
class RefinementProjectionRequest:
    idempotency_key: str
    workflow_session_id: str
    execution_id: str
    requested_at: str
    assist_request: dict[str, object]
    assist_request_digest: str
    budget_tokens: int
    work_context: dict[str, object] | None = None

    @property
    def source_scope(self) -> str:
        return self.delivery_id

    @property
    def request_id(self) -> str:
        return str(self.assist_request.get("request_id") or "")

    @property
    def correlation_id(self) -> str:
        return str(self.assist_request.get("correlation_id") or "")

    @property
    def delivery_id(self) -> str:
        return str(self.assist_request.get("delivery_id") or "")

    @property
    def package_ref(self) -> str:
        return str(self.assist_request.get("package_ref") or "")

    @property
    def context(self) -> str:
        return _canonical_json({**self.assist_request, **({"work_context": self.work_context} if self.work_context is not None else {})})

    @property
    def context_digest(self) -> str:
        return _digest_text(self.context)

    def validate_shape(self) -> None:
        if set(self.assist_request) - {"conversation", "related_drafts"} != {
            "schema_version",
            "request_id",
            "correlation_id",
            "delivery_id",
            "package_ref",
            "source_ref",
            "source_revision",
            "operator",
            "task",
            "packet",
            "target",
            "operator_prompt",
        }:
            raise RefinementProjectionError(
                "context_projection_invalid",
                "assist_request must match the admitted Refinement request shape",
            )
        if "conversation" in self.assist_request:
            turns = self.assist_request["conversation"]
            if not isinstance(turns, list) or len(turns) > 8 or any(not isinstance(turn, dict) or set(turn) != {"role", "text"}
                    or turn["role"] not in ("operator", "advisor") or not isinstance(turn["text"], str) or len(turn["text"]) > 12000 for turn in turns):
                raise RefinementProjectionError("context_projection_invalid", "Conversation must retain complete bounded working messages")
        if "related_drafts" in self.assist_request:
            drafts = self.assist_request["related_drafts"]
            if not isinstance(drafts, list) or len(drafts) > 256 or any(
                not isinstance(item, dict) or set(item) != {"field_key", "node_id", "value"}
                or not isinstance(item["field_key"], str) or not _STABLE_ID.fullmatch(item["field_key"])
                or not isinstance(item["node_id"], str) or not _STABLE_ID.fullmatch(item["node_id"])
                or not isinstance(item["value"], str) or len(item["value"]) > 16000 for item in drafts):
                raise RefinementProjectionError("context_projection_invalid", "Related drafts must be bounded typed field values")
            keys = [(item["field_key"], item["node_id"]) for item in drafts]
            if len(keys) != len(set(keys)):
                raise RefinementProjectionError("context_projection_invalid", "Related draft targets must be unique")
        for name, value in {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "workflow_session_id": self.workflow_session_id,
            "execution_id": self.execution_id,
        }.items():
            if not _STABLE_ID.fullmatch(value):
                raise RefinementProjectionError(
                    "context_projection_invalid", f"{name} must be a stable identifier"
                )
        if self.assist_request.get("schema_version") != 1:
            raise RefinementProjectionError(
                "context_projection_invalid", "assist_request schema_version must equal 1"
            )
        if not _DELIVERY_ID.fullmatch(self.delivery_id):
            raise RefinementProjectionError(
                "context_projection_invalid", "delivery_id must use the delivery-<number> form"
            )
        for name in ("package_ref", "source_ref", "source_revision"):
            value = self.assist_request.get(name)
            if not isinstance(value, str) or not value or len(value) > 512:
                raise RefinementProjectionError(
                    "context_projection_invalid", f"{name} must be present and bounded"
                )

        operator = self._object("operator")
        if (
            not set(operator).issubset({"id", "handle"})
            or "id" not in operator
            or not isinstance(operator.get("id"), str)
            or not operator["id"]
            or ("handle" in operator and (not isinstance(operator["handle"], str) or not operator["handle"]))
        ):
            raise RefinementProjectionError(
                "context_projection_invalid", "operator.id must be present"
            )
        task = self._object("task")
        if task != {
            "kind": REFINEMENT_TASK_KIND,
            "contract_ref": REFINEMENT_TASK_CONTRACT,
            "version": REFINEMENT_TASK_VERSION,
        }:
            raise RefinementProjectionError(
                "context_projection_invalid", "task does not match the admitted Refinement contract"
            )
        packet = self._object("packet")
        if set(packet) != {"packet_id", "packet_revision", "source_work_design_receipt_id"}:
            raise RefinementProjectionError(
                "context_projection_invalid", "packet must match the admitted binding shape"
            )
        for name in ("packet_id", "packet_revision", "source_work_design_receipt_id"):
            value = packet.get(name)
            if not isinstance(value, str) or not value:
                raise RefinementProjectionError(
                    "context_projection_invalid", f"packet.{name} must be present"
                )
        if not _STABLE_ID.fullmatch(str(packet["packet_id"])):
            raise RefinementProjectionError(
                "context_projection_invalid", "packet.packet_id must be a stable identifier"
            )

        target = self._object("target")
        required_target = {
            "field_key",
            "field_label",
            "field_kind",
            "required",
            "source_value",
            "draft_value",
            "selected_node_ids",
            "allowed_values",
        }
        if set(target) != required_target:
            raise RefinementProjectionError(
                "context_projection_invalid", "target must match the admitted Refinement field shape"
            )
        if not _STABLE_ID.fullmatch(str(target.get("field_key") or "")):
            raise RefinementProjectionError(
                "context_projection_invalid", "target.field_key must be a stable identifier"
            )
        if not isinstance(target.get("field_label"), str) or not target["field_label"]:
            raise RefinementProjectionError(
                "context_projection_invalid", "target.field_label must be present"
            )
        if target.get("field_kind") not in REFINEMENT_FIELD_KINDS:
            raise RefinementProjectionError(
                "context_projection_invalid", "target.field_kind is not admitted"
            )
        if not isinstance(target.get("required"), bool):
            raise RefinementProjectionError(
                "context_projection_invalid", "target.required must be boolean"
            )
        for name in ("source_value", "draft_value"):
            if not isinstance(target.get(name), str):
                raise RefinementProjectionError(
                    "context_projection_invalid", f"target.{name} must be text"
                )
        selected_node_ids = target.get("selected_node_ids")
        if (
            not isinstance(selected_node_ids, list)
            or not selected_node_ids
            or any(not isinstance(value, str) or not _STABLE_ID.fullmatch(value) for value in selected_node_ids)
            or len(set(selected_node_ids)) != len(selected_node_ids)
        ):
            raise RefinementProjectionError(
                "context_projection_invalid",
                "target.selected_node_ids must contain unique stable identifiers",
            )
        allowed_values = target.get("allowed_values")
        if (
            not isinstance(allowed_values, list)
            or any(not isinstance(value, str) for value in allowed_values)
            or len(set(allowed_values)) != len(allowed_values)
        ):
            raise RefinementProjectionError(
                "context_projection_invalid", "target.allowed_values must contain unique text values"
            )

        prompt = self.assist_request.get("operator_prompt")
        if not isinstance(prompt, str) or not 1 <= len(prompt) <= 4000:
            raise RefinementProjectionError(
                "context_projection_invalid", "operator_prompt must be present and bounded"
            )
        if not _SHA256.fullmatch(self.assist_request_digest):
            raise RefinementProjectionError(
                "context_projection_invalid", "assist_request_digest must be a sha256 digest"
            )
        if self.assist_request_digest != _digest_text(_canonical_json(self.assist_request)):
            raise RefinementProjectionError(
                "context_projection_invalid",
                "assist_request_digest does not match the canonical assist request",
            )
        if self.budget_tokens < 1:
            raise RefinementProjectionError(
                "context_projection_invalid", "budget_tokens must be positive"
            )
        _parse_timestamp(self.requested_at)
        if self.work_context is not None:
            self._validate_work_context()
        elif self.assist_request.get("related_drafts"):
            raise RefinementProjectionError("context_projection_invalid", "Related drafts require bound owner context")

    def binding(self, caller_id: str) -> dict[str, object]:
        task = self._object("task")
        packet = self._object("packet")
        target = self._object("target")
        operator = self._object("operator")
        return {
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "workflow_session_id": self.workflow_session_id,
            "execution_id": self.execution_id,
            "delivery_id": self.delivery_id,
            "package_ref": self.package_ref,
            "source_ref": self.assist_request["source_ref"],
            "source_revision": self.assist_request["source_revision"],
            "caller_id": caller_id,
            "operator_id": operator["id"],
            "task": task,
            "packet": packet,
            "target": {
                "field_key": target["field_key"],
                "field_kind": target["field_kind"],
                "selected_node_ids": target["selected_node_ids"],
            },
            "requested_at": self.requested_at,
            "context_digest": self.context_digest,
            "budget_tokens": self.budget_tokens,
        }

    def canonical_projection_text(self, caller_id: str) -> str:
        return _canonical_json(
            {
                "binding": self.binding(caller_id),
                "refinement_context": self.assist_request,
                **({"work_context": self.work_context} if self.work_context is not None else {}),
            }
        )

    def request_digest(self, caller_id: str) -> str:
        return _digest_text(self.canonical_projection_text(caller_id))

    def _object(self, name: str) -> dict[str, object]:
        value = self.assist_request.get(name)
        if not isinstance(value, dict):
            raise RefinementProjectionError(
                "context_projection_invalid", f"assist_request.{name} must be an object"
            )
        return value

    def _validate_work_context(self) -> None:
        value = self.work_context
        valid = isinstance(value, dict) and set(value) - {"metadata", "planning_rules"} == {"package_ref", "source_ref", "source_revision", "source_work_design_receipt_id", "nodes", "coverage"}
        if valid:
            valid = all(value[key] == self.assist_request.get(key) for key in ("package_ref", "source_ref", "source_revision"))
            valid = valid and value["source_work_design_receipt_id"] == (self.assist_request.get("packet") or {}).get("source_work_design_receipt_id")
            valid = valid and isinstance(value["coverage"], str) and bool(value["coverage"].strip()) and isinstance(value["nodes"], list) and bool(value["nodes"])
        if valid:
            nodes = value["nodes"]
            valid = all(isinstance(node, dict) and set(node) - {"planning"} == {"id", "kind", "title", "description"}
                        and all(isinstance(node[key], str) for key in ("id", "kind", "title", "description"))
                        and ("planning" not in node or isinstance(node["planning"], dict) and set(node["planning"]) == {"status", "target_pi", "iteration", "owner_repo"} and all(isinstance(v, str) for v in node["planning"].values()))
                        and bool(_STABLE_ID.fullmatch(node["id"])) and bool(node["title"].strip())
                        for node in nodes)
            if valid:
                ids = [node["id"] for node in nodes]
                valid = len(ids) == len(set(ids)) and set((self.assist_request.get("target") or {}).get("selected_node_ids", [])).issubset(ids)
        if valid and "metadata" in value:
            items = value["metadata"]
            required = {"node_id", "field_key", "backend_field", "field_kind", "required", "status", "source_value", "allowed_values", "validation_hint"}
            valid = isinstance(items, list) and len(items) <= 4096 and all(
                isinstance(item, dict) and set(item) - {"draft_value", "numeric_type"} == required
                and all(isinstance(item[key], str) for key in ("node_id", "field_key", "backend_field", "field_kind", "status", "source_value", "validation_hint"))
                and item["node_id"] in ids and bool(_STABLE_ID.fullmatch(item["field_key"]))
                and item["field_kind"] in ("generated", "long_text", "number", "select", "short_text")
                and ("numeric_type" not in item or item["field_kind"] == "number" and item["numeric_type"] in ("integer", "decimal"))
                and type(item["required"]) is bool and item["status"] in ("blocked", "complete", "missing")
                and isinstance(item["allowed_values"], list) and all(isinstance(v, str) for v in item["allowed_values"])
                and len(item["allowed_values"]) == len(set(item["allowed_values"]))
                and ("draft_value" not in item or isinstance(item["draft_value"], str) and len(item["draft_value"]) <= 16000)
                for item in items)
            if valid:
                keys = [(item["field_key"], item["node_id"]) for item in items]
                valid = len(keys) == len(set(keys)) and all(any(
                    item["field_key"] == draft["field_key"] and item["node_id"] == draft["node_id"] and item.get("draft_value") == draft["value"]
                    for item in items) for draft in self.assist_request.get("related_drafts", []))
        elif valid and self.assist_request.get("related_drafts"):
            valid = False
        if valid and "planning_rules" in value:
            rules = value["planning_rules"]
            lists = ("iteration_prefix_templates", "target_pi_required_types", "iteration_required_types")
            valid = isinstance(rules, dict) and set(rules) == {"workflow_id", "backlog_iteration_label", *lists}
            valid = valid and all(isinstance(rules[key], str) for key in ("workflow_id", "backlog_iteration_label"))
            valid = valid and all(isinstance(rules[key], list) and all(isinstance(v, str) for v in rules[key]) for key in lists)
        if not valid:
            raise RefinementProjectionError("context_projection_invalid", "Work context must bind the same source, receipt and selected nodes without duplicate or foreign fields")


class RefinementContextProjector(ReceiptBoundContextProjector):
    def __init__(
        self,
        *,
        store: LocalRefinementProjectionStore,
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
            surface_name="Refinement",
            source_label="refinement",
            source_type="refinement-assist",
            error_type=RefinementProjectionError,
        )

    def _response_fields(self, *, request, caller_id, packet, receipt):
        if (packet.get("budget") or {}).get("truncated") is True:
            raise RefinementProjectionError(
                "context_projection_oversized",
                "The selected Refinement field context was shortened by the context budget. Select a smaller scope; no complete field projection was issued.",
            )
        return {}


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _digest_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RefinementProjectionError(
            "context_projection_invalid", "requested_at must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise RefinementProjectionError(
            "context_projection_invalid", "requested_at must include a timezone"
        )
    return parsed.astimezone(timezone.utc)
