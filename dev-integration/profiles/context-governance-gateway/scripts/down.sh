#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

print_status
echo
echo "No admitted runtime exists for this proposed profile; no Kubernetes objects were changed."
