# Context Governance Gateway Dev-Integration Profile

This is the build-admitted `dev-integration` profile for Context Governance
Gateway service-mode implementation.

Lifecycle:

- `build-admitted`
- not self-serve launchable
- bounded service implementation is authorized by workspace, platform, and
  security gates
- runtime creation is denied until workspace, platform, and security activation
  promote the profile to `active`

The profile exists so API, worker, persistent storage, dashboard, broker
adapter, or cross-repo runtime work cannot start from chat memory or local
convenience. `build-admitted` authorizes the bounded owner-repo implementation
front; it does not make the runtime launchable.

## What It Runs When Active

When admitted, the profile is expected to run:

- a Context Governance Gateway API service
- a processing worker heartbeat
- PostgreSQL as the admitted metadata/search dependency
- MinIO/S3-compatible artifact custody dependency
- PVC-backed CGG state for packet, receipt, manifest, redaction-report,
  raw-artifact, and ledger custody
- read-only smoke that proves admission health without projecting raw
  operational context

The runtime is implemented in the owner repo, but it is only launchable when
the shared workspace registry marks the profile `active`. While the profile is
`build-admitted`, `up` and `access` continue to fail closed.

## Runtime Boundary

Runtime state model:

- `persistent`

Persistent is selected because service-mode CGG will hold admission metadata,
artifact custody metadata, packet receipts, and audit-ledger state during
long-running enterprise context governance work. Shared smoke must remain
read-only. If mutating runtime smoke is needed later, create a disposable
companion profile instead of writing test traffic into the persistent lane.

## Operator Actions

Use launch and access actions from the shared platform runner only after the
workspace registry marks the profile `active`:

- `make devint-up PROFILE=context-governance-gateway`
- `make devint-status PROFILE=context-governance-gateway`
- `make devint-access PROFILE=context-governance-gateway`
- `make devint-smoke PROFILE=context-governance-gateway`
- `make devint-down PROFILE=context-governance-gateway`
- `make devint-reset PROFILE=context-governance-gateway`
- `make devint-promote-check PROFILE=context-governance-gateway`

Current lifecycle behavior:

- `status` reports the recorded runtime shape.
- `up` creates the namespace, local secrets, PVCs, PostgreSQL, MinIO, API,
  worker, and API service only when the lifecycle is `active`.
- `access` port-forwards the API to `http://localhost:18280`.
- `smoke` is read-only. In `active`, it reads health, readiness, packet,
  receipt, manifest, dashboard, metrics, and trace surfaces from seeded safe
  devint context without writing new test traffic.
- `down` scales active runtime deployments to zero and preserves PVCs and
  local secrets.
- `reset` removes the active namespace and local state.
- `promote-check` explains the gates required before stage handoff.

## Smoke Scope

Build-admitted smoke is static and read-only. Active smoke is also read-only
against the persistent runtime. It proves:

- dev-integration build admission
- API readiness contract
- artifact custody model
- redaction policy gate
- packet receipt compatibility
- security custody review
- raw projection remains denied in the model-safe packet
- dashboard, metrics, and trace surfaces expose safe metadata only

It does not call an AI model, mutate platform state, or project raw artifacts
into model-safe packets.

## Stage Handoff Checks

The governed `stage` handoff is not ready until it proves:

- `active dev-integration profile admission`
- `API readiness contract`
- `artifact custody model`
- `redaction policy gate`
- `packet receipt compatibility`
- `security custody review`

These checks must mirror `stage_handoff.required_checks` in `profile.yaml` and
the workspace registry entry.

## Admission Gates

Before this profile can become `active`:

1. The owner repo must implement the API/service runtime and read-only smoke
   without replacing scanners, storage, observability, or model gateways.
2. `platform-engineering` must accept the concrete runtime commands,
   persistence behavior, ports, and suspend or reset behavior.
3. `security-architecture` must keep custody and trust-boundary review evidence
   current for the implemented runtime.
4. `workspace-governance` must register the profile as `active`.

Dev-integration is local evidence only. It is not governed stage or prod
deployment evidence.

## References

- `workspace-governance/contracts/developer-integration-policy.yaml`
- `workspace-governance/contracts/developer-integration-profiles.yaml`
- `workspace-governance/contracts/components.yaml`
- `docs/operating-model/local-cli.md`
- `docs/operating-model/dev-integration-service.md`
