from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cgg_api import ContextGatewayService, RuntimeGateError, RuntimeSettings
from context_storage import LocalContextStore, MinioS3ArtifactCustody, PostgresPgvectorMetadataStore, StorageSettings


class ServiceFoundationTests(unittest.TestCase):
    def test_build_admitted_runtime_denies_mutating_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = ContextGatewayService(
                RuntimeSettings(root=Path(tmp), runtime_profile_state="build-admitted")
            )

            self.assertFalse(service.readiness()["ready"])
            with self.assertRaises(RuntimeGateError):
                service.project_text("ERROR token API_TOKEN=secret-value", source_label="unit-test")

    def test_active_runtime_projects_text_and_reads_packet_receipt_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = ContextGatewayService(RuntimeSettings(root=root, runtime_profile_state="active"))

            result = service.project_text(
                "ERROR failed with API_TOKEN=secret-value\n",
                source_label="unit-test",
                profile_name="developer",
                budget_tokens=200,
            )

            packet = service.packet(str(result["artifact_id"]))
            receipt = service.receipt(str(result["artifact_id"]))
            manifest = service.manifest(str(result["artifact_id"]))

            self.assertEqual(packet["purpose"], "model-safe context packet")
            self.assertEqual(packet["admission_decision"]["raw_projection"], "denied")
            self.assertIn("<redacted:secret-env-var>", packet["safe_context_excerpt"])
            self.assertEqual(receipt["artifact_digest"], result["artifact_digest"])
            self.assertEqual(manifest["artifact_digest"], result["artifact_digest"])
            self.assertEqual(result["storage_record"]["backend"], "local-filesystem")

    def test_local_context_store_lists_and_reads_projection_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            service = ContextGatewayService(RuntimeSettings(root=root, runtime_profile_state="active"))
            result = service.project_text("plain context\n", source_label="unit-test")
            store = LocalContextStore(root)

            self.assertIn(result["artifact_id"], store.list_artifact_ids())
            self.assertEqual(store.get_packet(str(result["artifact_id"]))["artifact_digest"], result["artifact_digest"])

    def test_enterprise_storage_adapters_are_explicit_integration_seams(self) -> None:
        metadata = PostgresPgvectorMetadataStore(dsn="postgresql://example")
        custody = MinioS3ArtifactCustody(endpoint_url="http://minio.example", bucket="cgg")

        self.assertEqual(metadata.backend, "postgres-pgvector")
        self.assertEqual(custody.backend, "minio-s3")
        with self.assertRaises(NotImplementedError):
            metadata.record_projection({})
        with self.assertRaises(NotImplementedError):
            custody.put_bytes("artifact", b"data", content_type="text/plain")

    def test_storage_settings_select_local_and_external_backend_seams(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = StorageSettings()
            external = StorageSettings(
                metadata_backend="postgres-pgvector",
                artifact_backend="minio-s3",
                postgres_dsn="postgresql://example",
                s3_endpoint_url="http://minio.example",
                s3_bucket="cgg",
            )

            self.assertEqual(local.metadata_store(root).backend, "local-filesystem")
            self.assertEqual(local.artifact_custody(root).backend, "local-filesystem")
            self.assertEqual(external.metadata_store(root).backend, "postgres-pgvector")
            self.assertEqual(external.artifact_custody(root).backend, "minio-s3")


if __name__ == "__main__":
    unittest.main()
