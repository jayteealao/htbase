-- Migration: Ensure all timestamps use UTC
-- Issue: CR-NEW-6 from correctness review
-- Date: 2026-01-17
-- Priority: LOW (verify PostgreSQL timezone setting)

-- Option 1: Verify PostgreSQL is configured to use UTC globally
-- Check current setting:
-- SHOW timezone;

-- If not UTC, set at database level:
-- ALTER DATABASE htbase SET timezone = 'UTC';

-- Option 2: Update all server_default to explicitly use UTC
-- This is more explicit and doesn't depend on database configuration

-- Example for archived_urls table:
-- ALTER TABLE archived_urls
-- ALTER COLUMN created_at SET DEFAULT (now() AT TIME ZONE 'UTC');

-- Apply to all tables with created_at/updated_at columns:
-- - archived_urls
-- - archive_artifacts
-- - url_metadata
-- - article_summaries
-- - article_entities
-- - article_tags
-- - command_executions
-- - command_output_lines

-- Rationale:
-- - Application code uses datetime.utcnow() consistently
-- - Database defaults should also use UTC for consistency
-- - Prevents timezone confusion when servers in different regions
-- - Avoids daylight saving time issues

-- Current State:
-- - Python code: Uses datetime.utcnow() ✅
-- - Database defaults: Uses now() ⚠️ (depends on PostgreSQL timezone setting)

-- Recommended Action:
-- 1. Verify PostgreSQL timezone is UTC: SHOW timezone;
-- 2. If not UTC, either:
--    a. Set database timezone to UTC (simpler)
--    b. Update all server_default to use AT TIME ZONE 'UTC'
