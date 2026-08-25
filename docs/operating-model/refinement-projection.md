# Refinement Context Projection

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
