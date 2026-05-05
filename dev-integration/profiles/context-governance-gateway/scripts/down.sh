#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

print_status
echo
echo "No active runtime exists for this build-admitted profile; no Kubernetes objects were changed."
