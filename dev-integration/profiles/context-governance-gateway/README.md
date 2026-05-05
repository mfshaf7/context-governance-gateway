# Context Governance Gateway Dev-Integration Profile

This is the proposed `dev-integration` profile for Context Governance Gateway
service-mode admission.

Lifecycle:

- `proposed`
- not self-serve launchable
- runtime creation is denied until workspace, platform, and security admission
  promote the profile to `active`

The profile exists so API, worker, persistent storage, dashboard, broker
adapter, or cross-repo runtime work cannot start from chat memory or local
convenience. It records the intended runtime lane first, while Phase 1 remains
local CLI only.

## What It Will Run

When admitted, the profile is expected to run:

- a Context Governance Gateway API service
- a processing worker
- PostgreSQL metadata/search storage
- MinIO/S3-compatible artifact custody
- read-only smoke that proves admission health without projecting raw
  operational context

No service-mode runtime is created by this proposed profile today.

## Runtime Boundary

Runtime state model:

- `persistent`

Persistent is selected because service-mode CGG will hold admission metadata,
artifact custody metadata, packet receipts, and audit-ledger state during
long-running enterprise context governance work. Shared smoke must remain
read-only. If mutating runtime smoke is needed later, create a disposable
companion profile instead of writing test traffic into the persistent lane.

## Operator Actions

Use the shared platform runner only after the workspace registry marks the
profile `active`:

- `make devint-up PROFILE=context-governance-gateway`
- `make devint-status PROFILE=context-governance-gateway`
- `make devint-access PROFILE=context-governance-gateway`
- `make devint-smoke PROFILE=context-governance-gateway`
- `make devint-down PROFILE=context-governance-gateway`
- `make devint-reset PROFILE=context-governance-gateway`
- `make devint-promote-check PROFILE=context-governance-gateway`

Current proposed-profile behavior:

- `status` reports the recorded runtime shape.
- `smoke` performs static read-only profile checks only.
- `promote-check` explains the gates required before stage handoff.
- `up` and `access` fail closed because the runtime is not admitted yet.
- `down` and `reset` operate only on local profile state, not Kubernetes
  runtime objects.

## Smoke Scope

The proposed-profile smoke is static and read-only. It proves:

- dev-integration profile admission
- API readiness contract
- artifact custody model
- redaction policy gate
- packet receipt compatibility
- security custody review

It does not start Kubernetes workloads, create persistent volumes, call an AI
model, mutate platform state, or project raw artifacts into model-safe packets.

## Stage Handoff Checks

The governed `stage` handoff is not ready until it proves:

- `dev-integration profile admission`
- `API readiness contract`
- `artifact custody model`
- `redaction policy gate`
- `packet receipt compatibility`
- `security custody review`

These checks must mirror `stage_handoff.required_checks` in `profile.yaml` and
the workspace registry entry.

## Admission Gates

Before this profile can become `active`:

1. `workspace-governance` must register the profile as active.
2. `platform-engineering` must accept the runtime shape, persistence model, and
   shared runner wiring.
3. `security-architecture` must publish custody and trust-boundary review
   evidence.
4. The owner repo must implement the API/service runtime and read-only smoke
   without replacing scanners, storage, observability, or model gateways.

Dev-integration is local evidence only. It is not governed stage or prod
deployment evidence.

## References

- `workspace-governance/contracts/developer-integration-policy.yaml`
- `workspace-governance/contracts/developer-integration-profiles.yaml`
- `workspace-governance/contracts/components.yaml`
- `docs/operating-model/local-cli.md`
