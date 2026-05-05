#!/usr/bin/env bash
set -euo pipefail

readonly PROFILE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly OWNER_REPO_ROOT="$(cd "${PROFILE_ROOT}/../../.." && pwd)"
readonly PROFILE_ID="${DEVINT_PROFILE_ID:-context-governance-gateway}"
readonly OPERATOR="${DEVINT_OPERATOR:-${USER:-operator}}"
readonly NAMESPACE="${DEVINT_NAMESPACE:-devint-${PROFILE_ID}-${OPERATOR}}"
readonly STATE_ROOT="${DEVINT_STATE_ROOT:-${OWNER_REPO_ROOT}/.dev-integration/${PROFILE_ID}/${OPERATOR}}"
readonly SESSION_FILE="${DEVINT_SESSION_FILE:-${STATE_ROOT}/session.yaml}"
readonly PROMOTION_REPORT="${DEVINT_PROMOTION_REPORT:-${STATE_ROOT}/promotion-report.yaml}"
readonly STATUS_FILE="${STATE_ROOT}/profile-status.txt"
readonly SMOKE_SUMMARY="${STATE_ROOT}/smoke-summary.txt"
readonly PROFILE_PROMOTION_NOTES="${STATE_ROOT}/profile-promotion-notes.md"

ensure_state_dirs() {
  mkdir -p "${STATE_ROOT}"
}

write_status_file() {
  ensure_state_dirs
  cat >"${STATUS_FILE}" <<EOF
profile: ${PROFILE_ID}
lifecycle: proposed
namespace: ${NAMESPACE}
operator: ${OPERATOR}
state root: ${STATE_ROOT}
runtime: not-admitted
launchable: false
EOF
}

stage_handoff_required_checks_markdown() {
  cat <<'EOF'
   - `dev-integration profile admission`
   - `API readiness contract`
   - `artifact custody model`
   - `redaction policy gate`
   - `packet receipt compatibility`
   - `security custody review`
EOF
}

print_status() {
  write_status_file
  cat "${STATUS_FILE}"
}

fail_not_active() {
  print_status
  echo
  echo "refused: ${PROFILE_ID} is proposed, not active; service-mode runtime launch is intentionally blocked." >&2
  exit 2
}
