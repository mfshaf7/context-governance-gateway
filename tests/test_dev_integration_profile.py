from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = REPO_ROOT / "dev-integration" / "profiles" / "context-governance-gateway"


class DevIntegrationProfileTests(unittest.TestCase):
    def run_common(
        self,
        script: str,
        *,
        env_overrides: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(env_overrides or {})
        return subprocess.run(
            ["bash", "-c", f'source "{PROFILE_ROOT / "scripts" / "common.sh"}"\n{script}'],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
        )

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

    def test_work_design_composition_requires_its_projected_binding(self) -> None:
        result = self.run_common(
            "validate_work_design_binding_context",
            env_overrides={"DEVINT_COMPOSITION_ID": "work-design-advice"},
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("did not supply its required CGG caller binding", result.stderr)

    def test_work_design_binding_is_rejected_outside_registered_composition(self) -> None:
        result = self.run_common(
            "validate_work_design_binding_context",
            env_overrides={"CGG_WORK_DESIGN_CALLER_SHARED_SECRET": "private-binding"},
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("requires the registered work-design-advice composition", result.stderr)

    def test_runtime_manifest_uses_optional_secret_reference_without_persisting_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            binding = "composition-private-binding"
            result = self.run_common(
                "ensure_state_dirs\nensure_local_secrets\nrender_runtime_manifest",
                env_overrides={
                    "CGG_WORK_DESIGN_CALLER_SHARED_SECRET": binding,
                    "DEVINT_COMPOSITION_ID": "work-design-advice",
                    "DEVINT_OPERATOR": "test-operator",
                    "DEVINT_PROFILE_LIFECYCLE": "active",
                    "DEVINT_STATE_ROOT": tmp,
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = (Path(tmp) / "rendered" / "cgg-runtime.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn("name: CGG_WORK_DESIGN_CALLER_SHARED_SECRET", manifest)
            self.assertIn("name: context-governance-gateway-work-design-caller", manifest)
            self.assertIn("optional: true", manifest)
            self.assertNotIn(binding, manifest)
            self.assertNotIn(binding, (Path(tmp) / "local-secrets.env").read_text())

    def test_composed_binding_is_projected_only_to_ephemeral_secret_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            capture = Path(tmp) / "secret.json"
            binding = "composition-private-binding"
            result = self.run_common(
                'kubectl_cmd() { cat >"${CAPTURE_PATH}"; }\nreconcile_work_design_binding',
                env_overrides={
                    "CAPTURE_PATH": str(capture),
                    "CGG_WORK_DESIGN_CALLER_SHARED_SECRET": binding,
                    "DEVINT_COMPOSITION_ID": "work-design-advice",
                    "DEVINT_OPERATOR": "test-operator",
                    "DEVINT_PROFILE_LIFECYCLE": "active",
                    "DEVINT_STATE_ROOT": tmp,
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            secret = json.loads(capture.read_text(encoding="utf-8"))
            self.assertEqual(
                secret["metadata"],
                {
                    "name": "context-governance-gateway-work-design-caller",
                    "namespace": "devint-context-governance-gateway-test-operator",
                },
            )
            self.assertEqual(
                secret["stringData"]["CGG_WORK_DESIGN_CALLER_SHARED_SECRET"],
                binding,
            )

    def test_binding_readiness_compares_without_printing_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_k3s = Path(tmp) / "k3s"
            fake_k3s.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_k3s.chmod(0o700)
            binding = "composition-private-binding"
            encoded = subprocess.run(
                ["base64"],
                input=binding,
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            result = self.run_common(
                f"kubectl_cmd() {{ printf '%s' '{encoded}'; }}\nwork_design_binding_state",
                env_overrides={
                    "CGG_WORK_DESIGN_CALLER_SHARED_SECRET": binding,
                    "DEVINT_COMPOSITION_ID": "work-design-advice",
                    "DEVINT_OPERATOR": "test-operator",
                    "DEVINT_PROFILE_LIFECYCLE": "active",
                    "DEVINT_STATE_ROOT": tmp,
                    "PATH": f"{tmp}:{os.environ['PATH']}",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "ready")
            self.assertNotIn(binding, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
