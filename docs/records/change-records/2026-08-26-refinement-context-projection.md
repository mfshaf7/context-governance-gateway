# Refinement Context Projection

## Scope

- ART work item: `#1006`
- Landing Unit: `delivery-884-refinement-cgg-projection`
- Owner repo: `context-governance-gateway`
- Runtime lane: local `dev-integration` only

## Change

CGG now exposes a receipt-bound Refinement projection and readback contract.
The implementation reuses the established context pipeline and a shared
projection kernel while retaining separate Work Design and Refinement task,
credential, replay, denial, route, and storage boundaries.

## Authority

- CGG owns context admission, redaction, budgeting, packet custody, and
  projection receipts.
- OOS owns Refinement workflow semantics, model request orchestration,
  operator acceptance, and Delivery mutation.
- Platform owns logical model profile resolution, credential delivery, and
  runtime activation.
- Security Architecture owns trust-boundary acceptance under `#1012`.
- The Governance Operations Console calls OOS only and receives semantic data;
  this change does not alter approved visuals.

## Security Evidence

- AI boundary: projected content is model-safe; CGG cannot select or invoke a
  model and cannot approve a suggestion.
- Identity boundary: a dedicated Refinement caller allowlist and shared secret
  fail closed independently from Work Design.
- Data boundary: canonical request digests, source receipt binding, redaction
  receipts, byte/token budgets, and raw-projection denial are enforced.
- Replay boundary: separate operation namespaces prevent cross-workflow key
  collision; conflicting reuse is denied.
- Delivery boundary: authority flags deny Delivery mutation and no OOS,
  OpenProject, Catalog, Repository, or Temporal write path is introduced.

## Runtime Impact

The route has no usable default credential. Runtime use remains blocked until
the sequenced Platform profile, Security review, composition, and activation
children complete. Existing Work Design route names, payloads, storage paths,
and response schemas remain compatible.
