from __future__ import annotations

import re
from pathlib import Path


ERROR_RE = re.compile(
    r"\b(error|exception|traceback|failed|failure|fatal|panic|denied|unauthorized|timeout)\b",
    re.IGNORECASE,
)


def classify_text(text: str, *, source_type: str, source_label: str, exit_code: int | None = None) -> dict[str, object]:
    lines = text.splitlines()
    error_lines = []
    for index, line in enumerate(lines, start=1):
        if ERROR_RE.search(line):
            error_lines.append({"line": index, "text": line[:240]})
    signals = []
    if exit_code not in (None, 0):
        signals.append(f"command_exit_code:{exit_code}")
    if error_lines:
        signals.append(f"error_like_lines:{len(error_lines)}")
    if source_type == "path":
        suffix = Path(source_label).suffix.lower()
        if suffix:
            signals.append(f"file_extension:{suffix}")
    return {
        "source_type": source_type,
        "source_label": source_label,
        "line_count": len(lines),
        "byte_count": len(text.encode("utf-8", errors="replace")),
        "error_like_lines": error_lines[:20],
        "signals": signals,
    }


def summarize_failure(classification: dict[str, object], exit_code: int | None = None) -> dict[str, object]:
    error_lines = list(classification.get("error_like_lines") or [])
    return {
        "detected": bool(error_lines or (exit_code not in (None, 0))),
        "exit_code": exit_code,
        "error_like_line_count": len(error_lines),
        "sample": error_lines[:5],
    }
