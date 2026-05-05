from __future__ import annotations

import math


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def apply_budget(text: str, budget_tokens: int) -> tuple[str, dict[str, object]]:
    char_budget = max(0, budget_tokens) * 4
    if len(text) <= char_budget:
        return text, {
            "requested_tokens": budget_tokens,
            "estimated_tokens": estimate_tokens(text),
            "truncated": False,
            "included_characters": len(text),
        }
    suffix = "\n\n[CGG truncated]\n"
    allowed = max(0, char_budget - len(suffix))
    excerpt = text[:allowed].rstrip() + suffix
    return excerpt, {
        "requested_tokens": budget_tokens,
        "estimated_tokens": estimate_tokens(excerpt),
        "truncated": True,
        "included_characters": len(excerpt),
    }
