# =============================================================================
# Terraform Outputs
# =============================================================================

# =============================================================================
# API Gateway
# =============================================================================

output "api_gateway_url" {
  description = "URL of the API Gateway"
  value       = google_cloud_run_v2_service.api_gateway.uri
}

output "api_gateway_name" {
  description = "Name of the API Gateway service"
  value       = google_cloud_run_v2_service.api_gateway.name
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
  description = "Cloud SQL connection name for Cloud Run"
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

output "vpc_connector" {
  description = "VPC connector name"
  value       = google_vpc_access_connector.htbase.name
}

# =============================================================================
# Worker Services
# =============================================================================

output "archive_worker_services" {
  description = "Archive worker service URLs"
  value = {
    singlefile  = google_cloud_run_v2_service.archive_worker_singlefile.uri
    monolith    = google_cloud_run_v2_service.archive_worker_monolith.uri
    readability = google_cloud_run_v2_service.archive_worker_readability.uri
    pdf         = google_cloud_run_v2_service.archive_worker_pdf.uri
    screenshot  = google_cloud_run_v2_service.archive_worker_screenshot.uri
  }
}

output "summarization_worker_url" {
  description = "Summarization worker service URL"
  value       = google_cloud_run_v2_service.summarization_worker.uri
}

output "storage_worker_url" {
  description = "Storage worker service URL"
  value       = google_cloud_run_v2_service.storage_worker.uri
}

# =============================================================================
# Service Account
# =============================================================================

output "service_account_email" {
  description = "Service account email"
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
    database_url = "postgresql://htbase@/${google_sql_database.htbase.name}?host=/cloudsql/${google_sql_database_instance.htbase.connection_name}"
    gcs_bucket   = "gs://${google_storage_bucket.archives.name}"
  }
  sensitive = false
}
