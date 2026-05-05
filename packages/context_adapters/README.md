# Context Adapters Package

`context_adapters` owns downstream packet and receipt adapter contracts for CGG.

Implemented now:

- WGCF evidence-input adapter for model-safe packet and receipt references.
- OOS workflow-context adapter for packet and receipt references.
- AI/operator packet adapters for LiteLLM, OpenClaw, Ollama, Codex-style agents,
  and human operators.
- shared non-authority metadata proving adapters cannot mutate ART, approve
  governance, route model traffic, or read raw artifacts.
- `contracts/schemas/adapter-envelope.schema.json` records the shared output
  contract for downstream adapter envelopes.

The package does not call WGCF, OOS, LiteLLM, OpenClaw, Ollama, Codex, or any
model provider. It only projects already model-safe CGG packets into downstream
consumer shapes.

Adapter outputs intentionally omit raw artifact paths. Consumers receive packet
digests, policy profile, redaction count, safe excerpts, and receipt references
needed for audit without raw context passthrough.
