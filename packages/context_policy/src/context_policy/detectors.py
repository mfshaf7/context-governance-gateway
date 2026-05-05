from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from context_core.redaction.detectors import redact_text


class DetectorAdapter(Protocol):
    name: str
    source: str

    def scan(self, text: str) -> "DetectorResult":
        ...

    def status(self) -> dict[str, object]:
        ...


@dataclass(frozen=True)
class CustomRecognizer:
    code: str
    pattern: str
    replacement: str
    description: str
    flags: int = re.IGNORECASE

    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.pattern, self.flags)


@dataclass
class DetectorResult:
    redacted_text: str
    findings: list[dict[str, object]] = field(default_factory=list)
    unavailable_integrations: list[dict[str, object]] = field(default_factory=list)
    detector_sources: list[str] = field(default_factory=list)

    @property
    def finding_count(self) -> int:
        return sum(int(finding.get("count", 0)) for finding in self.findings)

    @property
    def uncertain_sensitive_material(self) -> bool:
        return bool(self.findings)

    def merge(self, other: "DetectorResult") -> None:
        self.redacted_text = other.redacted_text
        self.findings.extend(other.findings)
        self.unavailable_integrations.extend(other.unavailable_integrations)
        for source in other.detector_sources:
            if source not in self.detector_sources:
                self.detector_sources.append(source)

    def report(self) -> dict[str, object]:
        return {
            "finding_count": self.finding_count,
            "findings": self.findings,
            "uncertain_sensitive_material": self.uncertain_sensitive_material,
            "detector_sources": self.detector_sources,
            "unavailable_integrations": self.unavailable_integrations,
        }


@dataclass(frozen=True)
class DeterministicRedactionDetector:
    name: str = "deterministic-redaction"
    source: str = "local-deterministic-rules"

    def scan(self, text: str) -> DetectorResult:
        redacted, report = redact_text(text)
        findings = []
        for finding in report["findings"]:
            enriched = dict(finding)
            enriched.setdefault("detector", self.name)
            enriched.setdefault("source", self.source)
            findings.append(enriched)
        return DetectorResult(
            redacted_text=redacted,
            findings=findings,
            detector_sources=[self.source],
        )

    def status(self) -> dict[str, object]:
        return {
            "name": self.name,
            "source": self.source,
            "status": "active",
            "role": "deterministic phase-1 detection and masking",
        }


@dataclass(frozen=True)
class CustomRecognizerDetector:
    recognizers: tuple[CustomRecognizer, ...] = ()
    name: str = "custom-recognizers"
    source: str = "configured-custom-recognizers"

    def scan(self, text: str) -> DetectorResult:
        redacted = text
        findings: list[dict[str, object]] = []
        for recognizer in self.recognizers:
            redacted, count = recognizer.compiled().subn(recognizer.replacement, redacted)
            if count:
                findings.append(
                    {
                        "code": recognizer.code,
                        "description": recognizer.description,
                        "count": count,
                        "action": "masked",
                        "detector": self.name,
                        "source": self.source,
                    }
                )
        status = [] if self.recognizers else [self.status()]
        return DetectorResult(
            redacted_text=redacted,
            findings=findings,
            unavailable_integrations=status,
            detector_sources=[self.source] if self.recognizers else [],
        )

    def status(self) -> dict[str, object]:
        return {
            "name": self.name,
            "source": self.source,
            "status": "not_configured",
            "role": "operator-approved workspace recognizers",
        }


@dataclass(frozen=True)
class ExternalDetectorAdapter:
    name: str
    source: str
    tool: str
    role: str

    def scan(self, text: str) -> DetectorResult:
        raise NotImplementedError(
            f"{self.tool} integration is an explicit CGG adapter seam and is not configured in this foundation build."
        )

    def status(self) -> dict[str, object]:
        return {
            "name": self.name,
            "source": self.source,
            "tool": self.tool,
            "status": "not_configured",
            "role": self.role,
        }


@dataclass
class DetectorRegistry:
    active_detectors: tuple[DetectorAdapter, ...]
    external_integrations: tuple[ExternalDetectorAdapter, ...] = ()

    def scan(self, text: str) -> DetectorResult:
        result = DetectorResult(redacted_text=text)
        current = text
        for detector in self.active_detectors:
            detector_result = detector.scan(current)
            current = detector_result.redacted_text
            result.merge(detector_result)
        result.redacted_text = current
        result.unavailable_integrations.extend(integration.status() for integration in self.external_integrations)
        return result

    def status(self) -> dict[str, object]:
        return {
            "active_detectors": [detector.status() for detector in self.active_detectors],
            "external_integrations": [integration.status() for integration in self.external_integrations],
        }


def build_default_detector_registry(
    custom_recognizers: tuple[CustomRecognizer, ...] = (),
) -> DetectorRegistry:
    return DetectorRegistry(
        active_detectors=(
            DeterministicRedactionDetector(),
            CustomRecognizerDetector(custom_recognizers),
        ),
        external_integrations=(
            ExternalDetectorAdapter(
                name="presidio",
                source="external-presidio",
                tool="Presidio",
                role="PII and entity recognizer integration seam",
            ),
            ExternalDetectorAdapter(
                name="gitleaks",
                source="external-gitleaks",
                tool="Gitleaks",
                role="git-secret and credential scanner integration seam",
            ),
            ExternalDetectorAdapter(
                name="trufflehog",
                source="external-trufflehog",
                tool="TruffleHog",
                role="verified secret scanner integration seam",
            ),
        ),
    )


def scan_sensitive_context(
    text: str,
    *,
    registry: DetectorRegistry | None = None,
) -> tuple[str, dict[str, object]]:
    detector_registry = registry or build_default_detector_registry()
    result = detector_registry.scan(text)
    return result.redacted_text, result.report()
