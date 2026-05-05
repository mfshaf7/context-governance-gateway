# Context Policy Package

`context_policy` owns the CGG context-admission policy boundary.

The package keeps the current foundation deterministic while making the
enterprise integration points explicit:

- local deterministic detector orchestration remains active for Phase 1 and
  service-mode foundation work
- custom recognizers have a first-class adapter shape but are not configured by
  default
- Presidio, Gitleaks, and TruffleHog are represented as scanner adapter seams
  so CGG can integrate them later without replacing them
- OPA/Rego remains the intended policy engine, with current Rego contracts in
  `policies/opa/` and a fail-closed adapter seam until runtime activation

CGG does not implement a custom scanner or custom policy engine. It evaluates a
deterministic local policy now, records which external controls are not yet
configured, and keeps raw model projection denied when sensitive or uncertain
material is detected.
