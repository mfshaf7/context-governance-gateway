# Agent Console Context Projection

## Scope

- ART work item: `#1244`
- Landing Unit: `delivery-1203-agent-console-cgg`
- Owner repo: `context-governance-gateway`
- Runtime lane: source contract only; activation deferred

## Change

CGG now implements an authenticated Agent Console context projection and
readback contract for one exact page- or workspace-scoped source candidate. It
reuses the shared receipt-bound projection kernel and established context
pipeline for validation, replay, redaction, budgeting, custody, and receipts.

## Authority

- CGG owns context admission, redaction, budgeting, packet custody, and
  projection receipts.
- OOS owns sessions, invocations, model calls, action decisions, owner-repo
  receipts, and Console-facing workflow semantics.
- Platform owns caller admission, credential delivery, runtime composition,
  and activation.
- Security Architecture owns exact-source trust-boundary acceptance.
- The Governance Operations Console remains an OOS client.

## Security Evidence

- Identity: a dedicated allowlist and shared secret fail closed independently
  from Work Design, Refinement, and lifecycle projections.
- Data: candidate content must match its declared digest; raw content is
  omitted from replay bindings and responses.
- Scope: workspace interaction requires a workspace-scoped candidate, while
  every candidate is bound to an exact source owner, reference, and revision.
- Safety: the response exposes only redacted, budgeted content with explicit
  truncation and authority signals.
- Replay: identical requests replay the original receipt-bound result;
  conflicting idempotency-key reuse is denied.
- Custody: packet, redaction-receipt, projection-receipt, artifact digest, and
  timeline remain bound.
- Authority: CGG cannot invoke a model, authorize actions, mutate owner state,
  or choose a raw-context fallback.

## Runtime Impact

No OOS consumer wiring, Platform credential delivery, Console live adapter, or
live commissioning is included. The route remains unusable by default until
the sequenced OOS, Platform, Console, and Security work supplies and accepts
those boundaries. Existing projection contracts remain compatible.
