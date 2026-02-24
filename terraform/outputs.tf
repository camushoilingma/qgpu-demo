output "cluster_id" {
  description = "TKE cluster ID"
  value       = tencentcloud_kubernetes_cluster.qgpu.id
}

output "cluster_endpoint" {
  description = "Cluster API server endpoint"
  value       = tencentcloud_kubernetes_cluster.qgpu.cluster_external_endpoint
}

output "kubeconfig" {
  description = "Kubeconfig for kubectl access"
  value       = tencentcloud_kubernetes_cluster.qgpu.kube_config
  sensitive   = true
}

output "security_group_id" {
  description = "Security group ID"
  value       = tencentcloud_security_group.qgpu.id
}
