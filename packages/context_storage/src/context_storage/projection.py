from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from context_core.workspace import cgg_workspace, ensure_workspace


class LocalContextProjectionStore:
    """Durable local replay and denial records for one projection boundary."""

    backend = "local-filesystem"

    def __init__(self, root: Path, *, namespace: str, route_base: str) -> None:
        self.root = root.resolve()
        self.namespace = namespace
        self.route_base = route_base.rstrip("/")
        ensure_workspace(self.root)

    def read(self, idempotency_key: str) -> dict[str, object] | None:
        path = self._path(idempotency_key)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def create(self, idempotency_key: str, record: dict[str, object]) -> bool:
        path = self._path(idempotency_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._encode(record)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return True

    def replace(self, idempotency_key: str, record: dict[str, object]) -> None:
        path = self._path(idempotency_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(self._encode(record))
        temporary.chmod(0o600)
        os.replace(temporary, path)

    def reference(self, idempotency_key: str) -> str:
        return f"{self.route_base}/{idempotency_key}"

    def record_denial(self, record: dict[str, object]) -> str:
        material = self._encode(record)
        digest = hashlib.sha256(material).hexdigest()
        path = cgg_workspace(self.root) / f"{self.namespace}-denials" / f"{digest}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                return f"cgg://{self.namespace}-denials/{digest}"
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(material)
                handle.flush()
                os.fsync(handle.fileno())
        return f"cgg://{self.namespace}-denials/{digest}"

    def _path(self, idempotency_key: str) -> Path:
        digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
        return cgg_workspace(self.root) / f"{self.namespace}-projections" / f"{digest}.json"

    @staticmethod
    def _encode(record: dict[str, object]) -> bytes:
        return (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
