# ADR 0001: Context Governance Gateway, Not A Logging Tool Or AI Gateway

## Status

Accepted for Phase 1.

## Context

Operators and AI agents need compact context packets, but raw terminal, CI,
repo, and runtime output can be too large, noisy, and sensitive to send
directly to a model or automation flow.

## Decision

`context-governance-gateway` owns context admission control:

- capture raw context
- normalize and classify it
- redact risky values
- slice and budget the safe projection
- produce a model-safe packet
- produce an operator receipt
- preserve audit metadata and ledger events

It does not replace the LLM gateway, scanner, observability backend, object
store, WGCF, OOS, platform release authority, or security acceptance.

## Consequences

Phase 1 stays local and deterministic. Service mode, policy-engine integration,
scanner integration, object storage, downstream adapters, and dashboards remain
parked behind full-maturity work and dev-integration admission.
