# =============================================================================
# HT Base - Terraform Configuration for Google Cloud Run
# =============================================================================
# Usage:
#   cd infrastructure/terraform
#   terraform init
#   terraform plan -var-file="environments/production.tfvars"
#   terraform apply -var-file="environments/production.tfvars"
# =============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }

  # Configure remote state (recommended for production)
  # backend "gcs" {
  #   bucket = "htbase-terraform-state"
  #   prefix = "terraform/state"
  # }
}

# =============================================================================
# Providers
# =============================================================================

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# =============================================================================
# Local Values
# =============================================================================

locals {
  common_labels = {
    app         = "htbase"
    environment = var.environment
    managed_by  = "terraform"
  }

  # Service account email
  service_account_email = google_service_account.htbase.email

  # Container image URLs
  images = {
    api_gateway           = "${var.region}-docker.pkg.dev/${var.project_id}/htbase/api-gateway:${var.image_tag}"
    archive_worker        = "${var.region}-docker.pkg.dev/${var.project_id}/htbase/archive-worker:${var.image_tag}"
    summarization_worker  = "${var.region}-docker.pkg.dev/${var.project_id}/htbase/summarization-worker:${var.image_tag}"
    storage_worker        = "${var.region}-docker.pkg.dev/${var.project_id}/htbase/storage-worker:${var.image_tag}"
  }
}

# =============================================================================
# Enable Required APIs
# =============================================================================

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "redis.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "vpcaccess.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# =============================================================================
# Networking
# =============================================================================

# VPC Network
resource "google_compute_network" "htbase" {
  name                    = "htbase-vpc-${var.environment}"
  auto_create_subnetworks = false
  project                 = var.project_id

  depends_on = [google_project_service.apis]
}

# Subnet for Cloud Run VPC connector
resource "google_compute_subnetwork" "htbase" {
  name          = "htbase-subnet-${var.environment}"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.htbase.id

  private_ip_google_access = true
}

# VPC Connector for Cloud Run to access Redis/Cloud SQL
resource "google_vpc_access_connector" "htbase" {
  name          = "htbase-connector-${var.environment}"
  region        = var.region
  network       = google_compute_network.htbase.name
  ip_cidr_range = "10.8.0.0/28"
  min_instances = 2
  max_instances = 10

  depends_on = [google_project_service.apis]
}

# =============================================================================
# Service Account
# =============================================================================

resource "google_service_account" "htbase" {
  account_id   = "htbase-${var.environment}"
  display_name = "HT Base Service Account (${var.environment})"
  project      = var.project_id
}

# Grant necessary permissions
resource "google_project_iam_member" "htbase_roles" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/secretmanager.secretAccessor",
    "roles/storage.objectAdmin",
    "roles/redis.editor",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${local.service_account_email}"
}

# =============================================================================
# Artifact Registry
# =============================================================================

resource "google_artifact_registry_repository" "htbase" {
  location      = var.region
  repository_id = "htbase"
  format        = "DOCKER"
  description   = "Docker images for HT Base microservices"

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

# =============================================================================
# Secret Manager
# =============================================================================

resource "google_secret_manager_secret" "database_password" {
  secret_id = "htbase-database-password-${var.environment}"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "huggingface_api_key" {
  secret_id = "htbase-huggingface-api-key-${var.environment}"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret" "openai_api_key" {
  secret_id = "htbase-openai-api-key-${var.environment}"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = local.common_labels

  depends_on = [google_project_service.apis]
}

# Grant service account access to secrets
resource "google_secret_manager_secret_iam_member" "htbase_secrets" {
  for_each = {
    database_password   = google_secret_manager_secret.database_password.id
    huggingface_api_key = google_secret_manager_secret.huggingface_api_key.id
    openai_api_key      = google_secret_manager_secret.openai_api_key.id
  }

  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.service_account_email}"
}
