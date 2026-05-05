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
