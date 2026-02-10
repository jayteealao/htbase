-- =============================================================================
-- HT Base - PostgreSQL Initialization Script
-- =============================================================================
-- This script runs on first database initialization
-- =============================================================================

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create indexes for common query patterns (if tables already exist from migrations)
-- These are defensive - Alembic migrations should handle schema creation

-- Performance tuning for containerized environment
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '512MB';
ALTER SYSTEM SET work_mem = '16MB';
ALTER SYSTEM SET maintenance_work_mem = '64MB';
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;
ALTER SYSTEM SET max_connections = 100;

-- Logging configuration
ALTER SYSTEM SET log_statement = 'ddl';
ALTER SYSTEM SET log_duration = 'on';
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- Log queries > 1s

-- Note: Run SELECT pg_reload_conf(); after changes or restart container
