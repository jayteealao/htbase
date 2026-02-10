# =============================================================================
# Production Environment Configuration
# =============================================================================

project_id  = "your-project-id"  # Replace with your GCP project ID
region      = "us-central1"
environment = "production"
image_tag   = "latest"

# =============================================================================
# Redis Configuration
# =============================================================================

redis_tier      = "STANDARD_HA"  # High availability for production
redis_memory_gb = 2

# =============================================================================
# Cloud SQL Configuration
# =============================================================================

cloudsql_tier      = "db-custom-2-8192"  # 2 vCPU, 8GB RAM
cloudsql_disk_size = 50

# =============================================================================
# API Gateway Configuration
# =============================================================================

api_gateway_min_instances = 1
api_gateway_max_instances = 20
api_gateway_cpu           = "2"
api_gateway_memory        = "1Gi"
cors_origins              = "https://app.htbase.com,https://htbase.com"
api_rate_limit            = "100/minute"

# =============================================================================
# Worker Configuration
# =============================================================================

archive_worker_max_instances       = 20
summarization_worker_max_instances = 10
storage_worker_max_instances       = 15

# =============================================================================
# LLM Configuration
# =============================================================================

llm_provider        = "huggingface"  # or "openai"
huggingface_api_url = ""             # Set your TGI endpoint
openai_model        = "gpt-4o-mini"

# =============================================================================
# Logging
# =============================================================================

log_level = "INFO"
