# Context Storage Package

This package owns storage and custody seams for CGG service mode.

Implemented now:

- `LocalContextStore` for Phase 1-compatible local filesystem custody under
  `.cgg/`
- local manifest, packet, receipt, and redacted-artifact lookup by
  `artifact_id`
- local byte custody helpers for service tests and offline development
- `StorageSettings` for selecting local or external storage backends from
  runtime configuration

Enterprise dependency seams:

- `PostgresPgvectorMetadataStore`
- `MinioS3ArtifactCustody`

Those classes are explicit integration boundaries. They raise
`NotImplementedError` until active runtime admission wires the real external
dependencies. This repo must not replace PostgreSQL, pgvector, MinIO, or S3
with a custom metadata engine or object store.
