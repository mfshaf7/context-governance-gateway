# Phase 1 Local Custody Threat Model

Primary risks:

- raw operational context contains secrets
- raw context is projected directly into a model packet
- redaction misses private endpoints or credentials
- ledger and receipts omit enough information to audit a projection decision

Phase 1 controls:

- raw artifacts are preserved locally under `.cgg/artifacts/raw/`
- secret-like findings deny raw projection by default
- model-safe packets contain redacted and budgeted excerpts only
- receipts explain what was captured, redacted, included, denied, and where the
  full artifact is stored
- ledger events preserve artifact id, digest, profile, packet path, receipt
  path, and raw projection decision
