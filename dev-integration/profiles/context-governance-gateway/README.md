# Context Governance Gateway Dev-Integration Profile

This is the active local `dev-integration` profile for Context Governance
Gateway service-mode proof.

Lifecycle:

- `active`
- self-serve launchable through the shared platform runner
- local service-shape proof is authorized by workspace, platform, and security
  gates
- governed stage/prod runtime, raw model projection, downstream adapters,
  debug override, and CGG approval authority remain blocked

The profile exists so API, worker, persistent storage, dashboard metadata,
broker adapter, or cross-repo runtime work cannot start from chat memory or
local convenience. `active` authorizes only the local service-shape proof lane;
it does not make CGG a governed stage/prod service or approval authority.

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

The runtime is implemented in the owner repo and is launchable only while the
shared workspace registry marks the profile `active`.

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

Active smoke is read-only against the persistent runtime. It proves:

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

## Admission Evidence

This profile is active only because the following gates have evidence:

1. The owner repo must implement the API/service runtime and read-only smoke
   without replacing scanners, storage, observability, or model gateways.
2. `platform-engineering` must accept the concrete runtime commands,
   persistence behavior, ports, and suspend or reset behavior.
3. `security-architecture` must keep custody and trust-boundary review evidence
   current for the implemented runtime.
4. `workspace-governance` registered the profile as `active`.

Dev-integration is local evidence only. It is not governed stage or prod
deployment evidence.

## References

- `workspace-governance/contracts/developer-integration-policy.yaml`
- `workspace-governance/contracts/developer-integration-profiles.yaml`
- `workspace-governance/contracts/components.yaml`
- `docs/operating-model/local-cli.md`
- `docs/operating-model/dev-integration-service.md`
