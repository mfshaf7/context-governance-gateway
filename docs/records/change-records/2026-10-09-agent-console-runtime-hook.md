# Agent Console Runtime Hook

## Summary

CGG's existing dev-integration profile can now consume the already-implemented
Agent Console projection through an explicit, composition-owned caller
binding. The route remains unusable for standalone launches and for the
existing composition until Platform supplies the activation flag, exact OOS
allowlist, and ephemeral caller credential.

## Classification

- area: Context Governance Gateway dev-integration integration hook
- type: source-only runtime adapter
- runtime impact: default-off; no activation in this change

## Ownership

- owner repo: `context-governance-gateway`
- related ART work: Platform Agent Console activation `#1246`

## Root Cause

Agent Console projection source landed under `#1244` with runtime activation
deliberately deferred to the later Platform Landing Unit. The active profile
therefore needed a fail-closed hook matching the existing composition-owned
credential pattern before Platform could activate the route.

## Source Changes

- accept the Agent Console credential only from `refinement-catalog` with an
  explicit activation flag and exact caller allowlist;
- project the credential through an ephemeral namespace Secret and optional
  pod reference without writing its value to manifests or profile state;
- report missing, mismatched, or stale binding state and remove the Secret when
  activation is absent;
- cover standalone denial, incomplete activation, safe manifest rendering, and
  ephemeral Secret projection in profile tests.

## Artifact And Deployment Evidence

Source-only owner integration hook. Platform `#1246` owns composition,
credential delivery, live commissioning, rollback, and operating evidence.

## Live Verification

Repo-local profile tests and validators prove default-off and secret-safe
behavior. No live Agent Console route is activated by this change.

## Follow-Up Actions

Platform `#1246` must supply the exact composition bindings only after the
planned Security gate and must prove positive, negative, restart, rollback,
and cleanup outcomes before operating-ready closure.
