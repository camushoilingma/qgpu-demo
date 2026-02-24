#!/usr/bin/env bash
# Deploy qGPU demo — sources .env and runs setup.
set -euo pipefail

source "$(dirname "$0")/.env"

echo "Setting up qGPU demo cluster (${CLUSTER_ID}) in ${REGION} ..."
bash "$(dirname "$0")/setup.sh" "${1:-half}"
