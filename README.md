# qGPU Demo — GPU Sharing on TKE

Run two different LLMs simultaneously on a single NVIDIA L20 GPU using Tencent Cloud's qGPU technology.

## Architecture

```
TKE Cluster (Managed K8s)
└── Native GPU Node Pool (PNV5b.8XLARGE96 × 1 node, 1× L20 48GB)
    └── qGPU enabled (gpu-manager addon)
        ├── Pod A: vLLM + Qwen2.5-0.5B  (50% compute, 22GB VRAM) → :30081
        └── Pod B: vLLM + Qwen2.5-1.5B  (50% compute, 22GB VRAM) → :30082
```

## Demo Results

Two models serving inference concurrently on one GPU:

```
--- 20 concurrent requests (10 per model) ---

  [Qwen2.5-0.5B] 10 requests, 668 tokens, 551.6 tok/s
  [Qwen2.5-1.5B] 10 requests, 364 tokens, 300.5 tok/s

  Total wall time: 1.21s
  Total requests:  20
  Total tokens:    1032
```

## Quick Start

### 1. Test the endpoints

```bash
curl http://<NODE_IP>:30081/v1/models   # Qwen2.5-0.5B
curl http://<NODE_IP>:30082/v1/models   # Qwen2.5-1.5B
```

### 2. Run the concurrent test

```bash
python3 test_qgpu.py
```

### 3. Chat with either model

```bash
curl http://<NODE_IP>:30081/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen2.5-0.5B-Instruct",
       "messages":[{"role":"user","content":"What is qGPU?"}],
       "max_tokens":100}'
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

Go to https://console.tencentcloud.com/tke2/cluster → switch to **ap-tokyo**

| Setting | Value |
|---------|-------|
| Cluster name | `qgpu-demo` |
| Cluster spec | **Basic - L5** ($0.02/hr, up to 5 nodes / 150 pods) |
| Kubernetes version | latest (e.g. 1.34.1) |
| Runtime | containerd |
| OS | TencentOS Server (default) |
| VPC | your existing VPC |

Network configuration:
| Setting | Value |
|---------|-------|
| Container network add-on | **VPC-CNI** (recommended) |
| Network mode | Shared ENI with multiple IPs |
| Static Pod IP | unchecked |
| Container subnet | select your subnet |
| Service IP Range | `192.168.0.0/17` (default) |

Component configuration:
- Keep defaults (CBS, monitoragent, ip-masq-agent)
- **Skip QGPU addon** — must be installed after cluster creation

Click Create. Wait ~5-10 minutes.

### Step 2 — Install qGPU Addon

Once cluster shows **Running**:
1. Click your cluster name
2. Left sidebar → **Add-ons** (or Component Management)
3. Find **QGPU** → click **Install**

Wait ~2 minutes for the addon pods to start.

### Step 3 — Create GPU Node Pool

Left sidebar → **Node Management** → **Node Pool** → **Create**

| Setting | Value |
|---------|-------|
| Node pool type | **Native node pool** (required for qGPU) |
| Billing mode | Pay-as-you-go |
| Availability zone | must match your subnet |
| Instance type | **PNV5b.8XLARGE96** (32-core, 96GB, 1× L20 48GB, ~$2.67/hr) |
| GPU driver | default (e.g. 570.x, CUDA 12.8) |
| System disk | Enhanced SSD, **100 GB** |
| Data disk | Enhanced SSD, **200 GB**, ext4, mount at **`/var/lib/containerd`** |
| Auto scaling | node range **1–1** |

Wait ~5 minutes for the GPU node to join.

### Step 4 — Label Node for qGPU

The qGPU manager DaemonSet requires a label to schedule onto the node:

```bash
kubectl label node <NODE_NAME> qgpu-device-enable=enable
```

Verify qGPU resources appear:
```bash
kubectl describe node <NODE_NAME> | grep -A5 "Allocatable"
```

Look for:
```
tke.cloud.tencent.com/qgpu-core:    100
tke.cloud.tencent.com/qgpu-memory:  44
```

### Step 5 — Enable kubectl Access

**Option A — Public endpoint (console)**

Left sidebar → **Basic Information** → **API Server Information**:
1. Toggle **Via internet** → **Enabled**
2. Add your IP to the security group for port 443
3. Download kubeconfig from the same page

```bash
export KUBECONFIG=$HOME/Downloads/cls-xxxxxxxx-config
kubectl get nodes
```

**Option B — SSH tunnel to private endpoint**

If the public CLB has issues, tunnel through the GPU node:
```bash
ssh -L 16443:<PRIVATE_ENDPOINT>:443 -fN root@<NODE_EXTERNAL_IP>
```

Edit kubeconfig to point `server:` at `https://127.0.0.1:16443`, then:
```bash
kubectl --insecure-skip-tls-verify get nodes
```

### Step 6 — Deploy vLLM Pods

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/vllm-half-gpu.yaml
```

Wait ~5-7 minutes for vLLM to pull the image, load models, and compile CUDA graphs:
```bash
kubectl get pods -n qgpu-demo -w
```

### Step 7 — Verify GPU Sharing

Check that both pods are running and the GPU is fully allocated:

```bash
kubectl describe node <NODE_NAME> | grep -A5 "Allocated resources"
```

Expected output:
```
tke.cloud.tencent.com/qgpu-core    100   100
tke.cloud.tencent.com/qgpu-memory  44    44
```

### Step 8 — Test

```bash
# Quick test
curl http://<NODE_IP>:30081/v1/models
curl http://<NODE_IP>:30082/v1/models

# Concurrent test
python3 test_qgpu.py
```

### Cleanup

Go to https://console.tencentcloud.com/tke2/cluster → select `qgpu-demo` → **Delete**.
Check "delete nodes" to stop GPU billing.

## Important Notes

- qGPU **requires native node pools** — regular (ASG-based) node pools won't work
- qGPU addon cannot be installed during cluster creation — install it after
- Node must have label `qgpu-device-enable=enable` for qGPU manager to run
- L20 48GB reports **44GB allocatable** through qGPU
- Data disk must mount at **`/var/lib/containerd`** (not `/var/lib/container`) — the vLLM image is ~9GB
- System disk should be **100GB+** to avoid disk-pressure taints
- vLLM needs **300s+ probe delays** for initial CUDA graph compilation
- `nvidia-smi` doesn't work inside qGPU pods — use `env | grep QGPU` to verify allocation
- The Terraform provider does not support native node pools — use the console

## Files

```
├── k8s/
│   ├── namespace.yaml          qgpu-demo namespace
│   └── vllm-half-gpu.yaml      2 vLLM pods splitting GPU 50/50
├── terraform/                  Node pool IaC (regular pools only)
├── test_qgpu.py                Concurrent inference test script
├── setup.sh                    Cluster bootstrap script
├── deploy.sh                   Entry point (sources .env)
├── .env.example                Config template
└── .gitignore
```
