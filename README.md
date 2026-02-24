# qGPU Demo — TKE Cluster with GPU Sharing

Run multiple vLLM instances on a single NVIDIA L20 GPU using Tencent Cloud's qGPU technology.

## Architecture

```
TKE Cluster (Managed K8s)
└── GPU Node Pool (PNV5b.8XLARGE96 × 1 node)
    └── qGPU enabled (gpu-manager addon)
        ├── Pod A: vLLM (50% GPU, 24GB) → :30081
        └── Pod B: vLLM (50% GPU, 24GB) → :30082
```

## Console Setup (Step-by-Step)

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
| Container subnet | select your subnet in Tokyo |
| Service IP Range | `192.168.0.0/17` (default) |

Component configuration:
- Keep defaults (CBS, monitoragent, ip-masq-agent)
- **Skip QGPU addon** for now — it must be installed after cluster creation

Click Create. Wait ~5-10 minutes for the control plane to be ready.

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
| Node pool type | Native node pool |
| Billing mode | Pay-as-you-go |
| Availability zone | Tokyo Zone 1 or 2 (must match your subnet) |
| Instance family | **GPU-based** → **GPU Computing PNV5b** |
| Instance type | **PNV5b.8XLARGE96** (32-core, 96GB, 1× L20 48GB, ~$2.67/hr) |
| GPU driver | default (e.g. 570.x, CUDA 12.8) |
| System disk | Enhanced SSD, 100 GB |
| Data disk | Enhanced SSD, 200 GB, ext4, mount at `/var/lib/container` |
| Auto scaling | Activate, node range **1–1** (or 1–2) |
| qGPU sharing | enable if available (may require addon to be installed first) |

Click Create node pool. Wait ~5 minutes for the GPU node to join.

### Step 4 — Enable Public API Access (kubectl)

Left sidebar → **Basic Information** → **API Server Information** tab

1. Toggle **Via internet** to **Enabled**
2. Configure the CLB:
   - Security group: default (ensure port 443 is open for your IP)
   - Load Balancer: Automatic creation
   - Bandwidth: 10 Mbps
   - By traffic usage
3. Wait ~1 minute for CLB to be created

### Step 5 — Download Kubeconfig

On the same **API Server Information** page, scroll down to **Connect to a Kubernetes Cluster via kubectl**:

1. Download the kubeconfig file
2. Configure locally:
```bash
export KUBECONFIG=$HOME/Downloads/cls-xxxxxxxx-config
kubectl config get-contexts
kubectl config use-context cls-xxxxxxxx-XXXXXXXXXXXX-context-default
kubectl get nodes
```

### Step 6 — Verify qGPU Resources

```bash
kubectl describe node <NODE_NAME> | grep -A5 "Allocatable"
```

Look for:
```
tke.cloud.tencent.com/qgpu-core: 100
tke.cloud.tencent.com/qgpu-memory: 48
```

### Step 7 — Deploy vLLM Pods

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/vllm-half-gpu.yaml    # 2 pods sharing GPU (50% each)
```

Watch pods start:
```bash
kubectl get pods -n qgpu-demo -w
kubectl logs -n qgpu-demo deploy/vllm-half-a -f
```

### Step 8 — Test

```bash
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="ExternalIP")].address}')
curl http://$NODE_IP:30081/v1/models
curl http://$NODE_IP:30082/v1/models
```

### Step 9 — Benchmark

```bash
python3 benchmark.py --base-url http://$NODE_IP:30081/v1 --label half-a --save
python3 benchmark.py --base-url http://$NODE_IP:30082/v1 --label half-b --save
python3 benchmark.py --compare results-half-a-*.csv results-half-b-*.csv
```

### Cleanup

Go to https://console.tencentcloud.com/tke2/cluster → select `qgpu-demo` → **Delete**.
Check "delete nodes" to stop GPU billing.

---

## Quick Start (Terraform)

### 1. Provision the cluster

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your credentials, VPC/subnet IDs, SSH key, IP
terraform init && terraform apply
```

### 2. Deploy vLLM pods

```bash
cp .env.example .env
# Edit .env with cluster ID from terraform output
./deploy.sh half      # 2 pods sharing GPU (50% each)
./deploy.sh full      # 1 pod with full GPU (baseline)
./deploy.sh quarter   # 1 pod with 25% GPU
```

### 3. Benchmark

```bash
python3 benchmark.py --base-url http://<NODE_IP>:30081/v1 --label half-a --save
python3 benchmark.py --base-url http://<NODE_IP>:30080/v1 --label full --save
python3 benchmark.py --compare results-full-*.csv results-half-a-*.csv
```

## qGPU Resource Syntax

```yaml
resources:
  requests:
    tke.cloud.tencent.com/qgpu-core: 50      # 50% compute
    tke.cloud.tencent.com/qgpu-memory: 24     # 24GB VRAM
  limits:
    tke.cloud.tencent.com/qgpu-core: 50
    tke.cloud.tencent.com/qgpu-memory: 24
```

## Deployment Modes

| Mode | Pods | GPU per pod | NodePorts |
|------|------|-------------|-----------|
| `full` | 1 | 100% core, 46GB | 30080 |
| `half` | 2 | 50% core, 24GB | 30081, 30082 |
| `quarter` | 1 | 25% core, 12GB | 30083 |

## Files

```
├── terraform/          Cluster + GPU node pool IaC
├── k8s/                Kubernetes manifests (namespace, deployments, services)
├── setup.sh            Cluster bootstrap (kubeconfig, namespace, pods)
├── deploy.sh           Entry point — sources .env, runs setup
├── benchmark.py        Performance benchmark with comparison mode
├── .env.example        Config template
└── .gitignore
```
