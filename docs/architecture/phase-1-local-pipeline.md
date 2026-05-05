# Phase 1 Local Pipeline

Phase 1 is a local context admission workflow. It captures raw operational
context, preserves it locally, runs deterministic detector and policy
admission, redacts risky material, projects a budgeted model-safe packet, emits
an operator receipt, and appends a local ledger event.

The local pipeline is:

```text
raw context -> normalize -> classify -> detect -> redact -> policy -> slice -> budget -> project -> audit
```

Runtime boundaries:

- No API service in Phase 1.
- No workers in Phase 1.
- No database-backed storage in Phase 1.
- No dashboard in Phase 1.
- No broker adapter or cross-repo runtime behavior in Phase 1.
- Those surfaces require dev-integration profile admission first.
- OPA, Presidio, Gitleaks, and TruffleHog are adapter seams in the foundation;
  they are not replaced by custom CGG implementations.
