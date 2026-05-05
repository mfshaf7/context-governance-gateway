# CGG Dev-Integration Service

The `context-governance-gateway` dev-integration profile is the local
operational lane for service-mode CGG proof.

It is not stage or production evidence.

## Lifecycle

- `build-admitted`: source implementation is allowed, but runtime launch and
  access fail closed.
- `active`: the shared runner can launch the local-k3s runtime and run
  read-only smoke.

The profile derives lifecycle from the shared runner session manifest, or from
`DEVINT_PROFILE_LIFECYCLE` during direct owner-repo tests.

## Active Runtime

Active `up` creates:

- `context-governance-gateway-api`
- `context-governance-gateway-worker`
- `context-governance-gateway-postgresql`
- `context-governance-gateway-minio`
- PVC-backed CGG state, PostgreSQL data, and MinIO data

The API uses the existing CGG pipeline and local PVC-backed custody for packet,
receipt, manifest, redaction-report, raw-artifact, and ledger files. PostgreSQL
and MinIO are admitted runtime dependencies for the next persistence hardening
front; this profile does not claim governed stage dependency readiness.

## Operator Commands

Run through the shared platform runner after workspace activation:

```bash
make devint-up PROFILE=context-governance-gateway
make devint-status PROFILE=context-governance-gateway
make devint-access PROFILE=context-governance-gateway
make devint-smoke PROFILE=context-governance-gateway
make devint-down PROFILE=context-governance-gateway
make devint-reset PROFILE=context-governance-gateway
make devint-promote-check PROFILE=context-governance-gateway
```

`access` exposes the API at `http://localhost:18280`.

## Smoke

Smoke is read-only for the persistent lane. It reads:

- `/healthz`
- `/readyz`
- `/v1/context/packets/{artifact_id}`
- `/v1/context/receipts/{artifact_id}`
- `/v1/context/manifests/{artifact_id}`
- `/v1/operator/dashboard`
- `/v1/observability/metrics`
- `/v1/observability/traces`

It confirms raw projection is denied and the seeded secret-like value is not
present in the safe excerpt. It does not call a model and does not create new
test traffic.

## Failure Handling

- If the profile is not `active`, `up` and `access` refuse to run.
- If smoke finds no seed packet, run `up` first.
- If readiness fails, inspect the API pod install log at
  `/tmp/cgg-pip-install.log` inside the pod before changing manifests.
- If raw context appears in packet, dashboard, metric, or trace output, treat it
  as a security blocker before continuing activation.
