# qGPU Demo — GPU Sharing on TKE

Run two different LLMs simultaneously on a single NVIDIA L20 GPU using Tencent Cloud's qGPU technology.

## Architecture

```
TKE Cluster (Managed K8s)
└── Native GPU Node Pool (1× L20 48GB)
    └── qGPU enabled (gpu-manager addon)
        ├── Pod A: vLLM + Qwen2.5-0.5B  (50% compute, 22GB VRAM) → :30081
        ├── Pod B: vLLM + Qwen2.5-1.5B  (50% compute, 22GB VRAM) → :30082
        └── Router Agent (LLM-powered routing service)        → :30090
```

## Quick Start

### Prerequisites

```bash
# Set your GPU node's external IP
export NODE_IP="<YOUR_NODE_EXTERNAL_IP>"

# Install dependencies
pip install aiohttp
```

### Test endpoints

```bash
curl http://${NODE_IP}:30081/v1/models   # Qwen2.5-0.5B
curl http://${NODE_IP}:30082/v1/models   # Qwen2.5-1.5B
```

### Run tests

```bash
python3 test.py health       # Check all services
python3 test.py quick        # 5 prompts through the router
python3 test.py full         # 15 prompts through the router
python3 test.py csv          # Save results to CSV
python3 test.py chat         # Interactive chat via router
python3 test.py ecommerce    # E-commerce demo (router + specialist)
```

## Router Agent Service

The router agent uses the 0.5B model to analyze each request and intelligently route it:

```
Client Request
    ↓
Router Agent (LLM-powered, :30090)
    ├─→ Simple Agent     (Qwen2.5-0.5B, :30081)  — quick queries
    ├─→ Specialist Agent (Qwen2.5-1.5B, :30082)  — complex topics
    ├─→ Answer directly  (router handles it)
    └─→ Gemini API       (external, with fallback to specialist)
```

Response includes routing metadata:
```json
{
  "choices": [...],
  "routing_metadata": {
    "action": "route_specialist",
    "reason": "Complex topic requiring detailed analysis",
    "source": "specialist_agent"
  }
}
```

### Deploy Router

```bash
# Load API keys from ~/secrets into Kubernetes
./load_secrets.sh

# Deploy router service
./deploy_router.sh
```

## qGPU Resource Syntax

```yaml
resources:
  requests:
    tke.cloud.tencent.com/qgpu-core: 50      # 50% compute (0–100)
    tke.cloud.tencent.com/qgpu-memory: 22     # 22GB VRAM
  limits:
    tke.cloud.tencent.com/qgpu-core: 50
    tke.cloud.tencent.com/qgpu-memory: 22
```

## Console Setup

### Step 1 — Create TKE Cluster

Go to TKE console → select your region.

| Setting | Value |
|---------|-------|
| Cluster name | `qgpu-demo` |
| Cluster spec | L5 (up to 5 nodes / 150 pods) |
| Kubernetes version | latest |
| Runtime | containerd |

Network configuration:
| Setting | Value |
|---------|-------|
| Container network add-on | VPC-CNI |
| Network mode | Shared ENI with multiple IPs |

**Skip QGPU addon during creation** — install it after the cluster is running.

### Step 2 — Install qGPU Addon

Once cluster shows Running:
1. Click your cluster name
2. Left sidebar → Add-ons
3. Find **QGPU** → Install

### Step 3 — Create GPU Node Pool

Left sidebar → Node Management → Node Pool → Create

| Setting | Value |
|---------|-------|
| Node pool type | **Native node pool** (required for qGPU) |
| Instance type | GPU instance with L20 (e.g. PNV5b.8XLARGE96) |
| System disk | Enhanced SSD, **100 GB** |
| Data disk | Enhanced SSD, **200 GB**, mount at **`/var/lib/containerd`** |
| Auto scaling | node range 1–1 |

### Step 4 — Label Node for qGPU

```bash
kubectl get nodes
kubectl label node <NODE_NAME> qgpu-device-enable=enable
```

Verify qGPU resources appear:
```bash
kubectl describe node <NODE_NAME> | grep -A5 "Allocatable"
# Look for: tke.cloud.tencent.com/qgpu-core: 100
#           tke.cloud.tencent.com/qgpu-memory: 44
```

### Step 5 — Enable kubectl Access

**Option A — Public endpoint (recommended)**

Left sidebar → Basic Information → API Server Information:
1. Toggle internet access → Enabled
2. Add your IP to the security group for port 443
3. Download kubeconfig

```bash
export KUBECONFIG=$HOME/Downloads/<your-kubeconfig-file>
kubectl get nodes
```

**Option B — SSH tunnel**

```bash
ssh -L 16443:<PRIVATE_ENDPOINT>:443 -fN root@<NODE_EXTERNAL_IP>
# Edit kubeconfig: server: https://127.0.0.1:16443
kubectl --insecure-skip-tls-verify get nodes
```

### Step 6 — Deploy

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/vllm-half-gpu.yaml
kubectl get pods -n qgpu-demo -w   # Wait ~5-7 min for vLLM startup
```

### Step 7 — Verify GPU Sharing

```bash
kubectl describe node <NODE_NAME> | grep -A5 "Allocated resources"
# Expected: qgpu-core 100/100, qgpu-memory 44/44
```

### Cleanup

Delete cluster from TKE console. Check "delete nodes" to stop GPU billing.

## Terraform Variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit with your credentials and resource IDs
```

Required variables: `secret_id`, `secret_key`, `cluster_id`, `vpc_id`, `subnet_id`, `security_group_id`, `key_id`

Note: Terraform provider only supports regular node pools. Native node pools (required for qGPU) must be created via console.

## Important Notes

- qGPU **requires native node pools** — regular (ASG-based) node pools won't work
- qGPU addon cannot be installed during cluster creation — install it after
- Node must have label `qgpu-device-enable=enable` for qGPU manager to run
- L20 48GB reports **44GB allocatable** through qGPU
- Data disk must mount at **`/var/lib/containerd`** (not `/var/lib/container`)
- System disk should be **100GB+** to avoid disk-pressure taints
- vLLM needs **300s+ probe delays** for initial CUDA graph compilation
- `nvidia-smi` doesn't work inside qGPU pods — use `env | grep QGPU` to verify

## Files

```
├── k8s/
│   ├── namespace.yaml            Namespace
│   ├── vllm-half-gpu.yaml        2 vLLM pods splitting GPU 50/50
│   └── router-agent.yaml         Router agent deployment + service
├── router_service.py             Router agent FastAPI service
├── test.py                       Unified test & chat CLI
├── deploy_router.sh              Router deployment script
├── load_secrets.sh               Load API keys into K8s secrets
├── configure_router_secret.sh    Configure router secret reference
├── terraform/                    Node pool IaC (regular pools only)
├── setup.sh                      Cluster bootstrap script
├── deploy.sh                     Entry point (sources .env)
└── .env.example                  Config template
```
