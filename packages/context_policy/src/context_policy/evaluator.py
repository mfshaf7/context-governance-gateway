from __future__ import annotations

from dataclasses import dataclass

from context_core.profiles import ProjectionProfile


@dataclass(frozen=True)
class PolicyDecision:
    control: str
    decision: str
    reason: str
    policy_engine: str = "deterministic-local"

    def to_dict(self) -> dict[str, str]:
        return {
            "control": self.control,
            "decision": self.decision,
            "reason": self.reason,
            "policy_engine": self.policy_engine,
        }


@dataclass(frozen=True)
class PolicyEvaluation:
    profile: str
    admission_decision: dict[str, object]
    decisions: tuple[PolicyDecision, ...]
    opa: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "admission_decision": self.admission_decision,
            "decisions": [decision.to_dict() for decision in self.decisions],
            "opa": self.opa,
        }


def evaluate_context_admission(
    *,
    profile: ProjectionProfile,
    redaction_report: dict[str, object],
    raw_projection_requested: bool = False,
    debug_override_requested: bool = False,
    debug_override_allowed: bool = False,
) -> PolicyEvaluation:
    finding_count = int(redaction_report.get("finding_count", 0))
    uncertain = bool(redaction_report.get("uncertain_sensitive_material"))
    raw_projection_denied = bool(
        raw_projection_requested
        or (profile.deny_raw_projection_on_findings and (finding_count or uncertain))
    )
    raw_projection_state = "denied" if raw_projection_denied else "not_requested"
    if raw_projection_denied:
        admission_reason = (
            "Sensitive or uncertain material detected; raw projection denied by profile."
            if finding_count or uncertain
            else "Raw projection was requested but denied by default context admission policy."
        )
    else:
        admission_reason = "No raw projection requested; packet contains budgeted safe context only."

    redaction_safe = finding_count == 0 or raw_projection_denied
    debug_override_decision = "allowed" if debug_override_requested and debug_override_allowed else "denied"
    debug_override_reason = (
        "Debug override explicitly allowed by caller policy."
        if debug_override_decision == "allowed"
        else "Debug override denied by default; OPA debug_override policy defaults to fail closed."
    )
    admission_decision = {
        "profile": profile.name,
        "raw_projection": raw_projection_state,
        "reason": admission_reason,
        "redaction_safe": redaction_safe,
        "preserve_raw_artifact": True,
        "debug_override": debug_override_decision,
    }
    decisions = (
        PolicyDecision(
            control="context_admission",
            decision="allow_model_safe_packet",
            reason="Model-safe packet projection is allowed only after redaction, budgeting, and policy admission.",
        ),
        PolicyDecision(
            control="raw_projection",
            decision=raw_projection_state,
            reason=admission_reason,
        ),
        PolicyDecision(
            control="redaction",
            decision="safe" if redaction_safe else "unsafe",
            reason=(
                "Redaction is safe because no sensitive findings were detected or raw projection was denied."
                if redaction_safe
                else "Redaction is unsafe because findings exist without raw-projection denial."
            ),
        ),
        PolicyDecision(
            control="retention",
            decision="preserve_raw_artifact",
            reason="Raw artifact custody is preserved for audit while packet projection stays governed.",
        ),
        PolicyDecision(
            control="debug_override",
            decision=debug_override_decision,
            reason=debug_override_reason,
        ),
    )
    return PolicyEvaluation(
        profile=profile.name,
        admission_decision=admission_decision,
        decisions=decisions,
        opa={
            "engine": "opa",
            "status": "adapter_seam_not_configured",
            "policy_paths": [
                "policies/opa/context_admission.rego",
                "policies/opa/redaction.rego",
                "policies/opa/retention.rego",
                "policies/opa/debug_override.rego",
            ],
        },
    )
