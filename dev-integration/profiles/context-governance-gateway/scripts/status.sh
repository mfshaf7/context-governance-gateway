#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

print_status
echo
echo "intended components:"
echo "- context-governance-gateway-api"
echo "- context-governance-gateway-worker"
echo "- context-governance-gateway-postgresql"
echo "- context-governance-gateway-minio"

if is_active_profile && command -v k3s >/dev/null 2>&1; then
  echo
  echo "runtime objects:"
  kubectl_cmd -n "${NAMESPACE}" get deploy,svc,pvc --ignore-not-found=true || true
fi
