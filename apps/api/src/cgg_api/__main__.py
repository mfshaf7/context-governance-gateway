from __future__ import annotations

from .runtime import RuntimeSettings


def main() -> int:
    settings = RuntimeSettings.from_env()
    print("Context Governance Gateway API module")
    print(f"root: {settings.root}")
    print(f"runtime_profile_state: {settings.runtime_profile_state}")
    print("Run with the api extra installed: uvicorn cgg_api.app:app")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
