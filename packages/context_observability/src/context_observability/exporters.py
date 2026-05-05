from __future__ import annotations

from collections.abc import Iterable

from .models import AdmissionObservation, MetricSample, TraceSpan


def _label_value(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _metric_line(sample: MetricSample) -> str:
    if sample.labels:
        labels = ",".join(f'{key}="{_label_value(value)}"' for key, value in sorted(sample.labels.items()))
        return f"{sample.name}{{{labels}}} {sample.value}"
    return f"{sample.name} {sample.value}"


def build_prometheus_metrics(observations: Iterable[AdmissionObservation]) -> list[MetricSample]:
    samples: list[MetricSample] = []
    for observation in observations:
        labels = {
            "policy_profile": observation.policy_profile,
            "raw_projection": observation.raw_projection,
            "source_type": observation.source_type,
        }
        samples.extend(
            [
                MetricSample(
                    name="cgg_context_admission_packets_total",
                    value=1,
                    labels=labels,
                    help_text="CGG model-safe packet admissions observed by policy profile and source type.",
                    metric_type="counter",
                ),
                MetricSample(
                    name="cgg_context_redactions_total",
                    value=observation.redaction_count,
                    labels=labels,
                    help_text="Redaction findings applied during CGG context admission.",
                    metric_type="counter",
                ),
                MetricSample(
                    name="cgg_context_budget_estimated_tokens",
                    value=observation.budget_estimated_tokens,
                    labels=labels,
                    help_text="Estimated tokens admitted into the model-safe packet.",
                    metric_type="gauge",
                ),
                MetricSample(
                    name="cgg_context_budget_truncations_total",
                    value=1 if observation.budget_truncated else 0,
                    labels=labels,
                    help_text="Model-safe packet projections truncated by token budget.",
                    metric_type="counter",
                ),
                MetricSample(
                    name="cgg_context_failures_detected_total",
                    value=1 if observation.failure_detected else 0,
                    labels=labels,
                    help_text="CGG admissions whose classified context indicates failure or error.",
                    metric_type="counter",
                ),
            ]
        )
    return samples


def render_prometheus(samples: Iterable[MetricSample]) -> str:
    lines: list[str] = []
    emitted_headers: set[str] = set()
    for sample in samples:
        if sample.name not in emitted_headers:
            help_text = sample.help_text or sample.name
            lines.append(f"# HELP {sample.name} {help_text}")
            lines.append(f"# TYPE {sample.name} {sample.metric_type}")
            emitted_headers.add(sample.name)
        lines.append(_metric_line(sample))
    return "\n".join(lines) + ("\n" if lines else "")


def build_trace_spans(observations: Iterable[AdmissionObservation]) -> list[TraceSpan]:
    spans: list[TraceSpan] = []
    for observation in observations:
        spans.append(
            TraceSpan(
                name="cgg.context_admission",
                attributes={
                    "cgg.artifact_digest": observation.artifact_digest,
                    "cgg.captured_at": observation.captured_at,
                    "cgg.source_type": observation.source_type,
                    "cgg.policy_profile": observation.policy_profile,
                    "cgg.raw_projection": observation.raw_projection,
                    "cgg.redaction_count": observation.redaction_count,
                    "cgg.budget.estimated_tokens": observation.budget_estimated_tokens,
                    "cgg.budget.truncated": observation.budget_truncated,
                    "cgg.failure_detected": observation.failure_detected,
                    "cgg.detector.source_count": len(observation.detector_sources),
                    "cgg.detector.unavailable_count": len(observation.unavailable_integrations),
                    "cgg.policy.decision_count": observation.policy_decision_count,
                    "cgg.raw_artifact_location_visible": False,
                    "otel.exporter.status": "seam_not_configured",
                },
                events=(
                    {
                        "name": "context_admission_projected",
                        "attributes": {
                            "packet_available": observation.packet_available,
                            "receipt_available": observation.receipt_available,
                            "manifest_available": observation.manifest_available,
                        },
                    },
                ),
            )
        )
    return spans
