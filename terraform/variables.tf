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

variable "region" {
  description = "Tencent Cloud region"
  type        = string
  default     = "ap-tokyo"
}

variable "cluster_id" {
  description = "Existing TKE cluster ID"
  type        = string
}

variable "vpc_id" {
  description = "Existing VPC ID"
  type        = string
}

variable "subnet_id" {
  description = "Existing subnet ID (must match cluster AZ)"
  type        = string
}

variable "security_group_id" {
  description = "Existing security group ID"
  type        = string
}

variable "instance_type" {
  description = "GPU instance type"
  type        = string
  default     = "PNV5b.8XLARGE96"
}

variable "key_id" {
  description = "SSH key pair ID"
  type        = string
}
