from __future__ import annotations

from dataclasses import dataclass, field


def _string(value: object, default: str = "unknown") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return default


def _integration_name(value: object) -> str:
    if isinstance(value, dict):
        return _string(value.get("name") or value.get("source") or value.get("tool"))
    return _string(value)


@dataclass(frozen=True)
class AdmissionObservation:
    artifact_digest: str
    captured_at: str
    source_type: str
    policy_profile: str
    raw_projection: str
    redaction_count: int
    detector_sources: tuple[str, ...] = ()
    unavailable_integrations: tuple[str, ...] = ()
    budget_estimated_tokens: int = 0
    budget_limit_tokens: int = 0
    budget_truncated: bool = False
    failure_detected: bool = False
    policy_decision_count: int = 0
    packet_available: bool = True
    receipt_available: bool = False
    manifest_available: bool = False

    @classmethod
    def from_artifacts(
        cls,
        *,
        manifest: dict[str, object] | None,
        packet: dict[str, object],
        receipt: dict[str, object] | None = None,
        redaction_report: dict[str, object] | None = None,
    ) -> "AdmissionObservation":
        admission = dict(packet.get("admission_decision") or {})
        source = dict(packet.get("source") or {})
        budget = dict(packet.get("budget") or packet.get("token_output_budget_used") or {})
        failure_summary = dict(packet.get("failure_summary") or {})
        context_admission = dict(packet.get("context_admission") or {})
        decisions = list(context_admission.get("decisions") or [])
        detectors = dict((manifest or {}).get("detectors") or {})
        report = dict((redaction_report or {}).get("report") or redaction_report or {})

        detector_sources = tuple(_string(source) for source in detectors.get("sources", []) if source)
        unavailable = tuple(_integration_name(source) for source in detectors.get("unavailable_integrations", []) if source)

        return cls(
            artifact_digest=_string(packet.get("artifact_digest")),
            captured_at=_string(packet.get("captured_at")),
            source_type=_string(source.get("type")),
            policy_profile=_string(packet.get("policy_profile")),
            raw_projection=_string(admission.get("raw_projection"), default="not_requested"),
            redaction_count=_int(report.get("finding_count"), default=len(list(packet.get("redactions_applied") or []))),
            detector_sources=detector_sources,
            unavailable_integrations=unavailable,
            budget_estimated_tokens=_int(budget.get("estimated_tokens")),
            budget_limit_tokens=_int(budget.get("budget_tokens") or budget.get("requested_tokens")),
            budget_truncated=bool(budget.get("truncated")),
            failure_detected=bool(failure_summary.get("detected")),
            policy_decision_count=len(decisions),
            packet_available=True,
            receipt_available=receipt is not None,
            manifest_available=manifest is not None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "artifact_digest": self.artifact_digest,
            "captured_at": self.captured_at,
            "source_type": self.source_type,
            "policy_profile": self.policy_profile,
            "raw_projection": self.raw_projection,
            "redaction_count": self.redaction_count,
            "detector_sources": list(self.detector_sources),
            "unavailable_integrations": list(self.unavailable_integrations),
            "budget": {
                "estimated_tokens": self.budget_estimated_tokens,
                "budget_tokens": self.budget_limit_tokens,
                "truncated": self.budget_truncated,
            },
            "failure_detected": self.failure_detected,
            "policy_decision_count": self.policy_decision_count,
            "artifact_links": {
                "packet_available": self.packet_available,
                "receipt_available": self.receipt_available,
                "manifest_available": self.manifest_available,
                "raw_artifact_location_visible": False,
            },
        }


@dataclass(frozen=True)
class MetricSample:
    name: str
    value: int | float
    labels: dict[str, str] = field(default_factory=dict)
    help_text: str = ""
    metric_type: str = "gauge"

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "labels": dict(self.labels),
            "help": self.help_text,
            "type": self.metric_type,
        }


@dataclass(frozen=True)
class TraceSpan:
    name: str
    attributes: dict[str, object]
    events: tuple[dict[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "attributes": dict(self.attributes),
            "events": [dict(event) for event in self.events],
        }
