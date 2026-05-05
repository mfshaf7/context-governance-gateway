#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

write_status_file
cat >"${SMOKE_SUMMARY}" <<EOF
context-governance-gateway proposed dev-integration smoke (read-only)

profile: ${PROFILE_ID}
lifecycle: proposed
runtime launchable: false
state root: ${STATE_ROOT}

static checks:
- dev-integration profile admission: proposed only
- API readiness contract: required before activation
- artifact custody model: required before activation
- redaction policy gate: required before activation
- packet receipt compatibility: required before activation
- security custody review: required before activation

No Kubernetes workload was started. No raw context was projected.
EOF

cat "${SMOKE_SUMMARY}"
