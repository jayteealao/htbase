# =============================================================================
# Terraform Variables
# =============================================================================

# =============================================================================
# Project Configuration
# =============================================================================

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name (development, staging, production)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be one of: development, staging, production."
  }
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

# =============================================================================
# Redis Configuration
# =============================================================================

variable "redis_tier" {
  description = "Redis tier (BASIC or STANDARD_HA)"
  type        = string
  default     = "BASIC"
}

variable "redis_memory_gb" {
  description = "Redis memory size in GB"
  type        = number
  default     = 1
}

# =============================================================================
# Cloud SQL Configuration
# =============================================================================

variable "cloudsql_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-custom-2-4096"
}

variable "cloudsql_disk_size" {
  description = "Cloud SQL disk size in GB"
  type        = number
  default     = 20
}

# =============================================================================
# API Gateway Configuration
# =============================================================================

variable "api_gateway_min_instances" {
  description = "Minimum number of API Gateway instances"
  type        = number
  default     = 1
}

variable "api_gateway_max_instances" {
  description = "Maximum number of API Gateway instances"
  type        = number
  default     = 10
}

variable "api_gateway_cpu" {
  description = "API Gateway CPU limit"
  type        = string
  default     = "1"
}

variable "api_gateway_memory" {
  description = "API Gateway memory limit"
  type        = string
  default     = "512Mi"
}

variable "cors_origins" {
  description = "CORS allowed origins"
  type        = string
  default     = "*"
}

variable "api_rate_limit" {
  description = "API rate limit"
  type        = string
  default     = "100/minute"
}

# =============================================================================
# Worker Configuration
# =============================================================================

variable "archive_worker_max_instances" {
  description = "Maximum number of archive worker instances per type"
  type        = number
  default     = 10
}

variable "summarization_worker_max_instances" {
  description = "Maximum number of summarization worker instances"
  type        = number
  default     = 5
}

variable "storage_worker_max_instances" {
  description = "Maximum number of storage worker instances"
  type        = number
  default     = 10
}

# =============================================================================
# LLM Configuration
# =============================================================================

variable "llm_provider" {
  description = "LLM provider (huggingface, openai)"
  type        = string
  default     = "huggingface"
}

variable "huggingface_api_url" {
  description = "HuggingFace TGI API URL"
  type        = string
  default     = ""
}

variable "openai_model" {
  description = "OpenAI model to use"
  type        = string
  default     = "gpt-4o-mini"
}

# =============================================================================
# Logging Configuration
# =============================================================================

variable "log_level" {
  description = "Log level (DEBUG, INFO, WARNING, ERROR)"
  type        = string
  default     = "INFO"
}

# =============================================================================
# Domain Configuration
# =============================================================================

variable "domain" {
  description = "Domain name for the application (leave empty for no ingress)"
  type        = string
  default     = ""
}

# =============================================================================
# Secret Values (for GKE deployment)
# =============================================================================

variable "huggingface_api_key" {
  description = "HuggingFace API key"
  type        = string
  default     = ""
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  default     = ""
  sensitive   = true
}
