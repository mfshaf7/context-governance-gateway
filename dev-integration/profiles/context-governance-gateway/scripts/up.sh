#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_active_profile
need_cmd k3s
need_cmd python3

ensure_state_dirs
ensure_local_secrets
render_runtime_manifest

kubectl_cmd apply -f "${RENDERED_DIR}/cgg-runtime.yaml"
kubectl_cmd -n "${NAMESPACE}" rollout restart "deployment/${API_DEPLOYMENT}" >/dev/null 2>&1 || true
kubectl_cmd -n "${NAMESPACE}" rollout restart "deployment/${WORKER_DEPLOYMENT}" >/dev/null 2>&1 || true
wait_for_runtime_ready
seed_projection_if_needed

write_status_file
printf 'context-governance-gateway dev-integration profile ready\n'
printf 'namespace: %s\n' "${NAMESPACE}"
printf 'api: svc/%s\n' "${API_SERVICE}"
printf 'worker: deployment/%s\n' "${WORKER_DEPLOYMENT}"
printf 'postgres: svc/%s\n' "${POSTGRES_SERVICE}"
printf 'minio: svc/%s\n' "${MINIO_SERVICE}"
printf 'seed artifact: %s\n' "$(cat "${SEED_ARTIFACT_FILE}")"
