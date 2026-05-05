#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if ! is_active_profile; then
  print_status
  echo
  echo "No active runtime exists for this build-admitted profile; no Kubernetes objects were changed."
  exit 0
fi

need_cmd k3s
ensure_state_dirs

kubectl_cmd -n "${NAMESPACE}" scale "deployment/${API_DEPLOYMENT}" --replicas=0 >/dev/null 2>&1 || true
kubectl_cmd -n "${NAMESPACE}" scale "deployment/${WORKER_DEPLOYMENT}" --replicas=0 >/dev/null 2>&1 || true
kubectl_cmd -n "${NAMESPACE}" scale "deployment/${POSTGRES_DEPLOYMENT}" --replicas=0 >/dev/null 2>&1 || true
kubectl_cmd -n "${NAMESPACE}" scale "deployment/${MINIO_DEPLOYMENT}" --replicas=0 >/dev/null 2>&1 || true

print_status
echo
echo "active runtime deployments scaled to zero; persistent volumes and local secrets were preserved."
