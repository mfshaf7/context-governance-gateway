# Agent Console Context Projection

## Purpose

CGG turns one exact page- or workspace-scoped context candidate into a
redacted, budgeted, receipt-bound packet for an OOS-owned Agent Console
session. OOS remains responsible for session state, model invocation, action
decisions, and owner-repo receipts.

CGG does not select or invoke a model, authorize an action, mutate owner state,
or allow a caller to fall back to raw context.

## Routes

```text
POST /v1/context/agent-console/projections
GET  /v1/context/agent-console/projections/{idempotency_key}
```

The POST body follows
`contracts/schemas/agent-console-context-projection-request.schema.json`. It
binds the request, correlation, idempotency, Agent Console session, invocation,
operator, interaction mode, request time, and budget to one exact candidate.

The candidate records:

- `page` or `workspace` scope
- authoritative source owner, reference, and revision
- `live`, `source-projected`, or `synthetic` source mode
- capture time, source content, and matching SHA-256 digest

Workspace interaction rejects a page-scoped candidate. Focused interaction
may use either admitted scope because OOS, not CGG, owns the interaction
workflow and source choice.

The ready response follows
`contracts/schemas/agent-console-context-projection-result.schema.json`. It
contains only the redacted and budgeted projection, safe candidate bindings
without source content, explicit safety and authority flags, and digest-bound
packet, redaction-receipt, and projection-receipt references.

## Admission

The boundary fails closed unless all of these are true:

- `CGG_RUNTIME_PROFILE_STATE=active`
- the caller is listed by `CGG_AGENT_CONSOLE_ALLOWED_CALLERS`
- `CGG_AGENT_CONSOLE_CALLER_SHARED_SECRET` is configured and matches
- candidate content matches its declared digest
- capture and request times are valid and ordered
- the request remains within configured age, byte, and token limits
- the resulting packet is redaction-safe and raw projection remains denied

OOS is the only default admitted caller. The source contract has no usable
default credential; Platform activation is a later Landing Unit.

## Replay And Custody

The idempotency key binds the canonical request and caller identity. An
identical retry returns the original projection, including after a service
restart. Conflicting reuse is denied. Agent Console replay and denial records
use their own storage namespace and cannot collide with Work Design,
Refinement, or lifecycle records.

Raw candidate content is retained only through CGG artifact custody. Replay
bindings contain the source digest and exact source identity, not another raw
copy.

## Consumer Boundary

The Governance Operations Console calls OOS, not CGG. OOS owns session and
invocation semantics and presents only the CGG model-safe projection to the
governed AI caller. Platform owns credential delivery, runtime composition,
and live commissioning. Security Architecture reviews the exact source and
trust boundary before activation.
