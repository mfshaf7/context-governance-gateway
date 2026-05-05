# API App

The API app provides the bounded service-mode contract for CGG source-backed
service fronts.

It is intentionally fail-closed by default:

- `CGG_RUNTIME_PROFILE_STATE=build-admitted` reports health but denies mutating
  context admission requests.
- `CGG_RUNTIME_PROFILE_STATE=active` is required before
  `POST /v1/context/admissions` can write artifacts, packets, receipts, and
  ledger events.
- `GET /healthz` always reports process health.
- `GET /readyz` returns ready only when the profile is active.

Run locally after installing the API extra:

```bash
python3 -m pip install -e '.[api]'
CGG_RUNTIME_PROFILE_STATE=active uvicorn cgg_api.app:app
```

Configuration:

- `CGG_ROOT`: workspace root for `.cgg/` artifacts.
- `CGG_RUNTIME_PROFILE_STATE`: `build-admitted` by default, `active` to allow
  mutating admission.
- `CGG_METADATA_BACKEND`: `local` or `postgres-pgvector`.
- `CGG_ARTIFACT_BACKEND`: `local` or `minio-s3`.
- `CGG_POSTGRES_DSN`: required for `postgres-pgvector`.
- `CGG_S3_ENDPOINT_URL` and `CGG_S3_BUCKET`: required for `minio-s3`.

Primary routes:

- `POST /v1/context/admissions`
- `GET /v1/context/packets/{artifact_id}`
- `GET /v1/context/receipts/{artifact_id}`
- `GET /v1/context/manifests/{artifact_id}`
- `GET /v1/observability/admissions`
- `GET /v1/observability/metrics`
- `GET /v1/observability/traces`
- `GET /v1/operator/dashboard`
- `GET /v1/operator/dashboard.txt`

The API reuses `context_core.pipeline.ContextPipeline`, including the
`context_policy` admission and detector boundary. It does not introduce a
separate capture, detector, redaction, policy, projection, packet, receipt, or
ledger path.

Observability routes are read-only source seams:

- `/v1/observability/metrics` renders Prometheus-compatible text from governed
  packet metadata. It does not implement Prometheus storage or scraping.
- `/v1/observability/traces` renders OpenTelemetry-compatible JSON span
  payloads. It does not implement an OTLP collector or tracing backend.
- `/v1/operator/dashboard` and `.txt` render operator-safe dashboard summaries.
  They do not display raw context, safe excerpts, or raw artifact locations.
