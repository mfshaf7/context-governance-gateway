# Lifecycle Context Projection

## Purpose

CGG turns exact ART, repository, validation, and runtime source captures into a
bounded lifecycle-context packet for OOS. CGG admits and projects the context;
OOS remains responsible for deciding and executing the legal lifecycle action.

CGG does not choose an action, invoke a model, mutate ART, mutate source, or
decide whether a caller may bypass CGG with raw context.

## Routes

```text
POST /v1/context/lifecycle/projections
GET  /v1/context/lifecycle/projections/{idempotency_key}
```

The POST body follows
`contracts/schemas/lifecycle-context-projection-request.schema.json`. It binds
the workflow session, execution, Delivery item, Landing Unit, operator,
current lifecycle operation and state, budget, and a canonical digest over one
to sixteen typed source captures.

Each source uses one class:

- `art`
- `repository`
- `validation`
- `runtime`

An available source carries an exact source reference, revision, capture time,
content, and matching content digest. An unavailable source carries the exact
reference, capture time, and bounded reason instead of fabricated content.

The ready response follows
`contracts/schemas/lifecycle-context-projection-result.schema.json`. It returns
only redacted and budgeted content, safe source bindings without source
content, explicit unavailable-source and truncation signals, and digest-bound
packet, redaction-receipt, and projection-receipt references.

## Admission

The lifecycle boundary fails closed unless all of these are true:

- `CGG_RUNTIME_PROFILE_STATE=active`
- the caller is listed by `CGG_LIFECYCLE_ALLOWED_CALLERS`
- `CGG_LIFECYCLE_CALLER_SHARED_SECRET` is configured and matches
- source contents and the canonical source-list digest match
- the request is within the admitted age, byte, source-count, and token limits
- the resulting packet is redaction-safe and raw projection remains denied

The implemented source contract has no usable default credential. Platform
composition and controlled activation are separate later Landing Units.

## Replay And Custody

The idempotency key binds the canonical request and caller identity. Identical
retries return the original projection, including after a service restart.
Conflicting reuse is denied. Pending retry and recovery use the shared
receipt-bound projection kernel, while lifecycle replay and denial records use
their own storage namespace.

Raw submitted source content is retained only through CGG artifact custody.
The lifecycle replay record stores safe bindings, digests, receipt references,
and the projected packet, not a second raw source copy.

## Consumer Boundary

OOS is the default admitted caller and later owns source selection, lifecycle
legality, fallback policy, action execution, and Console-facing semantics. The
Governance Operations Console must call OOS rather than this route directly.
Security Architecture reviews the exact source and trust boundary before
activation; Platform owns credential delivery and runtime composition.
