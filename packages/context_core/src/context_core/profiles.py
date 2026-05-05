from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectionProfile:
    name: str
    purpose: str
    include_error_windows: bool
    context_lines: int
    deny_raw_projection_on_findings: bool
    suppress_excerpt_on_findings: bool


PROFILES = {
    "casual": ProjectionProfile(
        name="casual",
        purpose="Token reduction for low-risk local use with safe redacted excerpts.",
        include_error_windows=False,
        context_lines=3,
        deny_raw_projection_on_findings=True,
        suppress_excerpt_on_findings=False,
    ),
    "developer": ProjectionProfile(
        name="developer",
        purpose="Debugging-focused projection with relevant failure windows.",
        include_error_windows=True,
        context_lines=6,
        deny_raw_projection_on_findings=True,
        suppress_excerpt_on_findings=False,
    ),
    "enterprise": ProjectionProfile(
        name="enterprise",
        purpose="Strict projection with audit metadata and no raw log excerpt when sensitive material is detected.",
        include_error_windows=True,
        context_lines=4,
        deny_raw_projection_on_findings=True,
        suppress_excerpt_on_findings=True,
    ),
}

PROFILE_NAMES = tuple(PROFILES.keys())


def get_profile(name: str) -> ProjectionProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"unknown CGG profile: {name}") from exc
