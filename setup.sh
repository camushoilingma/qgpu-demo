#!/usr/bin/env bash
# Bootstrap the qGPU demo: configure kubectl, deploy manifests, verify pods.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/.env"

echo "============================================"
echo "  qGPU Demo — Cluster Setup"
echo "============================================"
echo

# ── 1. Check kubectl ──
echo "[1/6] Checking kubectl ..."
if ! command -v kubectl &>/dev/null; then
    echo "  kubectl not found. Installing ..."
    curl -LO "https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/$(uname -s | tr '[:upper:]' '[:lower:]')/$(uname -m)/kubectl"
    chmod +x kubectl
    sudo mv kubectl /usr/local/bin/
fi
echo "  kubectl $(kubectl version --client --short 2>/dev/null || kubectl version --client -o yaml | grep gitVersion | awk '{print $2}')"

# ── 2. Get kubeconfig ──
echo
echo "[2/6] Fetching kubeconfig for cluster ${CLUSTER_ID} ..."
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/qgpu-demo-config}"
mkdir -p "$(dirname "$KUBECONFIG_PATH")"

# Use tccli if available, otherwise try terraform output
if command -v tccli &>/dev/null; then
    tccli tke DescribeClusterKubeconfig \
        --ClusterId "$CLUSTER_ID" \
        --region "$REGION" \
        --output json | python3 -c "
import sys, json, base64
data = json.load(sys.stdin)
print(data['Kubeconfig'])" > "$KUBECONFIG_PATH"
else
    echo "  tccli not found. Trying terraform output ..."
    if [ -f "$SCRIPT_DIR/terraform/terraform.tfstate" ]; then
        terraform -chdir="$SCRIPT_DIR/terraform" output -raw kubeconfig > "$KUBECONFIG_PATH"
    else
        echo "  ERROR: No way to fetch kubeconfig. Install tccli or run terraform apply first."
        exit 1
    fi
fi

export KUBECONFIG="$KUBECONFIG_PATH"
echo "  Kubeconfig saved to $KUBECONFIG_PATH"

# ── 3. Verify nodes ──
echo
echo "[3/6] Waiting for GPU nodes ..."
for i in $(seq 1 30); do
    READY=$(kubectl get nodes --no-headers 2>/dev/null | grep -c " Ready" || true)
    if [ "$READY" -ge 1 ]; then
        echo "  $READY node(s) ready"
        break
    fi
    echo "  Waiting for nodes ... ($i/30)"
    sleep 10
done

kubectl get nodes -o wide
echo

# ── 4. Apply namespace ──
echo "[4/6] Creating namespace ..."
kubectl apply -f "$SCRIPT_DIR/k8s/namespace.yaml"

# ── 5. Deploy vLLM pods ──
echo
echo "[5/6] Deploying vLLM pods ..."
echo "  Choose deployment mode:"
echo "    full    — 1 pod with full GPU (baseline)"
echo "    half    — 2 pods sharing GPU (50% each)"
echo "    quarter — 1 pod with 25% GPU"
echo "    all     — deploy all configurations"
echo
MODE="${1:-half}"
echo "  Using mode: $MODE"

case "$MODE" in
    full)
        kubectl apply -f "$SCRIPT_DIR/k8s/vllm-full-gpu.yaml"
        ;;
    half)
        kubectl apply -f "$SCRIPT_DIR/k8s/vllm-half-gpu.yaml"
        ;;
    quarter)
        kubectl apply -f "$SCRIPT_DIR/k8s/vllm-quarter-gpu.yaml"
        ;;
    all)
        echo "  WARNING: deploying all configs requires enough GPU memory"
        kubectl apply -f "$SCRIPT_DIR/k8s/"
        ;;
    *)
        echo "  Unknown mode: $MODE (use full, half, quarter, or all)"
        exit 1
        ;;
esac

# ── 6. Wait for pods ──
echo
echo "[6/6] Waiting for pods to be ready ..."
kubectl -n qgpu-demo wait --for=condition=ready pod --all --timeout=300s 2>/dev/null || true

echo
echo "============================================"
echo "  Status"
echo "============================================"
echo
kubectl get pods -n qgpu-demo -o wide
echo
kubectl get svc -n qgpu-demo
echo
echo "  To benchmark, get the node's public IP and run:"
echo "    python3 benchmark.py --base-url http://<NODE_IP>:30081/v1"
echo
