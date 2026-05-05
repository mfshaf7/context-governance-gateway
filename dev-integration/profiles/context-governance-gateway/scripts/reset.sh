#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if is_active_profile && command -v k3s >/dev/null 2>&1; then
  kubectl_cmd delete namespace "${NAMESPACE}" --ignore-not-found=true
fi

rm -rf "${STATE_ROOT}"
ensure_state_dirs
echo "profile: ${PROFILE_ID}"
echo "lifecycle: ${PROFILE_LIFECYCLE}"
echo "local state reset: ${STATE_ROOT}"
if is_active_profile; then
  echo "runtime namespace reset: ${NAMESPACE}"
fi
