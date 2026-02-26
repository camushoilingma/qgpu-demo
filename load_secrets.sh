#!/usr/bin/env bash
# Load API keys from ~/secrets folder into Kubernetes secrets

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SECRETS_DIR="${SECRETS_DIR:-$HOME/secrets}"

echo "============================================"
echo "  Loading Secrets from $SECRETS_DIR"
echo "============================================"
echo

# Check if secrets directory exists
if [ ! -d "$SECRETS_DIR" ]; then
    echo "ERROR: Secrets directory not found: $SECRETS_DIR"
    exit 1
fi

# Check kubectl
if ! command -v kubectl &>/dev/null; then
    echo "ERROR: kubectl not found"
    exit 1
fi

# Load Gemini/Google API key
if [ -f "$SECRETS_DIR/googleapi" ]; then
    echo "[1/3] Loading Google API key from $SECRETS_DIR/googleapi..."
    GEMINI_KEY=$(cat "$SECRETS_DIR/googleapi" | tr -d '\n\r ')
    
    if [ -z "$GEMINI_KEY" ]; then
        echo "  WARNING: googleapi file is empty"
    else
        kubectl create secret generic gemini-api-key \
            --from-literal=api-key="$GEMINI_KEY" \
            -n qgpu-demo \
            --dry-run=client -o yaml | kubectl apply -f -
        echo "  ✅ Google API key secret created/updated"
    fi
else
    echo "[1/3] googleapi file not found in $SECRETS_DIR"
    echo "      Skipping Google API key"
fi

# Load Google service account key (if needed)
if [ -f "$SECRETS_DIR/googlekey.json" ]; then
    echo "[2/3] Loading Google service account key..."
    kubectl create secret generic google-service-account \
        --from-file=key.json="$SECRETS_DIR/googlekey.json" \
        -n qgpu-demo \
        --dry-run=client -o yaml | kubectl apply -f -
    echo "  ✅ Google service account secret created/updated"
else
    echo "[2/3] googlekey.json not found (optional)"
fi

# Load other API keys if needed
if [ -f "$SECRETS_DIR/hf" ]; then
    echo "[3/3] Loading HuggingFace token..."
    HF_TOKEN=$(cat "$SECRETS_DIR/hf" | tr -d '\n\r ')
    kubectl create secret generic huggingface-token \
        --from-literal=token="$HF_TOKEN" \
        -n qgpu-demo \
        --dry-run=client -o yaml | kubectl apply -f -
    echo "  ✅ HuggingFace token secret created/updated"
else
    echo "[3/3] HuggingFace token not found (optional)"
fi

echo
echo "============================================"
echo "  Secrets Loaded"
echo "============================================"
echo
kubectl get secrets -n qgpu-demo | grep -E "(gemini|google|huggingface)" || echo "  (no matching secrets found)"
echo
echo "To use these secrets with the router agent:"
echo "  ./configure_router_secret.sh gemini-api-key api-key"
