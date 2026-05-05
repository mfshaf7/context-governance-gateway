# Operator Dashboard App

This app is the bounded source surface for the CGG operator dashboard.

The current ART slice does not deploy a live Next.js dashboard and does not
activate CGG service mode. It provides the operator-safe dashboard view model
and text rendering helpers that a future UI can consume after runtime
activation.

The dashboard shows:

- packet counts
- redaction counts
- policy profile counts
- raw projection decisions
- budget truncation counts
- failure counts
- artifact digests for audit correlation

The dashboard never shows:

- raw captured context
- model-safe context excerpts
- raw artifact locations
- direct debug override controls

Primary source helpers live in `context_observability.dashboard`.
