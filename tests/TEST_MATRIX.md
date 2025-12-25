# HTBase Test Coverage Matrix

**Last Updated:** 2025-12-07
**Coverage:** Comprehensive test suite covering all TESTING_PLAN.md requirements

## Overview

This document maps automated tests to TESTING_PLAN.md test cases and tracks coverage across the codebase.

## Test Structure

```
tests/
├── unit/                    # Fast, isolated unit tests
├── integration/             # Component integration tests
├── e2e/                     # End-to-end system tests
└── fakes/                   # Test doubles and fakes
```

## Coverage by TESTING_PLAN Test Case

### ✅ Test Case 1: Local Storage Backend (Default)

| Test Case | Test File | Test Function | Status |
|-----------|-----------|---------------|--------|
| 1.2.1: Basic Archiving | `integration/test_local_storage_workflow.py` | `test_save_retrieve_workflow_single_archiver` | ✅ |
| 1.2.2: Multiple Archivers | `integration/test_local_storage_workflow.py` | `test_save_multiple_archivers_same_item` | ✅ |
| 1.3.1: Single File Retrieval | `integration/test_local_storage_workflow.py` | `test_save_retrieve_workflow_single_archiver` | ✅ |
| 1.3.2: Bundle Retrieval | `integration/test_local_storage_workflow.py` | `test_bundle_creation_all_archivers`<br>`test_bundle_extraction_and_content` | ✅ |
| 1.4: Static File Mounting | `integration/test_static_file_mounting.py` | `test_static_mounting_enabled_for_local_storage`<br>`test_static_file_serving_local_storage` | ✅ |

### ✅ Test Case 2: GCS Storage Backend

| Test Case | Test File | Test Function | Status |
|-----------|-----------|---------------|--------|
| 2.2.1: GCS Upload (Mock) | `integration/test_gcs_storage_workflow_mock.py` | `test_gcs_upload_with_compression_mock` | ✅ |
| 2.2.1: GCS Upload (Real) | `integration/test_gcs_storage_workflow_real.py` | `test_gcs_upload_real_compression_ratio` | ✅ |
| 2.2.2: DB GCS Path Tracking (Mock) | `integration/test_gcs_storage_workflow_mock.py` | `test_gcs_path_tracking_in_database_mock` | ✅ |
| 2.2.2: DB GCS Path Tracking (Real) | `integration/test_gcs_storage_workflow_real.py` | `test_gcs_metadata_storage_real` | ✅ |
| 2.3.1: GCS File Retrieval (Mock) | `integration/test_gcs_storage_workflow_mock.py` | `test_gcs_file_retrieval_via_api_mock` | ✅ |
| 2.3.1: GCS File Retrieval (Real) | `integration/test_gcs_storage_workflow_real.py` | `test_gcs_upload_download_roundtrip_real` | ✅ |
| 2.4: Static Mounting Bypass | `integration/test_static_file_mounting.py` | `test_static_mounting_disabled_for_gcs_storage` | ✅ |
| 2.5.1: GCS Error Handling (Mock) | `integration/test_gcs_storage_workflow_mock.py` | `test_gcs_upload_failure_handling_mock` | ✅ |
| 2.5.1: GCS Error Handling (Real) | `integration/test_gcs_storage_workflow_real.py` | `test_gcs_invalid_credentials_fallback_real` | ✅ |

### ✅ Test Case 3: Firestore Database Backend

| Test Case | Test File | Test Function | Status |
|-----------|-----------|---------------|--------|
| 3.2.1: Firestore Storage (Mock) | `integration/test_firestore_integration_mock.py` | `test_firestore_article_creation_mock` | ✅ |
| 3.2.1: Firestore Storage (Real) | `integration/test_firestore_integration_real.py` | `test_firestore_article_creation_real` | ✅ |
| 3.2.2: Document Structure (Mock) | `integration/test_firestore_integration_mock.py` | `test_firestore_document_structure_validation_mock` | ✅ |
| 3.2.2: Document Structure (Real) | `integration/test_firestore_integration_real.py` | `test_firestore_document_structure_real` | ✅ |
| 3.3: Firestore + GCS (Mock) | `integration/test_firestore_integration_mock.py` | `test_firestore_gcs_integration_mock` | ✅ |
| 3.3: Firestore + GCS (Real) | `integration/test_firestore_integration_real.py` | `test_firestore_gcs_full_cloud_workflow_real` | ✅ |

### ✅ Test Case 4: Error Handling & Fallback

| Test Case | Test File | Test Function | Status |
|-----------|-----------|---------------|--------|
| 4.1.1: Invalid URL | `integration/test_error_handling.py` | `test_invalid_url_handling` | ✅ |
| 4.1.2: Network Errors | `integration/test_error_handling.py` | `test_network_error_during_url_check` | ✅ |
| 4.2.1: Permission Errors | `integration/test_error_handling.py` | `test_permission_denied_on_data_dir` | ✅ |
| 4.2.2: Disk Space Full | `integration/test_error_handling.py` | `test_disk_space_full_simulation` | ✅ |
| 4.3.2: Corrupted DB Records | `integration/test_error_handling.py` | `test_corrupted_database_record_handling` | ✅ |
| 4.X: Partial Upload Failure | `integration/test_error_handling.py` | `test_partial_storage_upload_failure` | ✅ |
| 4.X: Timeout Handling | `integration/test_error_handling.py` | `test_archiver_timeout_handling` | ✅ |

### ✅ Test Case 5: Performance & Load Testing

| Test Case | Test File | Test Function | Status |
|-----------|-----------|---------------|--------|
| 5.1.1: Local File Serving | `integration/test_performance_benchmarks.py` | `test_local_file_serving_performance` | ✅ |
| 5.1.2: GCS File Serving | `integration/test_performance_benchmarks.py` | `test_gcs_file_serving_performance_mock` | ✅ |
| 5.2.1: Memory Usage | `integration/test_performance_benchmarks.py` | `test_memory_usage_during_bundle_creation` | ✅ |
| 5.3.1: Compression Ratio | `integration/test_performance_benchmarks.py` | `test_compression_ratio_reporting` | ✅ |
| 5.X: Concurrent Uploads | `integration/test_performance_benchmarks.py` | `test_concurrent_upload_performance` | ✅ |
| 5.X: DB Query Performance | `integration/test_performance_benchmarks.py` | `test_database_query_performance` | ✅ |

### ✅ Test Case 6: Background Task Integration

| Test Case | Test File | Test Function | Status |
|-----------|-----------|---------------|--------|
| 6.1.1: Batch Create | Existing: `integration/test_task_processing.py` | Various | ✅ |
| 6.1.2: Task Completion | Existing: `integration/test_task_processing.py` | Various | ✅ |
| 6.2.1: Background + GCS | Existing: `integration/test_task_processing.py` | Various | ✅ |

### ✅ Test Case 7: Configuration Validation

| Test Case | Test File | Test Function | Status |
|-----------|-----------|---------------|--------|
| 7.1.1: Invalid Backend Fallback | `unit/test_config.py` | `test_invalid_storage_backend_fallback` | ✅ |
| 7.1.2: Missing Backend Defaults | `unit/test_config.py` | `test_missing_storage_backend_defaults_to_local` | ✅ |
| 7.2: Configuration Validation | `unit/test_config.py` | `test_configuration_validation_detects_missing_gcs_bucket`<br>`test_storage_providers_list_parsing`<br>`test_database_url_construction` | ✅ |

## Test Statistics

### Overall Coverage

- **Total Test Cases Planned**: 40+ from TESTING_PLAN.md
- **Test Cases Implemented**: 40+
- **Coverage**: 100% of TESTING_PLAN requirements
- **Total Test Functions**: ~150
- **Lines of Test Code**: ~2,500+

### By Test Type

| Type | Files | Functions | Coverage |
|------|-------|-----------|----------|
| Unit | 15+ | 80+ | Comprehensive |
| Integration | 12 | 60+ | Comprehensive |
| E2E | 3 | 20+ | Good |
| **Total** | **30+** | **160+** | **100%** |

### By Module

| Module | Unit | Integration | E2E | Total |
|--------|------|-------------|-----|-------|
| Config | 25+ | 0 | 0 | 25+ |
| Storage | 30+ | 35+ | 0 | 65+ |
| Archivers | 15+ | 10+ | 10+ | 35+ |
| API | 10+ | 15+ | 10+ | 35+ |
| **Total** | **80+** | **60+** | **20+** | **160+** |

## Test Execution

### Local Development

```bash
# Run all unit tests (fast)
pytest tests/unit -v

# Run integration tests (local only)
pytest tests/integration -v -m "not gcs and not firestore"

# Run with real GCS (requires credentials)
export TEST_GCS_BUCKET=htbase-test-bucket
export TEST_GCS_PROJECT_ID=my-project
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
pytest tests/integration -v -m gcs

# Run performance benchmarks (reporting only)
pytest tests/integration/test_performance_benchmarks.py -v

# Run with coverage
pytest tests/unit tests/integration -v --cov=app --cov-report=html
```

### CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/test-suite.yml`) runs:

1. **Unit Tests** - Every push/PR
2. **Integration Tests** (local) - Every push/PR
3. **Cloud Integration Tests** - Main branch only
4. **Performance Benchmarks** - Main branch only
5. **E2E Tests** - Main branch and PRs to main

## Test Markers

Tests use pytest markers for selective execution:

- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Integration tests (may need DB)
- `@pytest.mark.e2e` - End-to-end system tests
- `@pytest.mark.gcs` - Requires real GCS credentials
- `@pytest.mark.firestore` - Requires real Firestore credentials
- `@pytest.mark.performance` - Performance benchmark tests
- `@pytest.mark.slow` - Tests taking > 5 seconds

## Performance Targets

Performance tests report metrics but do NOT fail on threshold violations:

| Metric | Target | Status |
|--------|--------|--------|
| Local file serving | < 500ms | Reporting |
| GCS file serving | < 1000ms | Reporting |
| Compression ratio | > 70% | Reporting |
| Memory usage (bundle) | Reasonable | Reporting |
| DB query time | < 100ms | Reporting |

## Test Fakes and Doubles

High-quality fakes for fast, deterministic testing:

| Fake | Purpose | File |
|------|---------|------|
| `InMemoryFileStorage` | Fast file storage without disk I/O | `tests/fakes/storage.py` |
| `InMemoryDatabaseStorage` | Fast database without PostgreSQL | `tests/fakes/storage.py` |
| `SyncTaskManager` | Synchronous task processing | `tests/fakes/task_manager.py` |
| `FakeCommandRunner` | Command execution without subprocess | `tests/fakes/command_runner.py` |
| `DummyArchiver` | Archiver without external binaries | `tests/conftest.py` |

## Continuous Improvement

### Adding New Tests

1. Choose appropriate test type (unit/integration/e2e)
2. Use existing fixtures and fakes when possible
3. Add test to this matrix
4. Update TEST_MATRIX.md with coverage
5. Add appropriate pytest markers

### Maintaining Tests

- Update tests when features change
- Keep fakes synchronized with real implementations
- Monitor CI/CD for flaky tests
- Review performance trends from benchmarks

## References

- **TESTING_PLAN.md** - Original manual testing plan
- **CLAUDE.md** - Project structure and patterns
- **pytest.ini** - Pytest configuration
- **.github/workflows/test-suite.yml** - CI/CD configuration
