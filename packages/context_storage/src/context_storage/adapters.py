from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class MetadataStore(Protocol):
    """Metadata/search storage boundary for manifests, packets, receipts, and ledger refs."""

    backend: str

    def record_projection(self, projection: dict[str, object]) -> dict[str, object]:
        """Record or index one projection result."""

    def get_manifest(self, artifact_id: str) -> dict[str, object]:
        """Read a context manifest by artifact id."""

    def get_packet(self, artifact_id: str) -> dict[str, object]:
        """Read a model-safe packet by artifact id."""

    def get_receipt(self, artifact_id: str) -> dict[str, object]:
        """Read an operator receipt by artifact id."""


class ArtifactCustody(Protocol):
    """Artifact custody boundary for raw and redacted artifact bytes."""

    backend: str

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> str:
        """Store bytes and return a durable reference."""

    def get_bytes(self, key: str) -> bytes:
        """Read bytes by key."""


@dataclass(frozen=True)
class PostgresPgvectorMetadataStore:
    """Integration seam for the enterprise metadata/search backend."""

    dsn: str
    backend: str = "postgres-pgvector"

    def record_projection(self, projection: dict[str, object]) -> dict[str, object]:
        raise NotImplementedError(
            "PostgreSQL/pgvector persistence is an external dependency adapter. "
            "Implement it during active runtime admission; do not replace it with a custom store."
        )

    def get_manifest(self, artifact_id: str) -> dict[str, object]:
        raise NotImplementedError(
            "PostgreSQL/pgvector lookup is an external dependency adapter. "
            "Implement it during active runtime admission; do not replace it with a custom store."
        )

    def get_packet(self, artifact_id: str) -> dict[str, object]:
        raise NotImplementedError(
            "PostgreSQL/pgvector lookup is an external dependency adapter. "
            "Implement it during active runtime admission; do not replace it with a custom store."
        )

    def get_receipt(self, artifact_id: str) -> dict[str, object]:
        raise NotImplementedError(
            "PostgreSQL/pgvector lookup is an external dependency adapter. "
            "Implement it during active runtime admission; do not replace it with a custom store."
        )


@dataclass(frozen=True)
class MinioS3ArtifactCustody:
    """Integration seam for S3-compatible artifact custody."""

    endpoint_url: str
    bucket: str
    backend: str = "minio-s3"

    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> str:
        raise NotImplementedError(
            "MinIO/S3 custody is an external dependency adapter. "
            "Implement it during active runtime admission; do not replace it with a custom object store."
        )

    def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError(
            "MinIO/S3 custody is an external dependency adapter. "
            "Implement it during active runtime admission; do not replace it with a custom object store."
        )
