# Work Design Context Projection

This surface admits and projects the model-safe context that OOS will use for
governed Work Design advice. It is active only in the local `dev-integration`
CGG runtime.

It does not call a model, choose a provider, approve advice, or mutate Delivery.
The Governance Operations Console must call OOS, not CGG directly.

## Contract

OOS calls:

```text
POST /v1/context/work-design/projections
x-cgg-caller-id: operator-orchestration-service
x-cgg-caller-secret: <platform-supplied secret>
```

The request schema is
`contracts/schemas/work-design-context-projection-request.schema.json`. The
request binds:

- request, correlation, idempotency, workflow-session, and execution identity
- Delivery package and exact source revision
- operator identity
- Work Design task kind, `oos.delivery-work-design.v1` contract version,
  output schema, and `delivery-work-design-advisor-v1` logical profile
- source-context digest, request timestamp, and bounded output budget

The result schema is
`contracts/schemas/work-design-context-projection-result.schema.json`. A ready
result contains model-safe content plus packet, redaction-receipt, and
projection-receipt references. Those references bind the original caller and
task metadata without exposing raw artifact paths.

## Replay And Recovery

- The first admitted request reserves its idempotency key before projection.
- An identical completed retry returns the original artifact and marks the
  response as replayed.
- Reusing the key with a different request digest fails with
  `context_projection_replay_conflict`.
- A current in-flight duplicate returns `context_projection_in_progress`.
- A stale pending record or a retryable failed record can be recovered by the
  same request.
- OOS owns workflow cancellation. CGG does not mutate OOS cancellation state;
  an abandoned in-flight projection becomes recoverable after the bounded
  pending timeout.
- Admitted-shaped unauthorized, stale, oversized, semantically malformed, and
  replay-conflicting requests leave safe denial evidence without storing
  request content in the denial record. Transport-level schema failures return
  a bounded error and never echo submitted context.

## Runtime Limits

Defaults are deliberately bounded:

- admitted caller: `operator-orchestration-service`
- maximum context: 262144 UTF-8 bytes
- maximum packet budget: 8000 estimated tokens
- maximum request age: 300 seconds
- pending recovery timeout: 120 seconds

The corresponding environment variables are:

```text
CGG_WORK_DESIGN_ALLOWED_CALLERS
CGG_WORK_DESIGN_CALLER_SHARED_SECRET
CGG_WORK_DESIGN_MAX_CONTEXT_BYTES
CGG_WORK_DESIGN_MAX_BUDGET_TOKENS
CGG_WORK_DESIGN_MAX_REQUEST_AGE_SECONDS
CGG_WORK_DESIGN_PENDING_TIMEOUT_SECONDS
```

The route fails closed when the shared secret is absent or does not match. The
secret is compared in constant time and is never stored in packet, receipt,
denial, or replay records. Changing these values does not activate a model
route or grant a new caller. Caller admission and model-profile activation
remain separate Platform and Security decisions.

## Dev-Integration Binding

The integrated runtime is launched through the Platform-owned
`work-design-advice` composition. Platform generates one private caller value
for the composition lifetime and projects matching environment bindings to
OOS and this CGG profile.

CGG accepts its binding only when `DEVINT_COMPOSITION_ID` identifies that
registered composition. The profile writes the value directly to a dedicated
ephemeral Kubernetes secret, references it from the API deployment, reports
only `ready`, `missing`, `mismatch`, `absent`, or `stale`, and deletes the
secret on teardown. It does not copy the value into rendered manifests,
persistent CGG-local secrets, packets, receipts, or status output.

Launching the CGG profile by itself remains supported for owner-repo service
work. In that shape the Work Design binding is absent and the projection route
continues to deny caller authentication.
