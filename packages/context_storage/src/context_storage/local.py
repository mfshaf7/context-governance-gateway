from __future__ import annotations

import json
from pathlib import Path

from context_core.workspace import cgg_workspace, ensure_workspace, safe_relative


class LocalContextStore:
    """Local filesystem custody used for Phase 1 compatibility and service tests."""

    backend = "local-filesystem"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        ensure_workspace(self.root)

    @property
    def workspace(self) -> Path:
        return cgg_workspace(self.root)

    def record_projection(self, projection: dict[str, object]) -> dict[str, object]:
        artifact_id = str(projection["artifact_id"])
        return {
            "artifact_id": artifact_id,
            "backend": self.backend,
            "manifest_path": projection.get("manifest_path"),
            "packet_path": projection.get("packet_path"),
            "receipt_path": projection.get("receipt_path"),
            "raw_artifact_path": projection.get("raw_artifact_path"),
            "redacted_artifact_path": projection.get("redacted_artifact_path"),
        }

    def list_artifact_ids(self) -> list[str]:
        packet_dir = self.workspace / "packets"
        return sorted(path.name.removesuffix(".packet.json") for path in packet_dir.glob("*.packet.json"))

    def get_manifest(self, artifact_id: str) -> dict[str, object]:
        return self._read_json(self.workspace / "manifests" / f"{artifact_id}.manifest.json")

    def get_packet(self, artifact_id: str) -> dict[str, object]:
        return self._read_json(self.workspace / "packets" / f"{artifact_id}.packet.json")

    def get_receipt(self, artifact_id: str) -> dict[str, object]:
        return self._read_json(self.workspace / "receipts" / f"{artifact_id}.receipt.json")

    def get_redaction_report(self, artifact_id: str) -> dict[str, object]:
        return self._read_json(self.workspace / "manifests" / f"{artifact_id}.redaction-report.json")

    def get_redacted_artifact_text(self, artifact_id: str) -> str:
        return (self.workspace / "artifacts" / "redacted" / f"{artifact_id}.txt").read_text(
            encoding="utf-8",
            errors="replace",
        )

    def put_bytes(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        target = self._safe_workspace_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return safe_relative(target, self.root)

    def get_bytes(self, key: str) -> bytes:
        return self._safe_workspace_path(key).read_bytes()

    def _read_json(self, path: Path) -> dict[str, object]:
        if not path.is_file():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8"))

    def _safe_workspace_path(self, key: str) -> Path:
        candidate = (self.workspace / key).resolve()
        candidate.relative_to(self.workspace.resolve())
        return candidate
