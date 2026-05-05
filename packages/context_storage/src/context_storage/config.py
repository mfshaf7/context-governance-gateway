from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .adapters import ArtifactCustody, MetadataStore, MinioS3ArtifactCustody, PostgresPgvectorMetadataStore
from .local import LocalContextStore


@dataclass(frozen=True)
class StorageSettings:
    metadata_backend: str = "local"
    artifact_backend: str = "local"
    postgres_dsn: str | None = None
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None

    @classmethod
    def from_env(cls) -> "StorageSettings":
        return cls(
            metadata_backend=os.environ.get("CGG_METADATA_BACKEND", "local").strip() or "local",
            artifact_backend=os.environ.get("CGG_ARTIFACT_BACKEND", "local").strip() or "local",
            postgres_dsn=os.environ.get("CGG_POSTGRES_DSN"),
            s3_endpoint_url=os.environ.get("CGG_S3_ENDPOINT_URL"),
            s3_bucket=os.environ.get("CGG_S3_BUCKET"),
        )

    def metadata_store(self, root: Path) -> MetadataStore:
        if self.metadata_backend == "local":
            return LocalContextStore(root)
        if self.metadata_backend == "postgres-pgvector":
            if not self.postgres_dsn:
                raise ValueError("CGG_POSTGRES_DSN is required for postgres-pgvector metadata.")
            return PostgresPgvectorMetadataStore(dsn=self.postgres_dsn)
        raise ValueError(f"unsupported CGG metadata backend: {self.metadata_backend}")

    def artifact_custody(self, root: Path) -> ArtifactCustody:
        if self.artifact_backend == "local":
            return LocalContextStore(root)
        if self.artifact_backend == "minio-s3":
            if not self.s3_endpoint_url or not self.s3_bucket:
                raise ValueError("CGG_S3_ENDPOINT_URL and CGG_S3_BUCKET are required for minio-s3 custody.")
            return MinioS3ArtifactCustody(endpoint_url=self.s3_endpoint_url, bucket=self.s3_bucket)
        raise ValueError(f"unsupported CGG artifact backend: {self.artifact_backend}")
