# =============================================================================
# GKE Cluster and Kubernetes Resources
# =============================================================================
# This file provisions a GKE cluster and deploys HT Base microservices
# using Kubernetes deployments, services, and ingress.
# =============================================================================

# =============================================================================
# GKE Cluster
# =============================================================================

resource "google_container_cluster" "htbase" {
  name     = "htbase-${var.environment}"
  location = var.region

  # We use separately managed node pools
  remove_default_node_pool = true
  initial_node_count       = 1

  # Network configuration
  network    = google_compute_network.htbase.name
  subnetwork = google_compute_subnetwork.htbase.name

  # Private cluster configuration
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  # IP allocation policy for VPC-native cluster
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Workload Identity
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Cluster autoscaling
  cluster_autoscaling {
    enabled = true
    resource_limits {
      resource_type = "cpu"
      minimum       = 4
      maximum       = 100
    }
    resource_limits {
      resource_type = "memory"
      minimum       = 16
      maximum       = 400
    }
  }

  # Maintenance window
  maintenance_policy {
    daily_maintenance_window {
      start_time = "03:00"
    }
  }

  # Addons
  addons_config {
    http_load_balancing {
      disabled = false
    }
    horizontal_pod_autoscaling {
      disabled = false
    }
    gce_persistent_disk_csi_driver_config {
      enabled = true
    }
  }

  # Logging and monitoring
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = true
    }
  }

  resource_labels = local.common_labels

  depends_on = [google_project_service.apis]
}

# =============================================================================
# Node Pools
# =============================================================================

# General purpose node pool for API Gateway and light workers
resource "google_container_node_pool" "general" {
  name       = "general-${var.environment}"
  location   = var.region
  cluster    = google_container_cluster.htbase.name
  node_count = var.environment == "production" ? 2 : 1

  autoscaling {
    min_node_count = var.environment == "production" ? 2 : 1
    max_node_count = 10
  }

  node_config {
    machine_type = "e2-standard-2"  # 2 vCPU, 8GB RAM
    disk_size_gb = 50
    disk_type    = "pd-standard"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    service_account = google_service_account.htbase.email

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    labels = merge(local.common_labels, {
      pool = "general"
    })

    tags = ["htbase", "general"]
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

# High-memory node pool for archive workers (Chrome needs RAM)
resource "google_container_node_pool" "archive_workers" {
  name     = "archive-workers-${var.environment}"
  location = var.region
  cluster  = google_container_cluster.htbase.name

  autoscaling {
    min_node_count = 0
    max_node_count = var.archive_worker_max_instances
  }

  node_config {
    machine_type = "e2-highmem-2"  # 2 vCPU, 16GB RAM
    disk_size_gb = 100
    disk_type    = "pd-ssd"

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    service_account = google_service_account.htbase.email

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    labels = merge(local.common_labels, {
      pool = "archive-workers"
    })

    tags = ["htbase", "archive-workers"]

    taint {
      key    = "workload"
      value  = "archive"
      effect = "NO_SCHEDULE"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

# =============================================================================
# Subnet with secondary ranges for GKE
# =============================================================================

resource "google_compute_subnetwork" "htbase" {
  name          = "htbase-subnet-${var.environment}"
  ip_cidr_range = "10.0.0.0/20"
  region        = var.region
  network       = google_compute_network.htbase.id

  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = "10.1.0.0/16"
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = "10.2.0.0/20"
  }
}

# =============================================================================
# Kubernetes Provider Configuration
# =============================================================================

data "google_client_config" "default" {}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.htbase.endpoint}"
  token                  = data.google_client_config.default.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.htbase.master_auth[0].cluster_ca_certificate)
}

provider "helm" {
  kubernetes {
    host                   = "https://${google_container_cluster.htbase.endpoint}"
    token                  = data.google_client_config.default.access_token
    cluster_ca_certificate = base64decode(google_container_cluster.htbase.master_auth[0].cluster_ca_certificate)
  }
}

# =============================================================================
# Kubernetes Namespace
# =============================================================================

resource "kubernetes_namespace" "htbase" {
  metadata {
    name = "htbase-${var.environment}"
    labels = {
      app         = "htbase"
      environment = var.environment
    }
  }

  depends_on = [google_container_cluster.htbase]
}

# =============================================================================
# Kubernetes Secrets
# =============================================================================

resource "kubernetes_secret" "htbase_secrets" {
  metadata {
    name      = "htbase-secrets"
    namespace = kubernetes_namespace.htbase.metadata[0].name
  }

  data = {
    DATABASE_PASSWORD     = random_password.database_password.result
    HUGGINGFACE_API_KEY   = var.huggingface_api_key
    OPENAI_API_KEY        = var.openai_api_key
  }

  type = "Opaque"
}

resource "kubernetes_config_map" "htbase_config" {
  metadata {
    name      = "htbase-config"
    namespace = kubernetes_namespace.htbase.metadata[0].name
  }

  data = {
    ENVIRONMENT           = var.environment
    LOG_LEVEL             = var.log_level
    LOG_FORMAT            = "json"
    REDIS_URL             = "redis://${google_redis_instance.htbase.host}:${google_redis_instance.htbase.port}"
    CELERY_BROKER_URL     = "redis://${google_redis_instance.htbase.host}:${google_redis_instance.htbase.port}/0"
    CELERY_RESULT_BACKEND = "redis://${google_redis_instance.htbase.host}:${google_redis_instance.htbase.port}/1"
    GCS_BUCKET            = google_storage_bucket.archives.name
    GCS_PROJECT_ID        = var.project_id
    DATABASE_HOST         = google_sql_database_instance.htbase.private_ip_address
    DATABASE_NAME         = google_sql_database.htbase.name
    DATABASE_USER         = google_sql_user.htbase.name
  }
}

# =============================================================================
# API Gateway Deployment
# =============================================================================

resource "kubernetes_deployment" "api_gateway" {
  metadata {
    name      = "api-gateway"
    namespace = kubernetes_namespace.htbase.metadata[0].name
    labels = {
      app       = "htbase"
      component = "api-gateway"
    }
  }

  spec {
    replicas = var.api_gateway_min_instances

    selector {
      match_labels = {
        app       = "htbase"
        component = "api-gateway"
      }
    }

    template {
      metadata {
        labels = {
          app       = "htbase"
          component = "api-gateway"
        }
      }

      spec {
        service_account_name = kubernetes_service_account.htbase.metadata[0].name

        container {
          name  = "api-gateway"
          image = local.images.api_gateway

          port {
            container_port = 8080
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map.htbase_config.metadata[0].name
            }
          }

          env {
            name = "DATABASE_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.htbase_secrets.metadata[0].name
                key  = "DATABASE_PASSWORD"
              }
            }
          }

          env {
            name  = "WORKERS"
            value = "4"
          }

          env {
            name  = "CORS_ORIGINS"
            value = var.cors_origins
          }

          env {
            name  = "DEFAULT_ARCHIVERS"
            value = "singlefile,monolith,readability,pdf,screenshot"
          }

          resources {
            limits = {
              cpu    = var.api_gateway_cpu
              memory = var.api_gateway_memory
            }
            requests = {
              cpu    = "250m"
              memory = "256Mi"
            }
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 8080
            }
            initial_delay_seconds = 10
            period_seconds        = 30
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8080
            }
            initial_delay_seconds = 5
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "api_gateway" {
  metadata {
    name      = "api-gateway"
    namespace = kubernetes_namespace.htbase.metadata[0].name
  }

  spec {
    selector = {
      app       = "htbase"
      component = "api-gateway"
    }

    port {
      port        = 80
      target_port = 8080
    }

    type = "ClusterIP"
  }
}

resource "kubernetes_horizontal_pod_autoscaler" "api_gateway" {
  metadata {
    name      = "api-gateway"
    namespace = kubernetes_namespace.htbase.metadata[0].name
  }

  spec {
    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = kubernetes_deployment.api_gateway.metadata[0].name
    }

    min_replicas = var.api_gateway_min_instances
    max_replicas = var.api_gateway_max_instances

    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = 70
        }
      }
    }
  }
}

# =============================================================================
# Archive Worker Deployments
# =============================================================================

locals {
  archive_workers = {
    singlefile = {
      queue       = "archive.singlefile"
      concurrency = 2
      timeout     = 300
      cpu         = "2"
      memory      = "4Gi"
    }
    monolith = {
      queue       = "archive.monolith"
      concurrency = 3
      timeout     = 300
      cpu         = "2"
      memory      = "4Gi"
    }
    readability = {
      queue       = "archive.readability"
      concurrency = 5
      timeout     = 120
      cpu         = "1"
      memory      = "2Gi"
    }
    pdf = {
      queue       = "archive.pdf"
      concurrency = 3
      timeout     = 60
      cpu         = "1"
      memory      = "2Gi"
    }
    screenshot = {
      queue       = "archive.screenshot"
      concurrency = 3
      timeout     = 60
      cpu         = "1"
      memory      = "2Gi"
    }
  }
}

resource "kubernetes_deployment" "archive_workers" {
  for_each = local.archive_workers

  metadata {
    name      = "archive-worker-${each.key}"
    namespace = kubernetes_namespace.htbase.metadata[0].name
    labels = {
      app       = "htbase"
      component = "archive-worker"
      archiver  = each.key
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app       = "htbase"
        component = "archive-worker"
        archiver  = each.key
      }
    }

    template {
      metadata {
        labels = {
          app       = "htbase"
          component = "archive-worker"
          archiver  = each.key
        }
      }

      spec {
        service_account_name = kubernetes_service_account.htbase.metadata[0].name

        # Tolerate archive worker taint
        toleration {
          key      = "workload"
          operator = "Equal"
          value    = "archive"
          effect   = "NoSchedule"
        }

        # Prefer archive worker nodes
        affinity {
          node_affinity {
            preferred_during_scheduling_ignored_during_execution {
              weight = 100
              preference {
                match_expressions {
                  key      = "pool"
                  operator = "In"
                  values   = ["archive-workers"]
                }
              }
            }
          }
        }

        container {
          name  = "archive-worker"
          image = local.images.archive_worker

          env_from {
            config_map_ref {
              name = kubernetes_config_map.htbase_config.metadata[0].name
            }
          }

          env {
            name = "DATABASE_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.htbase_secrets.metadata[0].name
                key  = "DATABASE_PASSWORD"
              }
            }
          }

          env {
            name  = "WORKER_QUEUES"
            value = each.value.queue
          }

          env {
            name  = "WORKER_CONCURRENCY"
            value = tostring(each.value.concurrency)
          }

          env {
            name  = "ARCHIVER_TYPE"
            value = each.key
          }

          env {
            name  = "ARCHIVER_TIMEOUT"
            value = tostring(each.value.timeout)
          }

          resources {
            limits = {
              cpu    = each.value.cpu
              memory = each.value.memory
            }
            requests = {
              cpu    = "500m"
              memory = "1Gi"
            }
          }

          # Shared memory for Chrome
          volume_mount {
            name       = "dshm"
            mount_path = "/dev/shm"
          }
        }

        volume {
          name = "dshm"
          empty_dir {
            medium     = "Memory"
            size_limit = "2Gi"
          }
        }
      }
    }
  }
}

resource "kubernetes_horizontal_pod_autoscaler" "archive_workers" {
  for_each = local.archive_workers

  metadata {
    name      = "archive-worker-${each.key}"
    namespace = kubernetes_namespace.htbase.metadata[0].name
  }

  spec {
    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = kubernetes_deployment.archive_workers[each.key].metadata[0].name
    }

    min_replicas = 0
    max_replicas = var.archive_worker_max_instances

    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = 70
        }
      }
    }
  }
}

# =============================================================================
# Summarization Worker Deployment
# =============================================================================

resource "kubernetes_deployment" "summarization_worker" {
  metadata {
    name      = "summarization-worker"
    namespace = kubernetes_namespace.htbase.metadata[0].name
    labels = {
      app       = "htbase"
      component = "summarization-worker"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app       = "htbase"
        component = "summarization-worker"
      }
    }

    template {
      metadata {
        labels = {
          app       = "htbase"
          component = "summarization-worker"
        }
      }

      spec {
        service_account_name = kubernetes_service_account.htbase.metadata[0].name

        container {
          name  = "summarization-worker"
          image = local.images.summarization_worker

          env_from {
            config_map_ref {
              name = kubernetes_config_map.htbase_config.metadata[0].name
            }
          }

          env {
            name = "DATABASE_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.htbase_secrets.metadata[0].name
                key  = "DATABASE_PASSWORD"
              }
            }
          }

          env {
            name = "HUGGINGFACE_API_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.htbase_secrets.metadata[0].name
                key  = "HUGGINGFACE_API_KEY"
              }
            }
          }

          env {
            name = "OPENAI_API_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.htbase_secrets.metadata[0].name
                key  = "OPENAI_API_KEY"
              }
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

          resources {
            limits = {
              cpu    = "1"
              memory = "1Gi"
            }
            requests = {
              cpu    = "250m"
              memory = "512Mi"
            }
          }
        }
      }
    }
  }
}

# =============================================================================
# Storage Worker Deployment
# =============================================================================

resource "kubernetes_deployment" "storage_worker" {
  metadata {
    name      = "storage-worker"
    namespace = kubernetes_namespace.htbase.metadata[0].name
    labels = {
      app       = "htbase"
      component = "storage-worker"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app       = "htbase"
        component = "storage-worker"
      }
    }

    template {
      metadata {
        labels = {
          app       = "htbase"
          component = "storage-worker"
        }
      }

      spec {
        service_account_name = kubernetes_service_account.htbase.metadata[0].name

        container {
          name  = "storage-worker"
          image = local.images.storage_worker

          env_from {
            config_map_ref {
              name = kubernetes_config_map.htbase_config.metadata[0].name
            }
          }

          env {
            name = "DATABASE_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.htbase_secrets.metadata[0].name
                key  = "DATABASE_PASSWORD"
              }
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

          resources {
            limits = {
              cpu    = "1"
              memory = "1Gi"
            }
            requests = {
              cpu    = "250m"
              memory = "256Mi"
            }
          }
        }
      }
    }
  }
}

# =============================================================================
# Kubernetes Service Account with Workload Identity
# =============================================================================

resource "kubernetes_service_account" "htbase" {
  metadata {
    name      = "htbase"
    namespace = kubernetes_namespace.htbase.metadata[0].name
    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.htbase.email
    }
  }
}

resource "google_service_account_iam_member" "htbase_workload_identity" {
  service_account_id = google_service_account.htbase.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${kubernetes_namespace.htbase.metadata[0].name}/htbase]"
}

# =============================================================================
# Ingress with Google Cloud Load Balancer
# =============================================================================

resource "kubernetes_ingress_v1" "htbase" {
  metadata {
    name      = "htbase-ingress"
    namespace = kubernetes_namespace.htbase.metadata[0].name
    annotations = {
      "kubernetes.io/ingress.class"                 = "gce"
      "kubernetes.io/ingress.global-static-ip-name" = google_compute_global_address.htbase.name
      "networking.gke.io/managed-certificates"      = "htbase-cert"
    }
  }

  spec {
    default_backend {
      service {
        name = kubernetes_service.api_gateway.metadata[0].name
        port {
          number = 80
        }
      }
    }

    rule {
      host = var.domain
      http {
        path {
          path      = "/*"
          path_type = "ImplementationSpecific"
          backend {
            service {
              name = kubernetes_service.api_gateway.metadata[0].name
              port {
                number = 80
              }
            }
          }
        }
      }
    }
  }
}

resource "google_compute_global_address" "htbase" {
  name = "htbase-ip-${var.environment}"
}

# =============================================================================
# Managed Certificate
# =============================================================================

resource "kubernetes_manifest" "managed_certificate" {
  count = var.domain != "" ? 1 : 0

  manifest = {
    apiVersion = "networking.gke.io/v1"
    kind       = "ManagedCertificate"
    metadata = {
      name      = "htbase-cert"
      namespace = kubernetes_namespace.htbase.metadata[0].name
    }
    spec = {
      domains = [var.domain]
    }
  }
}
