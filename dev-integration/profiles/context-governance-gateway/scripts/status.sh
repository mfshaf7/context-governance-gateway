#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

validate_work_design_binding_context
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

binding_state="$(work_design_binding_state)"
if is_work_design_composition && [[ "${binding_state}" != "ready" ]]; then
  echo "refused: composed Work Design caller binding is ${binding_state}." >&2
  exit 3
fi
if ! is_work_design_composition && [[ "${binding_state}" == "stale" ]]; then
  echo "refused: a stale Work Design caller binding exists outside its composition lifetime." >&2
  exit 3
fi
