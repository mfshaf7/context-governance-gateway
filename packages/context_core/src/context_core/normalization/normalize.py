from __future__ import annotations

import re

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = ANSI_ESCAPE_RE.sub("", value)
    return value.replace("\x00", "")
