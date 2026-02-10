# =============================================================================
# Terraform Outputs for GKE Deployment
# =============================================================================

# =============================================================================
# GKE Cluster
# =============================================================================

output "gke_cluster_name" {
  description = "Name of the GKE cluster"
  value       = google_container_cluster.htbase.name
}

output "gke_cluster_endpoint" {
  description = "GKE cluster endpoint"
  value       = google_container_cluster.htbase.endpoint
  sensitive   = true
}

output "gke_cluster_ca_certificate" {
  description = "GKE cluster CA certificate"
  value       = google_container_cluster.htbase.master_auth[0].cluster_ca_certificate
  sensitive   = true
}

output "kubectl_config" {
  description = "kubectl configuration command"
  value       = "gcloud container clusters get-credentials ${google_container_cluster.htbase.name} --region ${var.region} --project ${var.project_id}"
}

# =============================================================================
# Ingress / Load Balancer
# =============================================================================

output "load_balancer_ip" {
  description = "External IP address of the load balancer"
  value       = google_compute_global_address.htbase.address
}

output "api_gateway_url" {
  description = "URL of the API Gateway (via ingress)"
  value       = var.domain != "" ? "https://${var.domain}" : "http://${google_compute_global_address.htbase.address}"
}

# =============================================================================
# Infrastructure
# =============================================================================

output "redis_host" {
  description = "Redis host address"
  value       = google_redis_instance.htbase.host
}

output "redis_port" {
  description = "Redis port"
  value       = google_redis_instance.htbase.port
}

output "database_instance_name" {
  description = "Cloud SQL instance name"
  value       = google_sql_database_instance.htbase.name
}

output "database_connection_name" {
  description = "Cloud SQL connection name"
  value       = google_sql_database_instance.htbase.connection_name
}

output "database_private_ip" {
  description = "Cloud SQL private IP"
  value       = google_sql_database_instance.htbase.private_ip_address
}

output "storage_bucket" {
  description = "GCS bucket for archives"
  value       = google_storage_bucket.archives.name
}

output "storage_bucket_url" {
  description = "GCS bucket URL"
  value       = google_storage_bucket.archives.url
}

# =============================================================================
# Networking
# =============================================================================

output "vpc_network" {
  description = "VPC network name"
  value       = google_compute_network.htbase.name
}

output "vpc_subnet" {
  description = "VPC subnet name"
  value       = google_compute_subnetwork.htbase.name
}

# =============================================================================
# Kubernetes Resources
# =============================================================================

output "kubernetes_namespace" {
  description = "Kubernetes namespace for htbase"
  value       = kubernetes_namespace.htbase.metadata[0].name
}

output "kubernetes_service_account" {
  description = "Kubernetes service account name"
  value       = kubernetes_service_account.htbase.metadata[0].name
}

# =============================================================================
# Service Account
# =============================================================================

output "service_account_email" {
  description = "GCP service account email"
  value       = google_service_account.htbase.email
}

# =============================================================================
# Secrets
# =============================================================================

output "secret_database_password" {
  description = "Secret Manager secret for database password"
  value       = google_secret_manager_secret.database_password.name
}

output "secret_huggingface_api_key" {
  description = "Secret Manager secret for HuggingFace API key"
  value       = google_secret_manager_secret.huggingface_api_key.name
}

output "secret_openai_api_key" {
  description = "Secret Manager secret for OpenAI API key"
  value       = google_secret_manager_secret.openai_api_key.name
}

# =============================================================================
# Artifact Registry
# =============================================================================

output "artifact_registry_repository" {
  description = "Artifact Registry repository URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.htbase.repository_id}"
}

# =============================================================================
# Connection Strings (for local development reference)
# =============================================================================

output "connection_info" {
  description = "Connection information for debugging"
  value = {
    redis_url    = "redis://${google_redis_instance.htbase.host}:${google_redis_instance.htbase.port}"
    database_url = "postgresql://htbase:***@${google_sql_database_instance.htbase.private_ip_address}:5432/${google_sql_database.htbase.name}"
    gcs_bucket   = "gs://${google_storage_bucket.archives.name}"
  }
}

# =============================================================================
# Deployment Commands
# =============================================================================

output "deployment_commands" {
  description = "Useful deployment commands"
  value = {
    get_credentials = "gcloud container clusters get-credentials ${google_container_cluster.htbase.name} --region ${var.region} --project ${var.project_id}"
    view_pods       = "kubectl get pods -n ${kubernetes_namespace.htbase.metadata[0].name}"
    view_services   = "kubectl get services -n ${kubernetes_namespace.htbase.metadata[0].name}"
    view_logs       = "kubectl logs -f -l app=htbase -n ${kubernetes_namespace.htbase.metadata[0].name}"
    scale_workers   = "kubectl scale deployment archive-worker-singlefile --replicas=3 -n ${kubernetes_namespace.htbase.metadata[0].name}"
  }
}
