# Context Governance Gateway

`context-governance-gateway` is the implementation home for Operational Context Governance and Context Admission Control.

This is not a log platform, prompt compressor, LLM gateway, observability
backend, object store, or security scanner. Its purpose is to govern raw
operational context before that context reaches AI agents, operator workflows,
CI, or automation.

## Target Pipeline

```text
raw context
  -> capture
  -> normalize
  -> classify
  -> redact
  -> slice
  -> budget
  -> project
  -> audit
  -> model-safe/operator-safe context packet
```

## What This Repo Owns

- CLI and SDK implementation for context capture and packet projection.
- Deterministic normalization, classification, redaction, slicing, and
  budgeting logic.
- Context manifests, redaction reports, model-safe packets, operator receipts,
  artifact digests, and audit-ledger events.
- API, worker, local dev-integration storage proof, and later
  storage-adapter/downstream-adapter implementation after the relevant runtime
  lane gates are admitted.

## What This Repo Does Not Own

- Workspace contracts, maturity rules, or workspace-root routing.
- Workspace Governance Control Fabric validation planning, readiness, or ART
  mutation authority.
- Platform deployment authority, version pinning, promotion, or release gates.
- Security standards, security acceptance, or trust-boundary review output.
- Custom LLM gateway, custom scanner, custom observability backend, or custom
  object store implementations.

## Ownership Boundaries

- `workspace-governance` owns contracts, schemas, maturity rules, and context
  admission standards.
- `context-governance-gateway` owns the implementation of context capture,
  classification, redaction, projection, packets, receipts, and ledger events.
- `platform-engineering` owns approved deployment state, runtime profile
  admission, version pinning, promotion, and adoption gates.
- `security-architecture` owns trust-boundary review, sensitive-data custody
  expectations, and security acceptance.
- `operator-orchestration-service` owns broker and operator workflow adapters
  that may later consume CGG packets through governed integration.
- `workspace-governance-control-fabric` may consume compact context packets and
  receipts, but this repo does not replace WGCF.

## Security Binding

CGG handles sensitive operational context and AI-adjacent packet projection, so
active workspace admission depends on the security architecture binding:

- Security review checklist:
  [docs/reviews/security-review-checklist.md](https://github.com/mfshaf7/security-architecture/blob/main/docs/reviews/security-review-checklist.md)
- Current dated security review:
  [docs/reviews/components/2026-05-05-context-governance-gateway-phase-1-local-custody.md](https://github.com/mfshaf7/security-architecture/blob/main/docs/reviews/components/2026-05-05-context-governance-gateway-phase-1-local-custody.md)
- Service-mode security delta:
  [docs/reviews/components/2026-05-05-context-governance-gateway-service-mode-admission-gates.md](https://github.com/mfshaf7/security-architecture/blob/main/docs/reviews/components/2026-05-05-context-governance-gateway-service-mode-admission-gates.md)
- Active dev-integration security delta:
  [docs/reviews/components/2026-05-05-context-governance-gateway-active-devint-runtime.md](https://github.com/mfshaf7/security-architecture/blob/main/docs/reviews/components/2026-05-05-context-governance-gateway-active-devint-runtime.md)
- Service-mode security requirements:
  [docs/architecture/components/context-governance-gateway/service-mode-security-requirements.md](https://github.com/mfshaf7/security-architecture/blob/main/docs/architecture/components/context-governance-gateway/service-mode-security-requirements.md)
- AI security standard:
  [docs/standards/ai-security-and-governance.md](https://github.com/mfshaf7/security-architecture/blob/main/docs/standards/ai-security-and-governance.md)
- AI and agentic domain:
  [docs/architecture/domains/ai-and-agentic.md](https://github.com/mfshaf7/security-architecture/blob/main/docs/architecture/domains/ai-and-agentic.md)

## Current Phase

The current accepted ART scope is Phase 1 local foundation:

- local CLI workflow only
- local raw artifact preservation
- deterministic redaction and secret-like detection
- compact model-safe packet projection
- operator receipt generation
- local ledger append

Runtime-lane decision:

- Phase 1 is `local-only`.
- The `context-governance-gateway` `dev-integration` profile is
  `active`, which authorizes local-k3s service-shape proof through the shared
  platform runner.
- Active dev-integration is local evidence only. It does not authorize governed
  stage or production runtime, raw model projection, downstream adapters,
  debug override, or CGG approval authority.
- Profile activation is backed by runnable owner commands, read-only smoke,
  `platform-engineering` activation evidence, and current
  `security-architecture` active-devint evidence.

## Dev-Integration Profile

The active profile lives at:

- `dev-integration/profiles/context-governance-gateway/profile.yaml`
- `dev-integration/profiles/context-governance-gateway/README.md`

Current command behavior:

- `status` reports the active local dev-integration runtime shape.
- `up` creates the local-k3s namespace, PVCs, PostgreSQL, MinIO, API, worker,
  and API service only after the workspace registry marks the profile active.
- `access` port-forwards the API to `http://localhost:18280` only when active.
- `smoke` is read-only. Active smoke reads
  health, readiness, packet, receipt, manifest, dashboard, metrics, and trace
  surfaces from seeded safe devint context.
- `down` scales active deployments to zero while preserving persistent volumes.
- `reset` removes the active namespace and local state.
- `promote-check` lists the gates required before governed stage rehearsal.

Do not interpret the active dev-integration profile as governed stage or
production readiness. It is a local service-shape proof lane; governed runtime
launch still requires later platform promotion, security review, and release
gates.

## Service-Mode Source Contract

The current service-mode foundation adds source contracts only:

- `apps/api/src/cgg_api` exposes health, readiness, text admission, packet,
  receipt, and manifest lookup surfaces.
- Mutating admission is denied unless `CGG_RUNTIME_PROFILE_STATE=active`.
- `packages/context_storage` provides local filesystem custody plus explicit
  PostgreSQL/pgvector and MinIO/S3 integration seams.
- `packages/context_policy` provides the deterministic context-admission policy
  evaluator, detector registry, OPA seam, and Presidio/Gitleaks/TruffleHog
  scanner seams.
- `packages/context_adapters` provides downstream packet and receipt adapter
  contracts for WGCF, OOS, AI tools, and operators without mutation, approval,
  model-gateway, or raw-artifact authority.
- `packages/context_observability` provides Prometheus-compatible metric
  samples, OpenTelemetry-compatible span payloads, and operator dashboard view
  models from already governed packet/receipt/manifest metadata.
- `apps/dashboard` provides the bounded source surface for operator dashboard
  summaries; it is not yet a live Next.js deployment.
- The API reuses `ContextPipeline`; it does not create a second redaction,
  projection, packet, receipt, or ledger path.

## Safety Model

Default posture is deny raw model projection. If detection is uncertain or
secret-like material is found, the full artifact stays local or in the approved
artifact backend, while the model-safe packet receives only redacted,
budgeted, and policy-admitted context.

Enterprise mode must preserve auditability:

- raw artifact location
- artifact digest
- manifest
- redaction report
- context-admission policy decisions
- detector sources and unavailable external scanner integrations
- adapter envelopes for downstream consumers when packets are projected out of
  CGG
- observability and dashboard projections that expose only safe metadata, never
  raw context or raw artifact paths
- model-safe packet
- operator receipt
- ledger event

## Development

This repository is currently a governed foundation shell. Add implementation
only through the accepted ART plan and keep source changes tied to Review
Packet evidence when the work is source-backed.

## Phase 1 CLI

Install in editable mode:

```bash
python3 -m pip install -e .
```

Run without installation from the repo root:

```bash
PYTHONPATH=packages/context_core/src:packages/context_policy/src:apps/cli/src python3 -m cgg_cli init
PYTHONPATH=packages/context_core/src:packages/context_policy/src:apps/cli/src python3 -m cgg_cli run --profile developer --budget 2000 -- python3 -c "print('hello')"
```

Supported Phase 1 commands:

```bash
cgg init
cgg run --profile developer --budget 2000 -- <command>
cgg pack --path <file-or-directory> --budget 3000
cgg project --artifact <artifact-path> --profile developer
cgg inspect --packet <packet-path>
```

Generated local outputs:

- `.cgg/artifacts/raw/`
- `.cgg/artifacts/redacted/`
- `.cgg/manifests/`
- `.cgg/packets/`
- `.cgg/receipts/`
- `.cgg/ledger.jsonl`

The packet includes purpose, source command/path, timestamp, artifact digest,
failure summary, key signals, redactions, budget use, safe excerpt, and policy
profile. The receipt explains what was captured, what was redacted, what was
included, what was denied or suppressed, where the raw artifact is stored, the
digest, and the profile decision.
