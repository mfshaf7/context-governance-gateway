#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_active_profile
need_cmd k3s
wait_for_runtime_ready

echo "profile: ${PROFILE_ID}"
echo "namespace: ${NAMESPACE}"
echo "CGG API URL: http://localhost:${ACCESS_LOCAL_PORT}/healthz"
echo "CGG dashboard summary: http://localhost:${ACCESS_LOCAL_PORT}/v1/operator/dashboard.txt"
echo
echo "Keep this process running while you inspect the dev-integration API."
echo "Press Ctrl-C to close the access session."
echo

exec "${KUBECTL_CMD[@]}" -n "${NAMESPACE}" port-forward "svc/${API_SERVICE}" "${ACCESS_LOCAL_PORT}:8080"
