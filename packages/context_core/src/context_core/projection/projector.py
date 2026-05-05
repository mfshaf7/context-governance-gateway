from __future__ import annotations

import re


ERROR_RE = re.compile(
    r"\b(error|exception|traceback|failed|failure|fatal|panic|denied|unauthorized|timeout)\b",
    re.IGNORECASE,
)


def collapse_repeated_lines(text: str, keep: int = 3) -> tuple[str, list[dict[str, object]]]:
    lines = text.splitlines()
    collapsed: list[str] = []
    events: list[dict[str, object]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        count = 1
        while index + count < len(lines) and lines[index + count] == line:
            count += 1
        collapsed.extend([line] * min(count, keep))
        if count > keep:
            omitted = count - keep
            collapsed.append(f"[CGG collapsed {omitted} repeated line(s)]")
            events.append({"line": index + 1, "omitted": omitted, "text": line[:160]})
        index += count
    return "\n".join(collapsed) + ("\n" if text.endswith("\n") else ""), events


def error_windows(text: str, context_lines: int = 5, max_lines: int = 180) -> str:
    lines = text.splitlines()
    matches = [idx for idx, line in enumerate(lines) if ERROR_RE.search(line)]
    if not matches:
        return "\n".join(lines[:max_lines])
    selected: list[str] = []
    seen_lines: set[int] = set()
    # Put the failure line first so tight budgets do not cut off the signal
    # while preserving enough nearby context for local debugging.
    for match in matches:
        if selected:
            selected.append("[CGG omitted non-error context]")
        selected.append(f"[CGG error window around line {match + 1}]")
        selected.append(lines[match])
        seen_lines.add(match)
        start = max(0, match - context_lines)
        end = min(len(lines), match + context_lines + 1)
        for idx in range(start, end):
            if idx in seen_lines:
                continue
            selected.append(lines[idx])
            seen_lines.add(idx)
        if len(selected) >= max_lines:
            selected = selected[:max_lines]
            selected.append("[CGG omitted additional error context]")
            break
    return "\n".join(selected)
