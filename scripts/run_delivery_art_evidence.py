#!/usr/bin/env python3
"""Run bounded, base-owned Delivery ART evidence for this repository."""

from __future__ import annotations

import argparse
import compileall
import json
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    "packages/context_adapters/src",
    "packages/context_core/src",
    "packages/context_observability/src",
    "packages/context_policy/src",
    "packages/context_storage/src",
    "apps/api/src",
    "apps/cli/src",
    "apps/dashboard/src",
)


def configure_imports() -> None:
    for relative in reversed(SOURCE_ROOTS):
        sys.path.insert(0, str(REPO_ROOT / relative))


def run_tests() -> bool:
    configure_imports()
    suite = unittest.defaultTestLoader.discover(str(REPO_ROOT / "tests"))
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


def run_validation() -> bool:
    compiled = all(
        compileall.compile_dir(REPO_ROOT / relative, quiet=1)
        for relative in (*SOURCE_ROOTS, "tests")
    )
    json_valid = True
    for root in (REPO_ROOT / "contracts", REPO_ROOT / "profiles"):
        for candidate in root.rglob("*.json"):
            try:
                json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                print(f"{candidate.relative_to(REPO_ROOT)}: {error}", file=sys.stderr)
                json_valid = False
    return compiled and json_valid


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--tests", action="store_true")
    mode.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    passed = run_tests() if args.tests else run_validation()
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
