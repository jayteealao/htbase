# =============================================================================
# Infrastructure Resources (Redis, Cloud SQL, GCS)
# =============================================================================

# =============================================================================
# Redis (Memorystore)
# =============================================================================

resource "google_redis_instance" "htbase" {
  name           = "htbase-redis-${var.environment}"
  tier           = var.redis_tier
  memory_size_gb = var.redis_memory_gb
  region         = var.region

  authorized_network = google_compute_network.htbase.id

  redis_version = "REDIS_7_0"
  display_name  = "HT Base Redis (${var.environment})"

  # Persistence configuration
  persistence_config {
    persistence_mode    = "RDB"
    rdb_snapshot_period = "ONE_HOUR"
  }

  # Maintenance window
  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_time {
        hours   = 2
        minutes = 0
      }
    }
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

# =============================================================================
# Cloud SQL (PostgreSQL)
# =============================================================================

resource "google_sql_database_instance" "htbase" {
  name             = "htbase-postgres-${var.environment}"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier              = var.cloudsql_tier
    availability_type = var.environment == "production" ? "REGIONAL" : "ZONAL"
    disk_size         = var.cloudsql_disk_size
    disk_type         = "PD_SSD"
    disk_autoresize   = true

    # Network configuration
    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.htbase.id
      enable_private_path_for_google_cloud_services = true
    }

    # Backup configuration
    backup_configuration {
      enabled                        = true
      start_time                     = "02:00"
      point_in_time_recovery_enabled = var.environment == "production"
      backup_retention_settings {
        retained_backups = 7
      }
    }

    # Maintenance window
    maintenance_window {
      day          = 7  # Sunday
      hour         = 3
      update_track = "stable"
    }

    # Insights for monitoring
    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = true
    }

    # Database flags
    database_flags {
      name  = "log_checkpoints"
      value = "on"
    }

    database_flags {
      name  = "log_connections"
      value = "on"
    }

    database_flags {
      name  = "log_disconnections"
      value = "on"
    }

    user_labels = local.common_labels
  }

  deletion_protection = var.environment == "production"

  depends_on = [google_project_service.apis]
}

# Database
resource "google_sql_database" "htbase" {
  name     = "htbase"
  instance = google_sql_database_instance.htbase.name
}

# Database user
resource "google_sql_user" "htbase" {
  name     = "htbase"
  instance = google_sql_database_instance.htbase.name
  password = random_password.database_password.result
}

resource "random_password" "database_password" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# Store database password in Secret Manager
resource "google_secret_manager_secret_version" "database_password" {
  secret      = google_secret_manager_secret.database_password.id
  secret_data = random_password.database_password.result
}

# =============================================================================
# Cloud Storage Bucket
# =============================================================================

resource "google_storage_bucket" "archives" {
  name          = "htbase-archives-${var.project_id}-${var.environment}"
  location      = var.region
  storage_class = "STANDARD"
  force_destroy = var.environment != "production"

  uniform_bucket_level_access = true

  # Lifecycle rules
  lifecycle_rule {
    condition {
      age = 365  # Move to coldline after 1 year
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  # CORS configuration for signed URLs
  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }

  labels = local.common_labels

  versioning {
    enabled = var.environment == "production"
  }
}

# Grant service account access to bucket
resource "google_storage_bucket_iam_member" "htbase_storage" {
  bucket = google_storage_bucket.archives.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${local.service_account_email}"
}
