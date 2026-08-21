# Context Adapters Package

`context_adapters` owns downstream packet and receipt adapter contracts for CGG.

Implemented now:

- WGCF evidence-input adapter for model-safe packet and receipt references.
- OOS workflow-context adapter for packet and receipt references.
- One provider-neutral governed AI gateway handoff plus a separate human
  operator projection.
- shared non-authority metadata proving adapters cannot mutate ART, approve
  governance, route model traffic, or read raw artifacts.
- `contracts/schemas/adapter-envelope.schema.json` records the shared output
  contract for downstream adapter envelopes.
- `contracts/schemas/governed-ai-context-handoff.schema.json` records the
  exact three-field context object accepted by the platform gateway.

The package does not call WGCF, OOS, the governed AI gateway, or any model
provider. It only projects already model-safe CGG packets into downstream
consumer shapes. Model and provider selection remain platform responsibilities.

Adapter outputs intentionally omit raw artifact paths. Consumers receive packet
and receipt references, policy metadata where applicable, and safe excerpts
needed for audit without raw context passthrough. Packet and receipt digests
must agree before any paired projection is produced.

The governed AI handoff is dormant source contract only. It does not perform a
network call, select a logical model profile, obtain credentials, or authorize
runtime activation.
