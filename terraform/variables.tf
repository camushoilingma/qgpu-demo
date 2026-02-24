## ── Tencent Cloud Credentials ──

variable "secret_id" {
  description = "Tencent Cloud API Secret ID"
  type        = string
  sensitive   = true
}

variable "secret_key" {
  description = "Tencent Cloud API Secret Key"
  type        = string
  sensitive   = true
}

## ── Region & Availability Zone ──

variable "region" {
  description = "Tencent Cloud region"
  type        = string
  default     = "ap-tokyo"
}

variable "availability_zone" {
  description = "Availability zone for GPU nodes"
  type        = string
  default     = "ap-tokyo-2"
}

## ── Cluster Configuration ──

variable "cluster_name" {
  description = "TKE cluster name"
  type        = string
  default     = "qgpu-demo"
}

variable "cluster_version" {
  description = "Kubernetes version"
  type        = string
  default     = "1.28.3"
}

variable "cluster_cidr" {
  description = "Cluster pod CIDR"
  type        = string
  default     = "10.244.0.0/16"
}

## ── Node Pool ──

variable "instance_type" {
  description = "GPU instance type (PNV5b.8XLARGE96 = 1x NVIDIA L20 48GB, 32 vCPU, 96GB RAM)"
  type        = string
  default     = "PNV5b.8XLARGE96"
}

variable "min_node_count" {
  description = "Minimum number of GPU nodes"
  type        = number
  default     = 1
}

variable "max_node_count" {
  description = "Maximum number of GPU nodes"
  type        = number
  default     = 2
}

variable "desired_node_count" {
  description = "Desired number of GPU nodes"
  type        = number
  default     = 1
}

## ── Network ──

variable "vpc_id" {
  description = "Existing VPC ID"
  type        = string
}

variable "subnet_id" {
  description = "Existing subnet ID (must be in the same AZ)"
  type        = string
}

variable "bandwidth" {
  description = "Public network bandwidth cap in Mbps"
  type        = number
  default     = 100
}

## ── SSH & Security ──

variable "key_id" {
  description = "SSH key pair ID"
  type        = string
  default     = "skey-xxxxxxxx"
}

variable "my_ip" {
  description = "Your public IP for security group rules (CIDR format, e.g. 203.0.113.1/32)"
  type        = string
}

variable "security_group_name" {
  description = "Name for the security group"
  type        = string
  default     = "qgpu-demo-sg"
}

## ── Tags ──

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default = {
    project       = "qgpu-demo"
    TaggerAutoOff = "NO"
  }
}
