# API App

The API app now provides the bounded service-mode contract for #587/#588.

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

The API reuses `context_core.pipeline.ContextPipeline`; it does not introduce a
separate capture/redaction/projection path.
