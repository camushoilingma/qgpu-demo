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

# ── GPU Node Pool (against existing TKE cluster) ──

resource "tencentcloud_kubernetes_node_pool" "gpu" {
  cluster_id          = var.cluster_id
  name                = "gpu-pool"
  node_os             = "tlinux3.1x86_64"
  max_size            = 1
  min_size            = 1
  desired_capacity    = 1
  vpc_id              = var.vpc_id
  subnet_ids          = [var.subnet_id]
  retry_policy        = "INCREMENTAL_INTERVALS"
  delete_keep_instance = false

  auto_scaling_config {
    instance_type              = var.instance_type
    key_ids                    = [var.key_id]
    orderly_security_group_ids = [var.security_group_id]
    system_disk_type           = "CLOUD_BSSD"
    system_disk_size           = 100
    internet_charge_type       = "TRAFFIC_POSTPAID_BY_HOUR"
    internet_max_bandwidth_out = 100
    public_ip_assigned         = true

    data_disk {
      disk_type = "CLOUD_BSSD"
      disk_size = 200
    }
  }

  node_config {
    data_disk {
      disk_type             = "CLOUD_BSSD"
      disk_size             = 200
      mount_target          = "/var/lib/containerd"
      auto_format_and_mount = true
      file_system           = "ext4"
    }

    docker_graph_path = "/var/lib/containerd"
  }

  labels = {
    "qgpu-device-enable" = "enable"
  }

  taints {
    key    = "nvidia.com/gpu"
    value  = "present"
    effect = "NoSchedule"
  }
}
