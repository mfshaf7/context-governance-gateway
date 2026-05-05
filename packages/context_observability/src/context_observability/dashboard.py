from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from .models import AdmissionObservation


def _sort_key(observation: AdmissionObservation) -> str:
    return observation.captured_at


def build_dashboard_snapshot(
    observations: Iterable[AdmissionObservation],
    *,
    recent_limit: int = 10,
) -> dict[str, object]:
    ordered = sorted(list(observations), key=_sort_key, reverse=True)
    profile_counts = Counter(observation.policy_profile for observation in ordered)
    source_counts = Counter(observation.source_type for observation in ordered)
    raw_projection_counts = Counter(observation.raw_projection for observation in ordered)
    redaction_total = sum(observation.redaction_count for observation in ordered)
    budget_truncated_count = sum(1 for observation in ordered if observation.budget_truncated)
    failure_count = sum(1 for observation in ordered if observation.failure_detected)
    unavailable = sorted(
        {
            integration
            for observation in ordered
            for integration in observation.unavailable_integrations
        }
    )

    if not ordered:
        status = "empty"
    elif failure_count or budget_truncated_count or unavailable:
        status = "attention"
    else:
        status = "ok"

    recent = []
    for observation in ordered[:recent_limit]:
        recent.append(
            {
                "artifact_digest": observation.artifact_digest,
                "captured_at": observation.captured_at,
                "source_type": observation.source_type,
                "policy_profile": observation.policy_profile,
                "raw_projection": observation.raw_projection,
                "redaction_count": observation.redaction_count,
                "budget": {
                    "estimated_tokens": observation.budget_estimated_tokens,
                    "budget_tokens": observation.budget_limit_tokens,
                    "truncated": observation.budget_truncated,
                },
                "failure_detected": observation.failure_detected,
                "packet_available": observation.packet_available,
                "receipt_available": observation.receipt_available,
                "manifest_available": observation.manifest_available,
            }
        )

    return {
        "schema_version": 1,
        "purpose": "operator-safe-context-admission-dashboard",
        "status": status,
        "summary": {
            "packet_count": len(ordered),
            "redaction_count": redaction_total,
            "budget_truncated_count": budget_truncated_count,
            "failure_count": failure_count,
            "profile_counts": dict(sorted(profile_counts.items())),
            "source_type_counts": dict(sorted(source_counts.items())),
            "raw_projection_counts": dict(sorted(raw_projection_counts.items())),
            "unavailable_integration_count": len(unavailable),
        },
        "safety_posture": {
            "raw_context_visible": False,
            "packet_excerpt_visible": False,
            "raw_artifact_locations_visible": False,
            "dashboard_role": "operator_status_not_raw_context_view",
        },
        "unavailable_integrations": unavailable,
        "recent_admissions": recent,
    }


def render_dashboard_text(snapshot: dict[str, object]) -> str:
    summary = dict(snapshot.get("summary") or {})
    safety = dict(snapshot.get("safety_posture") or {})
    lines = [
        "Context Governance Gateway dashboard",
        f"Status: {snapshot.get('status', 'unknown')}",
        f"Packets: {summary.get('packet_count', 0)}",
        f"Redactions: {summary.get('redaction_count', 0)}",
        f"Failures: {summary.get('failure_count', 0)}",
        f"Budget truncations: {summary.get('budget_truncated_count', 0)}",
        f"Raw context visible: {safety.get('raw_context_visible', False)}",
        f"Raw artifact locations visible: {safety.get('raw_artifact_locations_visible', False)}",
    ]
    recent = list(snapshot.get("recent_admissions") or [])
    if recent:
        lines.append("Recent admissions:")
        for admission in recent:
            digest = str(admission.get("artifact_digest", "unknown"))
            lines.append(
                "- "
                + " ".join(
                    [
                        digest[:12],
                        str(admission.get("policy_profile", "unknown")),
                        str(admission.get("raw_projection", "unknown")),
                        f"redactions={admission.get('redaction_count', 0)}",
                    ]
                )
            )
    return "\n".join(lines) + "\n"
