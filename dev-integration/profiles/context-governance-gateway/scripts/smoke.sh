#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if is_active_profile; then
  need_cmd k3s
  wait_for_runtime_ready
  kubectl_cmd -n "${NAMESPACE}" exec -i "deployment/${API_DEPLOYMENT}" -- python - <<'PY' | tee "${SMOKE_SUMMARY}"
import json
import urllib.request
from pathlib import Path

root = Path("/var/lib/cgg")
packet_dir = root / ".cgg" / "packets"
packet_paths = sorted(packet_dir.glob("*.packet.json"))
if not packet_paths:
    raise SystemExit("No CGG seed packet is available; run the active profile up action first.")

artifact_id = packet_paths[-1].name.removesuffix(".packet.json")

def get_json(path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:8080{path}", timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))

def get_text(path: str) -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:8080{path}", timeout=10) as response:
        return response.read().decode("utf-8")

health = get_json("/healthz")
ready = get_json("/readyz")
packet = get_json(f"/v1/context/packets/{artifact_id}")
receipt = get_json(f"/v1/context/receipts/{artifact_id}")
manifest = get_json(f"/v1/context/manifests/{artifact_id}")
dashboard = get_json("/v1/operator/dashboard")
metrics = get_text("/v1/observability/metrics")
traces = get_json("/v1/observability/traces")

safe_excerpt = str(packet.get("safe_context_excerpt", ""))
assert health["status"] == "ok"
assert ready["ready"] is True
assert packet["admission_decision"]["raw_projection"] == "denied"
assert "<redacted:secret-env-var>" in safe_excerpt
assert "API_TOKEN=devint-seed-secret" not in safe_excerpt
assert receipt["artifact_digest"] == manifest["artifact_digest"]
assert "cgg_context_admission_packets_total" in metrics
assert traces["purpose"] == "otel-compatible-context-admission-spans"

print(
    json.dumps(
        {
            "profile": "context-governance-gateway",
            "lifecycle": "active",
            "runtime_ready": True,
            "artifact_id": artifact_id,
            "artifact_digest": manifest["artifact_digest"],
            "raw_projection": packet["admission_decision"]["raw_projection"],
            "redaction_marker_present": "<redacted:secret-env-var>" in safe_excerpt,
            "raw_secret_leaked": "API_TOKEN=devint-seed-secret" in safe_excerpt,
            "receipt_matches_manifest": receipt["artifact_digest"] == manifest["artifact_digest"],
            "dashboard_packet_count": dashboard["summary"]["packet_count"],
            "metrics_ready": "cgg_context_admission_packets_total" in metrics,
            "trace_count": len(traces["spans"]),
            "smoke_mode": "read-only",
        },
        indent=2,
        sort_keys=True,
    )
)
PY
  exit 0
fi

write_status_file
cat >"${SMOKE_SUMMARY}" <<EOF
context-governance-gateway build-admitted dev-integration smoke (read-only)

profile: ${PROFILE_ID}
lifecycle: ${PROFILE_LIFECYCLE}
runtime launchable: false
state root: ${STATE_ROOT}

static checks:
- dev-integration profile admission: build-admitted
- API readiness contract: required before activation
- artifact custody model: required before activation
- redaction policy gate: required before activation
- packet receipt compatibility: required before activation
- security custody review: required before activation

No Kubernetes workload was started. No raw context was projected.
EOF

cat "${SMOKE_SUMMARY}"
