from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

from .artifacts.store import read_text_artifact
from .budgeting.budget import apply_budget
from .classification.classifier import classify_text, summarize_failure
from .hashing.digest import sha256_file
from .ledger.ledger import append_ledger_event
from .normalization.normalize import normalize_text
from .profiles import get_profile
from .projection.projector import collapse_repeated_lines, error_windows
from .workspace import cgg_workspace, ensure_workspace, new_artifact_id, safe_relative, utc_now_iso, write_json
from context_policy import evaluate_context_admission, scan_sensitive_context


class ContextPipeline:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def init_workspace(self) -> dict[str, str]:
        return ensure_workspace(self.root)

    def capture_command(self, command: list[str], *, profile_name: str, budget_tokens: int) -> dict[str, object]:
        self.init_workspace()
        artifact_id = new_artifact_id("run")
        captured_at = utc_now_iso()
        completed = subprocess.run(
            command,
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )
        command_display = " ".join(shlex.quote(part) for part in command)
        raw_text = "\n".join(
            [
                f"$ {command_display}",
                f"[captured_at] {captured_at}",
                f"[exit_code] {completed.returncode}",
                "",
                "[stdout]",
                completed.stdout,
                "[stderr]",
                completed.stderr,
            ]
        )
        raw_path = cgg_workspace(self.root) / "artifacts" / "raw" / f"{artifact_id}.txt"
        raw_path.write_text(raw_text, encoding="utf-8")
        result = self._project_raw(
            artifact_id=artifact_id,
            raw_path=raw_path,
            captured_at=captured_at,
            source={"type": "command", "command": command_display},
            profile_name=profile_name,
            budget_tokens=budget_tokens,
            exit_code=completed.returncode,
        )
        result["command"] = {"argv": command, "display": command_display, "exit_code": completed.returncode}
        return result

    def pack_path(self, path: Path, *, profile_name: str, budget_tokens: int) -> dict[str, object]:
        self.init_workspace()
        target = path if path.is_absolute() else self.root / path
        artifact_id = new_artifact_id("pack")
        captured_at = utc_now_iso()
        raw_text = read_text_artifact(target)
        raw_path = cgg_workspace(self.root) / "artifacts" / "raw" / f"{artifact_id}.txt"
        raw_path.write_text(raw_text, encoding="utf-8")
        return self._project_raw(
            artifact_id=artifact_id,
            raw_path=raw_path,
            captured_at=captured_at,
            source={"type": "path", "path": str(target.resolve())},
            profile_name=profile_name,
            budget_tokens=budget_tokens,
        )

    def project_artifact(self, artifact_path: Path, *, profile_name: str, budget_tokens: int) -> dict[str, object]:
        self.init_workspace()
        source_path = artifact_path if artifact_path.is_absolute() else self.root / artifact_path
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        artifact_id = new_artifact_id("artifact")
        captured_at = utc_now_iso()
        raw_path = cgg_workspace(self.root) / "artifacts" / "raw" / f"{artifact_id}{source_path.suffix or '.txt'}"
        shutil.copy2(source_path, raw_path)
        return self._project_raw(
            artifact_id=artifact_id,
            raw_path=raw_path,
            captured_at=captured_at,
            source={"type": "artifact", "path": str(source_path.resolve())},
            profile_name=profile_name,
            budget_tokens=budget_tokens,
        )

    def project_text(
        self,
        text: str,
        *,
        source_label: str,
        profile_name: str,
        budget_tokens: int,
        source_type: str = "api-text",
    ) -> dict[str, object]:
        self.init_workspace()
        artifact_id = new_artifact_id("artifact")
        captured_at = utc_now_iso()
        raw_path = cgg_workspace(self.root) / "artifacts" / "raw" / f"{artifact_id}.txt"
        raw_path.write_text(text, encoding="utf-8")
        return self._project_raw(
            artifact_id=artifact_id,
            raw_path=raw_path,
            captured_at=captured_at,
            source={"type": source_type, "label": source_label},
            profile_name=profile_name,
            budget_tokens=budget_tokens,
        )

    def _project_raw(
        self,
        *,
        artifact_id: str,
        raw_path: Path,
        captured_at: str,
        source: dict[str, object],
        profile_name: str,
        budget_tokens: int,
        exit_code: int | None = None,
    ) -> dict[str, object]:
        profile = get_profile(profile_name)
        raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
        normalized = normalize_text(raw_text)
        classification = classify_text(
            normalized,
            source_type=str(source["type"]),
            source_label=str(source.get("command") or source.get("path") or source.get("label") or raw_path),
            exit_code=exit_code,
        )
        redacted_text, redaction_report = scan_sensitive_context(normalized)
        collapsed_text, collapse_events = collapse_repeated_lines(redacted_text)
        digest = sha256_file(raw_path)

        if profile.include_error_windows:
            candidate_excerpt = error_windows(collapsed_text, context_lines=profile.context_lines)
        else:
            candidate_excerpt = collapsed_text
        if profile.suppress_excerpt_on_findings and redaction_report["finding_count"]:
            candidate_excerpt = (
                "Raw context excerpt suppressed by enterprise profile because sensitive indicators were detected. "
                "Use the local redacted artifact, manifest, receipt, and digest for operator-side review."
            )
        safe_excerpt, budget_report = apply_budget(candidate_excerpt, budget_tokens)

        base = cgg_workspace(self.root)
        redacted_path = base / "artifacts" / "redacted" / f"{artifact_id}.txt"
        manifest_path = base / "manifests" / f"{artifact_id}.manifest.json"
        packet_path = base / "packets" / f"{artifact_id}.packet.json"
        receipt_path = base / "receipts" / f"{artifact_id}.receipt.json"
        redaction_report_path = base / "manifests" / f"{artifact_id}.redaction-report.json"

        redacted_path.write_text(collapsed_text, encoding="utf-8")

        failure_summary = summarize_failure(classification, exit_code=exit_code)
        policy_evaluation = evaluate_context_admission(
            profile=profile,
            redaction_report=redaction_report,
        )
        admission_decision = policy_evaluation.admission_decision

        manifest = {
            "schema_version": 1,
            "artifact_id": artifact_id,
            "captured_at": captured_at,
            "source": source,
            "artifact_digest": digest,
            "raw_artifact_path": safe_relative(raw_path, self.root),
            "redacted_artifact_path": safe_relative(redacted_path, self.root),
            "redaction_report_path": safe_relative(redaction_report_path, self.root),
            "packet_path": safe_relative(packet_path, self.root),
            "receipt_path": safe_relative(receipt_path, self.root),
            "classification": classification,
            "profile": profile.name,
            "budget": budget_report,
            "detectors": {
                "sources": redaction_report.get("detector_sources", []),
                "unavailable_integrations": redaction_report.get("unavailable_integrations", []),
            },
            "policy": policy_evaluation.to_dict(),
        }
        packet = {
            "schema_version": 1,
            "purpose": "model-safe context packet",
            "source": source,
            "captured_at": captured_at,
            "artifact_digest": digest,
            "failure_summary": failure_summary,
            "key_relevant_signals": classification["signals"],
            "redactions_applied": redaction_report["findings"],
            "token_output_budget_used": budget_report,
            "budget": budget_report,
            "safe_context_excerpt": safe_excerpt,
            "policy_profile": profile.name,
            "policy_profile_purpose": profile.purpose,
            "admission_decision": admission_decision,
            "context_admission": policy_evaluation.to_dict(),
            "artifact_paths": {
                "raw": safe_relative(raw_path, self.root),
                "redacted": safe_relative(redacted_path, self.root),
                "manifest": safe_relative(manifest_path, self.root),
                "receipt": safe_relative(receipt_path, self.root),
            },
        }
        receipt = {
            "schema_version": 1,
            "artifact_id": artifact_id,
            "what_was_captured": source,
            "what_was_removed_or_redacted": redaction_report["findings"],
            "what_was_included_in_packet": {
                "safe_context_excerpt": True,
                "failure_summary": failure_summary,
                "key_relevant_signals": classification["signals"],
            },
            "what_was_denied_or_suppressed": {
                "raw_projection": admission_decision["raw_projection"],
                "collapse_events": collapse_events,
                "budget_truncated": budget_report["truncated"],
            },
            "full_artifact_location": safe_relative(raw_path, self.root),
            "artifact_digest": digest,
            "policy_profile_decision": admission_decision,
        }
        redaction_report_payload = {
            "schema_version": 1,
            "artifact_id": artifact_id,
            "artifact_digest": digest,
            "report": redaction_report,
        }

        write_json(manifest_path, manifest)
        write_json(packet_path, packet)
        write_json(receipt_path, receipt)
        write_json(redaction_report_path, redaction_report_payload)
        append_ledger_event(
            base / "ledger.jsonl",
            {
                "schema_version": 1,
                "event_type": "context.projected",
                "artifact_id": artifact_id,
                "captured_at": captured_at,
                "artifact_digest": digest,
                "profile": profile.name,
                "packet_path": safe_relative(packet_path, self.root),
                "receipt_path": safe_relative(receipt_path, self.root),
                "raw_projection": admission_decision["raw_projection"],
            },
        )

        return {
            "artifact_id": artifact_id,
            "artifact_digest": digest,
            "manifest_path": safe_relative(manifest_path, self.root),
            "packet_path": safe_relative(packet_path, self.root),
            "receipt_path": safe_relative(receipt_path, self.root),
            "redacted_artifact_path": safe_relative(redacted_path, self.root),
            "raw_artifact_path": safe_relative(raw_path, self.root),
            "redaction_findings": redaction_report["finding_count"],
            "admission_decision": admission_decision,
        }
