# Context Governance Gateway Agent Notes

This repository owns implementation for Operational Context Governance and
Context Admission Control.

Read `README.md` first.

## What This Repo Owns

- context capture, normalization, classification, redaction, slicing,
  budgeting, projection, and audit-ledger implementation
- model-safe and operator-safe packet generation
- operator receipts, redaction reports, manifests, artifact digests, and local
  ledger behavior
- active local dev-integration API, worker, storage proof, and later governed
  storage adapter and downstream adapter implementation after the relevant
  runtime gates are admitted

## What This Repo Does Not Own

- workspace contracts or workspace-root routing
- Workspace Governance Control Fabric validation planning, readiness decisions,
  or ART mutation authority
- operator-orchestration-service broker or workflow-adapter authority
- platform deployment authority, release gates, or promotion state
- security standards, security acceptance, or review-output ownership
- custom LLM gateway, custom scanner, custom observability backend, or custom
  object store implementation

## Working Rules

- Keep Phase 1 local-only unless the ART plan explicitly activates service
  mode.
- Do not introduce API, worker, database-backed storage, dashboard, broker
  adapter, or cross-repo runtime behavior until the
  `context-governance-gateway` `dev-integration` profile is `build-admitted`
  or the workspace records an approved runtime-lane waiver.
- `build-admitted` authorizes bounded service implementation only. Its `up`,
  `access`, and shared-runner smoke paths must fail closed until workspace,
  platform, and security activation promote it to `active`.
- `active` authorizes only local-k3s dev-integration service-shape proof. It
  does not authorize governed stage/prod deployment, raw model projection,
  downstream adapters, debug override, or CGG approval authority.
- Preserve raw artifacts locally or in the approved artifact backend, but deny
  raw projection into model-safe packets by default.
- Keep security architecture binding references current in `README.md` and
  this file. Required refs are the security review checklist, the current dated
  CGG reviews, the service-mode requirements, the AI security standard, and
  the AI and agentic domain:
  - https://github.com/mfshaf7/security-architecture/blob/main/docs/reviews/security-review-checklist.md
  - https://github.com/mfshaf7/security-architecture/blob/main/docs/reviews/components/2026-05-05-context-governance-gateway-phase-1-local-custody.md
  - https://github.com/mfshaf7/security-architecture/blob/main/docs/reviews/components/2026-05-05-context-governance-gateway-service-mode-admission-gates.md
  - https://github.com/mfshaf7/security-architecture/blob/main/docs/reviews/components/2026-05-05-context-governance-gateway-active-devint-runtime.md
  - https://github.com/mfshaf7/security-architecture/blob/main/docs/architecture/components/context-governance-gateway/service-mode-security-requirements.md
  - https://github.com/mfshaf7/security-architecture/blob/main/docs/standards/ai-security-and-governance.md
  - https://github.com/mfshaf7/security-architecture/blob/main/docs/architecture/domains/ai-and-agentic.md
- Prefer deterministic detection first: command metadata, file extension,
  error patterns, secret-like regexes, token/JWT/private-key detection,
  internal hostname/private IP masking, env-var suppression, repeated log
  collapse, and error-window extraction.
- Integrate existing scanners, policy engines, storage, and observability
  tools later instead of building replacements.
- If a change affects identity, secrets, artifact custody, AI boundaries,
  platform deployment, or operator workflow, route the security and platform
  evidence in the same work.

## Review Guidelines

Treat these as high-risk review findings:

- raw operational context can reach a model-safe packet without redaction,
  budgeting, and policy admission
- the security binding, platform deployment boundary, or dev-integration admission
  posture drifts from the active workspace contract
- uncertain sensitive material is best-effort included instead of denied from
  model projection
- the repo starts owning workspace contracts, WGCF readiness, ART mutation,
  platform release, or security acceptance
- a custom LLM gateway, scanner, observability backend, or object store is
  implemented instead of using governed integrations
- API, worker, storage, dashboard, or broker-adapter work lands without a
  runtime-lane decision and `dev-integration` build-admission path
