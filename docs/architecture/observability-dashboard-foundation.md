# Observability And Dashboard Foundation

This source foundation makes CGG context admission observable without turning
CGG into an observability platform.

## Scope

- Build safe admission observations from packet, receipt, manifest, and
  redaction-report metadata.
- Render Prometheus-compatible metric samples.
- Render OpenTelemetry-compatible span payloads.
- Render an operator dashboard snapshot and text view.

## Non-Goals

- No Prometheus server.
- No OpenTelemetry collector.
- No Langfuse backend.
- No live Next.js dashboard deployment.
- No raw artifact browser.
- No raw context, safe-context excerpt, or raw artifact location in
  observability/dashboard payloads.

## Safety Contract

Metrics use low-cardinality labels only:

- policy profile
- raw projection decision
- source type

Traces and dashboard summaries may expose the artifact digest for audit
correlation. They still hide raw artifact locations and captured content.

## Runtime Contract

The API exposes read-only observability and dashboard routes. Mutating context
admission still requires `CGG_RUNTIME_PROFILE_STATE=active`. The current
dev-integration profile is active for local service-shape proof only; this is
not governed stage or production runtime evidence.
