# Lifecycle Context Projection

## Scope

- ART work item: `#1164`
- Landing Unit: `delivery-1154-cgg-lifecycle-projection`
- Owner repo: `context-governance-gateway`
- Runtime lane: source contract only; activation deferred

## Change

CGG now implements an authenticated typed lifecycle-context projection and
readback contract for exact ART, repository, validation, and runtime sources.
It reuses the shared receipt-bound projection kernel and established context
pipeline for validation, replay, redaction, budgeting, custody, and receipts.

## Authority

- CGG owns source admission, redaction, budgeting, packet custody, and
  projection receipts.
- OOS owns source selection, lifecycle legality, action choice, execution,
  fallback policy, and Console-facing workflow semantics.
- Platform owns credential delivery, runtime composition, and activation.
- Security Architecture owns exact-source trust-boundary acceptance.
- The Governance Operations Console remains an OOS client.

## Security Evidence

- Identity: a dedicated allowlist and shared secret fail closed independently
  from Work Design and Refinement.
- Data: source contents and canonical source-list digest must match; raw
  content is omitted from replay bindings and responses.
- Safety: the response exposes only redacted, budgeted content and explicit
  truncation or unavailable-source signals.
- Replay: identical requests replay the original receipt-bound result;
  conflicting idempotency-key reuse is denied.
- Custody: packet, redaction-receipt, projection-receipt, artifact digest, and
  timeline remain bound.
- Authority: CGG cannot choose lifecycle actions, invoke models, mutate ART,
  mutate source, or choose a raw-context fallback.

## Runtime Impact

No Platform composition, secret delivery, OOS consumer wiring, or live
activation is included. The route remains unusable by default until the
sequenced consumer, Security, and Platform work supplies those boundaries.
Existing Work Design and Refinement contracts remain compatible.
