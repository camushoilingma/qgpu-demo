#!/usr/bin/env bash
# Configure router agent to use existing Google/Gemini API secret

set -euo pipefail

SECRET_NAME="${1:-}"
SECRET_KEY="${2:-api-key}"

if [ -z "$SECRET_NAME" ]; then
    echo "Usage: $0 <secret-name> [secret-key-name]"
    echo ""
    echo "Example:"
    echo "  $0 google-api-key api-key"
    echo "  $0 gemini-secret GEMINI_API_KEY"
    echo ""
    echo "Available secrets in qgpu-demo namespace:"
    kubectl get secrets -n qgpu-demo 2>/dev/null | grep -v NAME || echo "  (none found)"
    exit 1
fi

# Check if secret exists
if ! kubectl get secret "$SECRET_NAME" -n qgpu-demo &>/dev/null; then
    echo "ERROR: Secret '$SECRET_NAME' not found in qgpu-demo namespace"
    echo ""
    echo "Available secrets:"
    kubectl get secrets -n qgpu-demo 2>/dev/null | grep -v NAME || echo "  (none found)"
    exit 1
fi

# Check if secret has the key
if ! kubectl get secret "$SECRET_NAME" -n qgpu-demo -o jsonpath="{.data.$SECRET_KEY}" &>/dev/null; then
    echo "WARNING: Secret '$SECRET_NAME' exists but key '$SECRET_KEY' not found"
    echo "Available keys in secret:"
    kubectl get secret "$SECRET_NAME" -n qgpu-demo -o json | jq -r '.data | keys[]' 2>/dev/null || echo "  (could not list keys)"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Configuring router agent to use secret: $SECRET_NAME (key: $SECRET_KEY)"

# Patch the deployment to use the correct secret
kubectl patch deployment router-agent -n qgpu-demo --type='json' -p="[
  {
    \"op\": \"replace\",
    \"path\": \"/spec/template/spec/containers/0/env/4/valueFrom/secretKeyRef/name\",
    \"value\": \"$SECRET_NAME\"
  },
  {
    \"op\": \"replace\",
    \"path\": \"/spec/template/spec/containers/0/env/4/valueFrom/secretKeyRef/key\",
    \"value\": \"$SECRET_KEY\"
  }
]" 2>/dev/null || {
    echo "Deployment not found. Deploying router first..."
    ./deploy_router.sh
    kubectl patch deployment router-agent -n qgpu-demo --type='json' -p="[
      {
        \"op\": \"replace\",
        \"path\": \"/spec/template/spec/containers/0/env/4/valueFrom/secretKeyRef/name\",
        \"value\": \"$SECRET_NAME\"
      },
      {
        \"op\": \"replace\",
        \"path\": \"/spec/template/spec/containers/0/env/4/valueFrom/secretKeyRef/key\",
        \"value\": \"$SECRET_KEY\"
      }
    ]"
}

echo "✅ Router agent configured to use secret: $SECRET_NAME"
echo "   The deployment will restart with the new secret reference."
