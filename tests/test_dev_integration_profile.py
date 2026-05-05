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


if __name__ == "__main__":
    unittest.main()
