terraform {
  required_providers {
    tencentcloud = {
      source  = "tencentcloudstack/tencentcloud"
      version = ">= 1.81.0"
    }
  }
  required_version = ">= 1.0"
}

provider "tencentcloud" {
  region     = var.region
  secret_id  = var.secret_id
  secret_key = var.secret_key
}

# ── Security Group ──

resource "tencentcloud_security_group" "qgpu" {
  name        = var.security_group_name
  description = "Security group for qGPU demo TKE cluster"
}

resource "tencentcloud_security_group_lite_rule" "qgpu" {
  security_group_id = tencentcloud_security_group.qgpu.id

  ingress = [
    "ACCEPT#${var.my_ip}#22#TCP",             # SSH from your IP
    "ACCEPT#${var.my_ip}#6443#TCP",           # kubectl API from your IP
    "ACCEPT#${var.my_ip}#30000-32767#TCP",    # NodePort services from your IP
  ]

  egress = [
    "ACCEPT#0.0.0.0/0#ALL#ALL",
  ]
}

# ── TKE Cluster ──

resource "tencentcloud_kubernetes_cluster" "qgpu" {
  cluster_name                    = var.cluster_name
  cluster_version                 = var.cluster_version
  cluster_cidr                    = var.cluster_cidr
  vpc_id                          = var.vpc_id
  cluster_max_pod_num             = 64
  cluster_max_service_num         = 256
  cluster_deploy_type             = "MANAGED_CLUSTER"
  cluster_os                      = "ubuntu22.04x86_64"
  container_runtime               = "containerd"
  cluster_internet                = true
  cluster_internet_security_group = tencentcloud_security_group.qgpu.id

  tags = var.tags
}

# ── GPU Node Pool ──

resource "tencentcloud_kubernetes_node_pool" "gpu" {
  cluster_id          = tencentcloud_kubernetes_cluster.qgpu.id
  name                = "gpu-pool"
  node_os             = "ubuntu22.04x86_64"
  max_size            = var.max_node_count
  min_size            = var.min_node_count
  desired_capacity    = var.desired_node_count
  vpc_id              = var.vpc_id
  subnet_ids          = [var.subnet_id]
  retry_policy        = "INCREMENTAL_INTERVALS"
  delete_keep_instance = false

  auto_scaling_config {
    instance_type              = var.instance_type
    key_ids                    = [var.key_id]
    security_group_ids         = [tencentcloud_security_group.qgpu.id]
    system_disk_type           = "CLOUD_SSD"
    system_disk_size           = 100
    internet_charge_type       = "TRAFFIC_POSTPAID_BY_HOUR"
    internet_max_bandwidth_out = var.bandwidth
    public_ip_assigned         = true

    data_disk {
      disk_type = "CLOUD_SSD"
      disk_size = 200
    }
  }

  labels = {
    "gpu-type" = "l20"
    "qgpu"     = "enabled"
  }

  taints {
    key    = "nvidia.com/gpu"
    value  = "present"
    effect = "NoSchedule"
  }

  tags = var.tags
}

# ── gpu-manager addon for qGPU ──

resource "tencentcloud_kubernetes_addon_attachment" "gpu_manager" {
  cluster_id = tencentcloud_kubernetes_cluster.qgpu.id
  name       = "gpu-manager"

  values = [
    jsonencode({
      "global" = {
        "cluster_id" = tencentcloud_kubernetes_cluster.qgpu.id
      }
    })
  ]
}
