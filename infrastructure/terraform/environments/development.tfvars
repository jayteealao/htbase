# =============================================================================
# Development Environment Configuration
# =============================================================================

project_id  = "your-project-id"  # Replace with your GCP project ID
region      = "us-central1"
environment = "development"
image_tag   = "dev"

# =============================================================================
# Redis Configuration (minimal for dev)
# =============================================================================

redis_tier      = "BASIC"
redis_memory_gb = 1

# =============================================================================
# Cloud SQL Configuration (minimal for dev)
# =============================================================================

cloudsql_tier      = "db-custom-1-3840"  # 1 vCPU, 3.75GB RAM
cloudsql_disk_size = 10

# =============================================================================
# API Gateway Configuration
# =============================================================================

api_gateway_min_instances = 0  # Scale to zero when idle
api_gateway_max_instances = 3
api_gateway_cpu           = "1"
api_gateway_memory        = "512Mi"
cors_origins              = "*"
api_rate_limit            = "1000/minute"

# =============================================================================
# Worker Configuration (minimal for dev)
# =============================================================================

archive_worker_max_instances       = 3
summarization_worker_max_instances = 2
storage_worker_max_instances       = 3

# =============================================================================
# LLM Configuration
# =============================================================================

llm_provider        = "huggingface"
huggingface_api_url = ""
openai_model        = "gpt-4o-mini"

# =============================================================================
# Logging
# =============================================================================

log_level = "DEBUG"
