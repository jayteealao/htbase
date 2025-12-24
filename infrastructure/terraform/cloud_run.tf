# =============================================================================
# Cloud Run Services
# =============================================================================

# =============================================================================
# Common Environment Variables
# =============================================================================

locals {
  common_env_vars = [
    {
      name  = "REDIS_URL"
      value = "redis://${google_redis_instance.htbase.host}:${google_redis_instance.htbase.port}"
    },
    {
      name  = "CELERY_BROKER_URL"
      value = "redis://${google_redis_instance.htbase.host}:${google_redis_instance.htbase.port}/0"
    },
    {
      name  = "CELERY_RESULT_BACKEND"
      value = "redis://${google_redis_instance.htbase.host}:${google_redis_instance.htbase.port}/1"
    },
    {
      name  = "DATABASE_URL"
      value = "postgresql://htbase@/${google_sql_database.htbase.name}?host=/cloudsql/${google_sql_database_instance.htbase.connection_name}"
    },
    {
      name  = "GCS_BUCKET"
      value = google_storage_bucket.archives.name
    },
    {
      name  = "GCS_PROJECT_ID"
      value = var.project_id
    },
    {
      name  = "ENVIRONMENT"
      value = var.environment
    },
    {
      name  = "LOG_LEVEL"
      value = var.log_level
    },
    {
      name  = "LOG_FORMAT"
      value = "json"
    },
  ]

  # Secret references
  database_password_secret = {
    name = "DATABASE_PASSWORD"
    value_source {
      secret_key_ref {
        secret  = google_secret_manager_secret.database_password.secret_id
        version = "latest"
      }
    }
  }
}

# =============================================================================
# API Gateway
# =============================================================================

resource "google_cloud_run_v2_service" "api_gateway" {
  name     = "htbase-api-gateway-${var.environment}"
  location = var.region

  template {
    service_account = local.service_account_email

    scaling {
      min_instance_count = var.api_gateway_min_instances
      max_instance_count = var.api_gateway_max_instances
    }

    vpc_access {
      connector = google_vpc_access_connector.htbase.id
      egress    = "ALL_TRAFFIC"
    }

    containers {
      image = local.images.api_gateway

      resources {
        limits = {
          cpu    = var.api_gateway_cpu
          memory = var.api_gateway_memory
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      ports {
        container_port = 8080
      }

      # Common environment variables
      dynamic "env" {
        for_each = local.common_env_vars
        content {
          name  = env.value.name
          value = env.value.value
        }
      }

      # API Gateway specific
      env {
        name  = "WORKERS"
        value = "4"
      }

      env {
        name  = "CORS_ORIGINS"
        value = var.cors_origins
      }

      env {
        name  = "API_RATE_LIMIT"
        value = var.api_rate_limit
      }

      env {
        name  = "DEFAULT_ARCHIVERS"
        value = "singlefile,monolith,readability,pdf,screenshot"
      }

      env {
        name  = "ENABLE_SUMMARIZATION"
        value = "true"
      }

      # Secrets
      env {
        name = "DATABASE_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_password.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 5
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        period_seconds    = 30
        failure_threshold = 3
      }
    }

    # Cloud SQL connection
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.htbase.connection_name]
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  labels = local.common_labels

  depends_on = [
    google_project_iam_member.htbase_roles,
    google_secret_manager_secret_iam_member.htbase_secrets,
  ]
}

# Allow unauthenticated access to API Gateway
resource "google_cloud_run_v2_service_iam_member" "api_gateway_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api_gateway.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# =============================================================================
# Archive Workers
# =============================================================================

# Archive Worker - SingleFile
resource "google_cloud_run_v2_service" "archive_worker_singlefile" {
  name     = "htbase-archive-singlefile-${var.environment}"
  location = var.region

  template {
    service_account = local.service_account_email

    scaling {
      min_instance_count = 0
      max_instance_count = var.archive_worker_max_instances
    }

    timeout = "900s"  # 15 minutes for long-running archives

    vpc_access {
      connector = google_vpc_access_connector.htbase.id
      egress    = "ALL_TRAFFIC"
    }

    containers {
      image = local.images.archive_worker

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
        cpu_idle = false  # Keep CPU during idle for Chrome
      }

      # Common environment variables
      dynamic "env" {
        for_each = local.common_env_vars
        content {
          name  = env.value.name
          value = env.value.value
        }
      }

      env {
        name  = "WORKER_QUEUES"
        value = "archive.singlefile"
      }

      env {
        name  = "WORKER_CONCURRENCY"
        value = "2"
      }

      env {
        name  = "ARCHIVER_TYPE"
        value = "singlefile"
      }

      env {
        name  = "ARCHIVER_TIMEOUT"
        value = "300"
      }

      env {
        name = "DATABASE_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_password.secret_id
            version = "latest"
          }
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.htbase.connection_name]
      }
    }
  }

  labels = local.common_labels

  depends_on = [
    google_project_iam_member.htbase_roles,
  ]
}

# Archive Worker - Monolith
resource "google_cloud_run_v2_service" "archive_worker_monolith" {
  name     = "htbase-archive-monolith-${var.environment}"
  location = var.region

  template {
    service_account = local.service_account_email

    scaling {
      min_instance_count = 0
      max_instance_count = var.archive_worker_max_instances
    }

    timeout = "900s"

    vpc_access {
      connector = google_vpc_access_connector.htbase.id
      egress    = "ALL_TRAFFIC"
    }

    containers {
      image = local.images.archive_worker

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
        cpu_idle = false
      }

      dynamic "env" {
        for_each = local.common_env_vars
        content {
          name  = env.value.name
          value = env.value.value
        }
      }

      env {
        name  = "WORKER_QUEUES"
        value = "archive.monolith"
      }

      env {
        name  = "WORKER_CONCURRENCY"
        value = "3"
      }

      env {
        name  = "ARCHIVER_TYPE"
        value = "monolith"
      }

      env {
        name  = "ARCHIVER_TIMEOUT"
        value = "300"
      }

      env {
        name = "DATABASE_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_password.secret_id
            version = "latest"
          }
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.htbase.connection_name]
      }
    }
  }

  labels = local.common_labels
}

# Archive Worker - Readability
resource "google_cloud_run_v2_service" "archive_worker_readability" {
  name     = "htbase-archive-readability-${var.environment}"
  location = var.region

  template {
    service_account = local.service_account_email

    scaling {
      min_instance_count = 0
      max_instance_count = var.archive_worker_max_instances
    }

    timeout = "300s"

    vpc_access {
      connector = google_vpc_access_connector.htbase.id
      egress    = "ALL_TRAFFIC"
    }

    containers {
      image = local.images.archive_worker

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        cpu_idle = true
      }

      dynamic "env" {
        for_each = local.common_env_vars
        content {
          name  = env.value.name
          value = env.value.value
        }
      }

      env {
        name  = "WORKER_QUEUES"
        value = "archive.readability"
      }

      env {
        name  = "WORKER_CONCURRENCY"
        value = "5"
      }

      env {
        name  = "ARCHIVER_TYPE"
        value = "readability"
      }

      env {
        name  = "ARCHIVER_TIMEOUT"
        value = "120"
      }

      env {
        name = "DATABASE_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_password.secret_id
            version = "latest"
          }
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.htbase.connection_name]
      }
    }
  }

  labels = local.common_labels
}

# Archive Worker - PDF
resource "google_cloud_run_v2_service" "archive_worker_pdf" {
  name     = "htbase-archive-pdf-${var.environment}"
  location = var.region

  template {
    service_account = local.service_account_email

    scaling {
      min_instance_count = 0
      max_instance_count = var.archive_worker_max_instances
    }

    timeout = "180s"

    vpc_access {
      connector = google_vpc_access_connector.htbase.id
      egress    = "ALL_TRAFFIC"
    }

    containers {
      image = local.images.archive_worker

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        cpu_idle = true
      }

      dynamic "env" {
        for_each = local.common_env_vars
        content {
          name  = env.value.name
          value = env.value.value
        }
      }

      env {
        name  = "WORKER_QUEUES"
        value = "archive.pdf"
      }

      env {
        name  = "WORKER_CONCURRENCY"
        value = "3"
      }

      env {
        name  = "ARCHIVER_TYPE"
        value = "pdf"
      }

      env {
        name  = "ARCHIVER_TIMEOUT"
        value = "60"
      }

      env {
        name = "DATABASE_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_password.secret_id
            version = "latest"
          }
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.htbase.connection_name]
      }
    }
  }

  labels = local.common_labels
}

# Archive Worker - Screenshot
resource "google_cloud_run_v2_service" "archive_worker_screenshot" {
  name     = "htbase-archive-screenshot-${var.environment}"
  location = var.region

  template {
    service_account = local.service_account_email

    scaling {
      min_instance_count = 0
      max_instance_count = var.archive_worker_max_instances
    }

    timeout = "180s"

    vpc_access {
      connector = google_vpc_access_connector.htbase.id
      egress    = "ALL_TRAFFIC"
    }

    containers {
      image = local.images.archive_worker

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        cpu_idle = true
      }

      dynamic "env" {
        for_each = local.common_env_vars
        content {
          name  = env.value.name
          value = env.value.value
        }
      }

      env {
        name  = "WORKER_QUEUES"
        value = "archive.screenshot"
      }

      env {
        name  = "WORKER_CONCURRENCY"
        value = "3"
      }

      env {
        name  = "ARCHIVER_TYPE"
        value = "screenshot"
      }

      env {
        name  = "ARCHIVER_TIMEOUT"
        value = "60"
      }

      env {
        name = "DATABASE_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_password.secret_id
            version = "latest"
          }
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.htbase.connection_name]
      }
    }
  }

  labels = local.common_labels
}

# =============================================================================
# Summarization Worker
# =============================================================================

resource "google_cloud_run_v2_service" "summarization_worker" {
  name     = "htbase-summarization-${var.environment}"
  location = var.region

  template {
    service_account = local.service_account_email

    scaling {
      min_instance_count = 0
      max_instance_count = var.summarization_worker_max_instances
    }

    timeout = "300s"

    vpc_access {
      connector = google_vpc_access_connector.htbase.id
      egress    = "ALL_TRAFFIC"
    }

    containers {
      image = local.images.summarization_worker

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle = true
      }

      dynamic "env" {
        for_each = local.common_env_vars
        content {
          name  = env.value.name
          value = env.value.value
        }
      }

      env {
        name  = "WORKER_QUEUES"
        value = "summarization"
      }

      env {
        name  = "WORKER_CONCURRENCY"
        value = "5"
      }

      env {
        name  = "LLM_PROVIDER"
        value = var.llm_provider
      }

      env {
        name  = "HUGGINGFACE_API_URL"
        value = var.huggingface_api_url
      }

      env {
        name  = "OPENAI_MODEL"
        value = var.openai_model
      }

      env {
        name  = "CHUNK_SIZE"
        value = "4000"
      }

      env {
        name  = "CHUNK_OVERLAP"
        value = "200"
      }

      env {
        name = "DATABASE_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_password.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "HUGGINGFACE_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.huggingface_api_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name = "OPENAI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.openai_api_key.secret_id
            version = "latest"
          }
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.htbase.connection_name]
      }
    }
  }

  labels = local.common_labels
}

# =============================================================================
# Storage Worker
# =============================================================================

resource "google_cloud_run_v2_service" "storage_worker" {
  name     = "htbase-storage-${var.environment}"
  location = var.region

  template {
    service_account = local.service_account_email

    scaling {
      min_instance_count = 0
      max_instance_count = var.storage_worker_max_instances
    }

    timeout = "300s"

    vpc_access {
      connector = google_vpc_access_connector.htbase.id
      egress    = "ALL_TRAFFIC"
    }

    containers {
      image = local.images.storage_worker

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        cpu_idle = true
      }

      dynamic "env" {
        for_each = local.common_env_vars
        content {
          name  = env.value.name
          value = env.value.value
        }
      }

      env {
        name  = "WORKER_QUEUES"
        value = "storage"
      }

      env {
        name  = "WORKER_CONCURRENCY"
        value = "10"
      }

      env {
        name  = "STORAGE_PROVIDER"
        value = "gcs"
      }

      env {
        name  = "COMPRESSION_ENABLED"
        value = "true"
      }

      env {
        name  = "CLEANUP_AFTER_UPLOAD"
        value = "true"
      }

      env {
        name = "DATABASE_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_password.secret_id
            version = "latest"
          }
        }
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.htbase.connection_name]
      }
    }
  }

  labels = local.common_labels
}
