from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = REPO_ROOT / "dev-integration" / "profiles" / "context-governance-gateway"


class DevIntegrationProfileTests(unittest.TestCase):
    def test_profile_commands_exist_and_are_executable(self) -> None:
        expected = {
            "access.sh",
            "down.sh",
            "promote-check.sh",
            "reset.sh",
            "smoke.sh",
            "status.sh",
            "up.sh",
        }
        scripts = PROFILE_ROOT / "scripts"
        self.assertTrue((PROFILE_ROOT / "profile.yaml").is_file())
        self.assertTrue((PROFILE_ROOT / "README.md").is_file())
        for script_name in expected:
            script_path = scripts / script_name
            self.assertTrue(script_path.is_file(), script_name)
            mode = script_path.stat().st_mode
            self.assertTrue(mode & stat.S_IXUSR, script_name)

    def test_build_admitted_profile_status_and_smoke_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env.update(
                {
                    "DEVINT_OPERATOR": "test-operator",
                    "DEVINT_STATE_ROOT": tmp,
                }
            )
            status = subprocess.run(
                [str(PROFILE_ROOT / "scripts" / "status.sh")],
                check=True,
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertIn("lifecycle: build-admitted", status.stdout)
            self.assertIn("launchable: false", status.stdout)

            smoke = subprocess.run(
                [str(PROFILE_ROOT / "scripts" / "smoke.sh")],
                check=True,
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertIn("No Kubernetes workload was started", smoke.stdout)

    def test_build_admitted_profile_up_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env.update(
                {
                    "DEVINT_OPERATOR": "test-operator",
                    "DEVINT_STATE_ROOT": tmp,
                }
            )
            result = subprocess.run(
                [str(PROFILE_ROOT / "scripts" / "up.sh")],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("service-mode runtime launch is intentionally blocked", result.stderr)

    def test_active_lifecycle_can_be_read_from_shared_runner_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            session_file = state_root / "current-session.yaml"
            session_file.write_text("profile_lifecycle: active\n", encoding="utf-8")
            env = os.environ.copy()
            env.update(
                {
                    "DEVINT_OPERATOR": "test-operator",
                    "DEVINT_STATE_ROOT": str(state_root),
                    "DEVINT_SESSION_FILE": str(session_file),
                }
            )

            status = subprocess.run(
                [str(PROFILE_ROOT / "scripts" / "status.sh")],
                check=True,
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
            )

            self.assertIn("lifecycle: active", status.stdout)
            self.assertIn("runtime: active-local-k3s", status.stdout)
            self.assertIn("launchable: true", status.stdout)

    def test_active_up_requires_kubernetes_tooling_instead_of_static_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env.update(
                {
                    "DEVINT_OPERATOR": "test-operator",
                    "DEVINT_PROFILE_LIFECYCLE": "active",
                    "DEVINT_STATE_ROOT": tmp,
                    "PATH": "/bin:/usr/bin",
                }
            )

            result = subprocess.run(
                [str(PROFILE_ROOT / "scripts" / "up.sh")],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Missing required command: k3s", result.stderr)


if __name__ == "__main__":
    unittest.main()
