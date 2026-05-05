# Phase 1 Local Pipeline

Phase 1 is a local context admission workflow. It captures raw operational
context, preserves it locally, redacts risky material, projects a budgeted
model-safe packet, emits an operator receipt, and appends a local ledger event.

The local pipeline is:

```text
raw context -> normalize -> classify -> redact -> slice -> budget -> project -> audit
```

Runtime boundaries:

- No API service in Phase 1.
- No workers in Phase 1.
- No database-backed storage in Phase 1.
- No dashboard in Phase 1.
- No broker adapter or cross-repo runtime behavior in Phase 1.
- Those surfaces require dev-integration profile admission first.
