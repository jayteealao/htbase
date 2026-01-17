-- Migration: Add URL format validation CHECK constraint
-- Issue: CR-NEW-5 from correctness review
-- Date: 2026-01-17
-- Priority: LOW (defense-in-depth, API already validates)

-- Add CHECK constraint to ensure URLs are valid HTTP/HTTPS format
ALTER TABLE archived_urls
ADD CONSTRAINT archived_urls_url_format_check
CHECK (url ~ '^https?://');

-- Rationale:
-- - API layer already validates URLs using Pydantic HttpUrl
-- - This constraint provides database-level protection against direct SQL inserts
-- - Prevents garbage data from entering the database
-- - Defense-in-depth security practice

-- Rollback:
-- ALTER TABLE archived_urls DROP CONSTRAINT archived_urls_url_format_check;
