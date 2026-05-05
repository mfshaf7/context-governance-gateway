# Context Governance Gateway

`context-governance-gateway` is the implementation home for Operational
Context Governance and Context Admission Control.

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
- Later API, worker, storage-adapter, and downstream adapter implementation
  once the runtime lane is admitted.

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
- `workspace-governance-control-fabric` may consume compact context packets and
  receipts, but this repo does not replace WGCF.

## Security Binding

CGG handles sensitive operational context and AI-adjacent packet projection, so
active workspace admission depends on the security architecture binding:

- Security review checklist:
  [docs/reviews/security-review-checklist.md](https://github.com/mfshaf7/security-architecture/blob/main/docs/reviews/security-review-checklist.md)
- Current dated security review:
  [docs/reviews/components/2026-05-05-context-governance-gateway-phase-1-local-custody.md](https://github.com/mfshaf7/security-architecture/blob/main/docs/reviews/components/2026-05-05-context-governance-gateway-phase-1-local-custody.md)
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
- The proposed `context-governance-gateway` `dev-integration` profile records
  the service-mode runtime shape, but is not self-serve launchable yet.
- The proposed profile must become active before this repo adds API service,
  worker, database-backed storage, operator workflow, dashboard, broker
  adapter, or cross-repo runtime behavior.
- Profile activation requires `workspace-governance`, `platform-engineering`,
  and `security-architecture` evidence.

## Dev-Integration Profile

The proposed profile lives at:

- `dev-integration/profiles/context-governance-gateway/profile.yaml`
- `dev-integration/profiles/context-governance-gateway/README.md`

Current command behavior:

- `status` reports the proposed runtime shape.
- `smoke` performs static read-only profile checks only.
- `promote-check` lists the gates required before governed stage rehearsal.
- `up` and `access` fail closed because service mode is not admitted yet.
- `down` and `reset` touch only local profile state.

Do not interpret this proposed profile as an active local-k3s runtime. It is an
admission contract and operator instruction surface for the next service-mode
front.

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
PYTHONPATH=packages/context_core/src:apps/cli/src python3 -m cgg_cli init
PYTHONPATH=packages/context_core/src:apps/cli/src python3 -m cgg_cli run --profile developer --budget 2000 -- python3 -c "print('hello')"
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
