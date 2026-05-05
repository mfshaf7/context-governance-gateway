#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ensure_state_dirs
cat >"${PROFILE_PROMOTION_NOTES}" <<EOF
# Context Governance Gateway Stage Handoff Notes

Session manifest:
- ${SESSION_FILE}

Generic promotion report:
- ${PROMOTION_REPORT}

Profile lifecycle:
- ${PROFILE_LIFECYCLE}

Before governed stage rehearsal:

1. Land CGG API/service runtime and read-only smoke in \`context-governance-gateway\`.
2. Land platform activation acceptance for the concrete runtime commands in \`platform-engineering\`.
3. Keep security custody and trust-boundary review evidence current in \`security-architecture\`.
4. Register the active dev-integration admission record in \`workspace-governance\`.
5. Prove the profile-owned checks:
$(stage_handoff_required_checks_markdown)

Dev-integration is local evidence only. It is not stage or prod deployment
evidence and must not be promoted directly.
EOF

if [[ -f "${PROMOTION_REPORT}" ]]; then
  cat "${PROMOTION_REPORT}"
  echo
fi
cat "${PROFILE_PROMOTION_NOTES}"
