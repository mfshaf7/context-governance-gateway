#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

rm -rf "${STATE_ROOT}"
ensure_state_dirs
echo "profile: ${PROFILE_ID}"
echo "lifecycle: ${PROFILE_LIFECYCLE}"
echo "local state reset: ${STATE_ROOT}"
