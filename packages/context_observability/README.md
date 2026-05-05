# Context Observability

`context_observability` provides source-level observability projections for
CGG context admission.

It is intentionally not an observability backend. It produces safe,
Prometheus-compatible metric samples, OpenTelemetry-compatible span payloads,
and operator dashboard view models from already governed CGG artifacts.

Safety rules:

- never include raw artifact locations
- never include raw captured context
- never include safe-context excerpts in dashboard or telemetry payloads
- keep high-cardinality artifact digests out of metric labels
- expose artifact digests only in traces and dashboard summaries where they are
  needed for audit correlation

External systems such as Prometheus, OpenTelemetry collectors, and Langfuse can
integrate later through these seams after runtime activation.
