# Refinement Context Projection

Selected metadata advice requires complete admitted field context. If budgeting
shortens that context, CGG returns `context_projection_oversized` rather than a
ready partial field projection. Narrow the selected context before a new request;
this does not raise the budget, expose raw data or grant model/action authority.

## Purpose

CGG projects the exact context needed by OOS for Refinement metadata advice.
It does not invoke a model, approve advice, mutate a Refinement packet, update
Delivery, manage repositories, or write Catalog values.

## Routes

```text
POST /v1/context/refinement/projections
GET  /v1/context/refinement/projections/{idempotency_key}
```

The POST body follows
`contracts/schemas/refinement-context-projection-request.schema.json`. Its
`assist_request` is the OOS `oos.delivery-refinement.v1` assist request. The
CGG wrapper adds only the workflow session, execution, idempotency, request
time, budget, and canonical assist-request digest required for governed
projection and replay.

The ready response follows
`contracts/schemas/refinement-context-projection-result.schema.json`. It
contains model-safe content and digest-bound packet, redaction receipt, and
projection receipt references. The response authority flags remain false for
model invocation, suggestion approval, and Delivery mutation.

## Admission

The approved unpublished continuity extension accepts optional owner-supplied
`work_context` beside the unchanged `assist_request`. It contains canonical
selected-node/ancestor narratives and explicit coverage, bound to that same
package, source revision and Work Design receipt. It supplies no read or edit
authority. CGG validates source/selection identity, admits/redacts the complete
content and binds it into `context_digest` and the projection request digest.
`assist_request_digest` continues to bind only the original field request.
Absent optional context preserves the previous wire and digest behavior.
Malformed, foreign, duplicate-node or budget-shortened input is denied; no
reference fetch or document retrieval is added. Deploy before the dependent
OOS consumer through the existing reviewed complete-runtime path.

The boundary is fail-closed unless all of these are true:

- `CGG_RUNTIME_PROFILE_STATE=active`
- the caller is listed by `CGG_REFINEMENT_ALLOWED_CALLERS`
- `CGG_REFINEMENT_CALLER_SHARED_SECRET` is configured and matches
- the request matches the OOS Refinement contract and its canonical digest
- the request is within the admitted age, byte, and token budgets
- the resulting CGG packet is redaction-safe and does not allow raw projection

The later Platform profile and composition Landing Units own credential
delivery and runtime activation. Standalone CGG source does not provide a
default secret or bypass.

## Replay And Recovery

Each idempotency key is bound to the canonical request plus caller identity.
An identical request replays its original projection. Conflicting reuse is
denied. A current pending record blocks duplicate execution; a stale pending
or retryable failed record may be recovered without changing the request
binding. Refinement records use their own storage namespace and cannot collide
with Work Design records.

## Evidence And Audit

The projection preserves:

- caller, operator, Delivery package, source revision, packet revision, and
  source Work Design receipt binding
- selected target field and node identifiers
- canonical request and artifact digests
- packet, redaction-receipt, and projection-receipt references
- requested and projected timestamps
- bounded denial records that do not copy submitted context or credentials

The Governance Operations Console remains an OOS client. It must not call this
CGG route directly or interpret CGG as advice authority.

## Paired maintenance: selected drafts and planning facts

The maintenance extension admits bounded optional `related_drafts` in the assist
request and optional `metadata`, `planning_rules` and node planning snapshots in
the owner work context. The existing OOS caller owns canonical field/selection
validation; CGG checks the closed shapes, unique field/node identities, matching
source/receipt, selected-node coverage and correspondence of supplied drafts.
Draft values remain explicitly unaccepted operator data, not instructions or
canonical facts. All enriched input passes the same redaction and complete
context budget. Changed drafts or planning facts change context digests and
replay identity. An oversized complete context is refused, never silently cut.
No old caller is required to provide the new context. Related drafts cannot be
projected without their bound owner wrapper. All three authority flags remain
false; no Catalog, model or Delivery action is introduced.

Tracking: operator-approved maintenance, Landing Unit Decision
`child_isolated_landing_unit`, `refinement-advisor-context-20261119`. Gary authors
and the standing delegated human reviews this separate admission/runtime rollback
unit. The [paired source review](https://github.com/mfshaf7/security-architecture/blob/main/docs/reviews/components/2026-11-19-refinement-advisor-context.md)
retains source-vs-runtime evidence; publication is operator-approved. This existing operator surface is the CGG
maintenance tracking home; no new owner record or generic validator is introduced.


The metadata wrapper also admits optional `numeric_type` (`integer` or `decimal`)
only for number fields. It remains inside the same redacted, budgeted and
digest-bound context. Each metadata row carries that record's native choices,
not a whole-group intersection; OOS validates selection and permissions before
admission. This extension gives the model field facts without mutation authority.
