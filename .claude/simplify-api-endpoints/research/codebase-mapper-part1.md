# Codebase Mapper Research Report

**Date**: 2026-01-16
**Feature**: API Endpoint Simplification - Remove 3 deprecated endpoints and consolidate duplicates
**Component Type**: API endpoints
**Search Scope**: Repository-wide analysis

---

## Executive Summary

This research identifies all callers and consumers of the 28 HTBase API endpoints planned for simplification. Analysis reveals:

**Key Findings**:
- 3 deprecated Firebase endpoints actively marked for removal in v2.0.0
- 4 client types identified: Frontend React app, Cloud Functions, Example code, Test suites
- Migration path already documented and partially implemented
- Microservices architecture (api-gateway) is production-ready replacement
- Low breaking change risk due to existing deprecation warnings

**Client Types Found**: 4
- Frontend UI (React + TypeScript)
- Firebase Cloud Functions (Node.js)
- Example code (Python, JavaScript, Bash)
- Integration tests (pytest)

**Risk Hotspots Identified**: 2
- Firebase Cloud Function production dependency on /firebase/archive
- Frontend UI uses /api/save/ endpoints (safe, not deprecated)

---
