from __future__ import annotations

from pathlib import Path


TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".css",
    ".csv",
    ".env",
    ".ini",
    ".js",
    ".json",
    ".log",
    ".md",
    ".py",
    ".rego",
    ".sh",
    ".sql",
    ".txt",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}


def read_text_artifact(path: Path, *, max_bytes_per_file: int = 512_000) -> str:
    if path.is_file():
        return _read_one_file(path, max_bytes_per_file=max_bytes_per_file)
    if not path.is_dir():
        raise FileNotFoundError(path)

    parts: list[str] = []
    for child in sorted(path.rglob("*")):
        if not child.is_file() or _skip_path(child):
            continue
        if child.suffix.lower() not in TEXT_SUFFIXES:
            continue
        relative = child.relative_to(path)
        parts.append(f"===== {relative} =====")
        parts.append(_read_one_file(child, max_bytes_per_file=max_bytes_per_file))
    return "\n".join(parts)


def _skip_path(path: Path) -> bool:
    names = set(path.parts)
    return bool({".git", ".cgg", "__pycache__", ".venv", "node_modules"} & names)


def _read_one_file(path: Path, *, max_bytes_per_file: int) -> str:
    data = path.read_bytes()[:max_bytes_per_file]
    text = data.decode("utf-8", errors="replace")
    if path.stat().st_size > max_bytes_per_file:
        text += "\n[CGG truncated file at per-file capture limit]\n"
    return text
