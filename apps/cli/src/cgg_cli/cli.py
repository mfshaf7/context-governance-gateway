from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from context_core.pipeline import ContextPipeline
from context_core.profiles import PROFILE_NAMES


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cgg",
        description="Context Governance Gateway Phase 1 local CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create the local .cgg artifact workspace.")
    init_parser.add_argument("--json", action="store_true", help="Print machine-readable output.")

    run_parser = subparsers.add_parser("run", help="Capture a command and project a model-safe packet.")
    run_parser.add_argument("--profile", choices=PROFILE_NAMES, default="developer")
    run_parser.add_argument("--budget", type=int, default=2000)
    run_parser.add_argument("wrapped_command", nargs=argparse.REMAINDER)

    pack_parser = subparsers.add_parser("pack", help="Capture a file or directory and project a model-safe packet.")
    pack_parser.add_argument("--path", required=True)
    pack_parser.add_argument("--profile", choices=PROFILE_NAMES, default="developer")
    pack_parser.add_argument("--budget", type=int, default=3000)

    project_parser = subparsers.add_parser("project", help="Project an existing raw artifact into a model-safe packet.")
    project_parser.add_argument("--artifact", required=True)
    project_parser.add_argument("--profile", choices=PROFILE_NAMES, default="developer")
    project_parser.add_argument("--budget", type=int, default=3000)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a generated model-safe packet.")
    inspect_parser.add_argument("--packet", required=True)
    inspect_parser.add_argument("--json", action="store_true", help="Print the full packet JSON.")

    return parser


def _normalize_wrapped_command(raw: list[str]) -> list[str]:
    if raw and raw[0] == "--":
        raw = raw[1:]
    if not raw:
        raise SystemExit("cgg run requires a command after --")
    return raw


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    pipeline = ContextPipeline(Path.cwd())

    if args.command == "init":
        result = pipeline.init_workspace()
        if args.json:
            _print_json(result)
        else:
            print(f"initialized {result['workspace_path']}")
        return 0

    if args.command == "run":
        command = _normalize_wrapped_command(args.wrapped_command)
        result = pipeline.capture_command(command, profile_name=args.profile, budget_tokens=args.budget)
        _print_json(result)
        return int(result["command"]["exit_code"])

    if args.command == "pack":
        result = pipeline.pack_path(Path(args.path), profile_name=args.profile, budget_tokens=args.budget)
        _print_json(result)
        return 0

    if args.command == "project":
        result = pipeline.project_artifact(Path(args.artifact), profile_name=args.profile, budget_tokens=args.budget)
        _print_json(result)
        return 0

    if args.command == "inspect":
        packet_path = Path(args.packet)
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        if args.json:
            _print_json(packet)
            return 0
        print(f"packet: {packet_path}")
        print(f"purpose: {packet.get('purpose')}")
        print(f"profile: {packet.get('policy_profile')}")
        print(f"digest: {packet.get('artifact_digest')}")
        print(f"redactions: {len(packet.get('redactions_applied', []))}")
        print(f"estimated_tokens: {packet.get('budget', {}).get('estimated_tokens')}")
        print(f"admission: {packet.get('admission_decision', {}).get('raw_projection')}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
