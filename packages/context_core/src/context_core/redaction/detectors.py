from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RedactionRule:
    code: str
    pattern: re.Pattern[str]
    replacement: str
    description: str


RULES = (
    RedactionRule(
        "private-key-block",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
        "<redacted:private-key-block>",
        "Private key block",
    ),
    RedactionRule(
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "<redacted:jwt>",
        "JWT-like token",
    ),
    RedactionRule(
        "bearer-token",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{20,}"),
        "Bearer <redacted:bearer-token>",
        "Bearer token",
    ),
    RedactionRule(
        "github-token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
        "<redacted:github-token>",
        "GitHub token",
    ),
    RedactionRule(
        "aws-access-key",
        re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
        "<redacted:aws-access-key>",
        "AWS access key id",
    ),
    RedactionRule(
        "secret-env-var",
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASS|API_KEY|ACCESS_KEY|PRIVATE_KEY|CLIENT_SECRET)[A-Z0-9_]*)\s*=\s*([^\s\"']+)"
        ),
        r"\1=<redacted:secret-env-var>",
        "Sensitive environment assignment",
    ),
    RedactionRule(
        "json-secret-field",
        re.compile(
            r'(?i)("?(?:secret|token|password|api[_-]?key|client[_-]?secret|private[_-]?key)"?\s*:\s*)("[^"]+"|[^\s,}]+)'
        ),
        r"\1<redacted:secret-field>",
        "Sensitive key/value field",
    ),
    RedactionRule(
        "private-ip",
        re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b"),
        "<redacted:private-ip>",
        "Private IP address",
    ),
    RedactionRule(
        "internal-hostname",
        re.compile(r"\b[a-zA-Z0-9.-]+\.(?:internal|local|cluster\.local)\b"),
        "<redacted:internal-hostname>",
        "Internal hostname",
    ),
)


def redact_text(text: str) -> tuple[str, dict[str, object]]:
    findings: list[dict[str, object]] = []
    redacted = text
    for rule in RULES:
        redacted, count = rule.pattern.subn(rule.replacement, redacted)
        if count:
            findings.append(
                {
                    "code": rule.code,
                    "description": rule.description,
                    "count": count,
                    "action": "masked",
                }
            )
    return redacted, {
        "finding_count": sum(int(finding["count"]) for finding in findings),
        "findings": findings,
        "uncertain_sensitive_material": bool(findings),
    }
