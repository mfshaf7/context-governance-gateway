from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OpaPolicyEngine:
    binary: str = "opa"
    policy_dir: Path = Path("policies/opa")

    def evaluate(self, *, package: str, input_document: dict[str, object]) -> dict[str, object]:
        raise NotImplementedError(
            "OPA/Rego evaluation is an explicit integration seam; this foundation records policy contracts "
            "without implementing a custom policy engine."
        )

    def status(self) -> dict[str, object]:
        return {
            "engine": "opa",
            "binary": self.binary,
            "policy_dir": str(self.policy_dir),
            "status": "not_configured",
        }
