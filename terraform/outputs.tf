output "node_pool_id" {
  description = "GPU node pool ID"
  value       = tencentcloud_kubernetes_node_pool.gpu.id
}
