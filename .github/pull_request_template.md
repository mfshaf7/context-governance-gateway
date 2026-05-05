## Summary

Describe the CGG behavior, contract, or documentation change.

## Governance Declaration

- Confirm whether this changes raw context capture, redaction, packet
  projection, receipts, audit ledger behavior, or service-mode admission.
- Confirm the change does not make CGG own workspace contracts, WGCF readiness,
  platform deployment authority, or security acceptance.

## Documentation Updates

- List README, AGENTS, architecture, ADR, threat model, operating model, or
  security-binding updates.
- State if no documentation update is required and why.

## Validation

- List local commands and CI-equivalent checks.
- Include profile, packet, receipt, or ledger evidence when applicable.

## Codex Review

Review for raw operational context leakage, model-safe packet admission,
redaction denial behavior, authority-boundary drift, and dev-integration
admission bypass.

## Review Gates

- Security binding updated when identity, secrets, artifact custody, AI
  boundary, or runtime posture changes.
- Platform handoff updated when service-mode runtime, persistent storage, or
  deployment shape changes.
