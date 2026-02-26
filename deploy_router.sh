#!/usr/bin/env bash
# Deploy router agent service to Kubernetes cluster

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================"
echo "  Deploying Router Agent Service"
echo "============================================"
echo

# Check kubectl
if ! command -v kubectl &>/dev/null; then
    echo "ERROR: kubectl not found"
    exit 1
fi

# Read router service code
ROUTER_CODE=$(cat "$SCRIPT_DIR/router_service.py" | base64 | tr -d '\n')

# Create/update ConfigMap with router code
echo "[1/4] Creating ConfigMap with router service code..."
kubectl create configmap router-agent-code \
    --from-file=router_service.py="$SCRIPT_DIR/router_service.py" \
    -n qgpu-demo \
    --dry-run=client -o yaml | kubectl apply -f -

# Check for existing Gemini/Google API secret
GEMINI_SECRET_NAME="${GEMINI_SECRET_NAME:-gemini-api-key}"
GEMINI_SECRET_KEY="${GEMINI_SECRET_KEY:-api-key}"

if kubectl get secret "$GEMINI_SECRET_NAME" -n qgpu-demo &>/dev/null; then
    echo "[2/4] Using existing secret: $GEMINI_SECRET_NAME"
    echo "      Secret key: $GEMINI_SECRET_KEY"
elif [ -f "$HOME/secrets/googleapi" ]; then
    echo "[2/4] Loading Google API key from ~/secrets/googleapi..."
    GEMINI_KEY=$(cat "$HOME/secrets/googleapi" | tr -d '\n\r ')
    if [ -n "$GEMINI_KEY" ]; then
        kubectl create secret generic "$GEMINI_SECRET_NAME" \
            --from-literal="$GEMINI_SECRET_KEY=$GEMINI_KEY" \
            -n qgpu-demo \
            --dry-run=client -o yaml | kubectl apply -f -
        echo "      ✅ Secret created from ~/secrets/googleapi"
    else
        echo "      ⚠️  googleapi file is empty"
    fi
elif [ -n "${GEMINI_API_KEY:-}" ]; then
    echo "[2/4] Creating Gemini API key secret from environment variable..."
    kubectl create secret generic "$GEMINI_SECRET_NAME" \
        --from-literal="$GEMINI_SECRET_KEY=$GEMINI_API_KEY" \
        -n qgpu-demo \
        --dry-run=client -o yaml | kubectl apply -f -
else
    echo "[2/4] No Gemini API key found"
    echo "      Router will work but Gemini routing will be disabled"
    echo "      To enable, run: ./load_secrets.sh"
fi

# Apply router deployment
echo "[3/4] Deploying router agent..."
kubectl apply -f "$SCRIPT_DIR/k8s/router-agent.yaml"

# Update deployment with secret name if custom
if [ -n "${GEMINI_SECRET_NAME:-}" ] && [ "$GEMINI_SECRET_NAME" != "gemini-api-key" ]; then
    echo "      Updating deployment to use secret: $GEMINI_SECRET_NAME"
    kubectl set env deployment/router-agent \
        GEMINI_SECRET_NAME="$GEMINI_SECRET_NAME" \
        GEMINI_SECRET_KEY="${GEMINI_SECRET_KEY:-api-key}" \
        -n qgpu-demo
fi

# Wait for deployment
echo "[4/4] Waiting for router agent to be ready..."
kubectl wait --for=condition=available \
    deployment/router-agent \
    -n qgpu-demo \
    --timeout=120s || true

echo
echo "============================================"
echo "  Router Agent Deployment Complete"
echo "============================================"
echo
kubectl get pods -n qgpu-demo -l app=router-agent
kubectl get svc -n qgpu-demo router-agent
echo
echo "Router agent available at:"
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="ExternalIP")].address}')
echo "  http://${NODE_IP}:30090/v1/chat/completions"
echo
echo "Test with:"
echo "  curl http://${NODE_IP}:30090/v1/chat/completions \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"messages\":[{\"role\":\"user\",\"content\":\"Hello!\"}]}'"
