# HTBase Integration Tests

This directory contains the integration test suite for HTBase.

## Structure

```
tests/
├── conftest.py              # Shared fixtures and test configuration
├── unit/                    # Unit tests (isolated components)
│   ├── test_repositories.py # Repository pattern tests
│   └── ...
├── integration/             # Integration tests (multiple components)
│   ├── test_archive_workflow.py  # End-to-end workflow tests
│   └── ...
└── README.md               # This file
```

## Running Tests

### Install dependencies

```bash
# Install shared package in editable mode
pip install -e ../../shared

# Install test dependencies
pip install pytest pytest-asyncio pytest-cov
```

### Run all tests

```bash
pytest
```

### Run specific test file

```bash
pytest tests/integration/test_archive_workflow.py
```

### Run with coverage

```bash
pytest --cov=shared --cov=services --cov-report=html
```

### Run only integration tests

```bash
pytest -m integration
```

## Test Patterns

### Repository Pattern Tests

Tests use mock Firestore clients to avoid needing real Firestore:

```python
def test_create_article(article_repository, sample_article_data):
    article = article_repository.create(**sample_article_data)
    assert article["item_id"] == sample_article_data["item_id"]
```

### API Endpoint Tests with Dependency Injection

Override FastAPI dependencies with mocks:

```python
from shared.web.dependencies import get_article_repository

app.dependency_overrides[get_article_repository] = lambda: mock_repository

response = client.post("/api/v1/archives", json={...})
assert response.status_code == 200
```

### End-to-End Integration Tests

Test complete workflows:

```python
@pytest.mark.integration
def test_complete_archive_flow(article_repository, artifact_repository):
    # Create article
    article_repository.create(...)

    # Archive it
    artifact_repository.update(..., status="in_progress")

    # Complete archiving
    artifact_repository.update(..., status="success", gcs_path="...")

    # Verify final state
    artifact = artifact_repository.get(...)
    assert artifact["status"] == "success"
```

## Fixtures

### Mock Firestore Client

`mock_firestore_client` - In-memory Firestore implementation for testing

### Repositories

- `article_repository` - ArticleRepository with mock Firestore
- `artifact_repository` - ArtifactRepository with mock Firestore

### Test Data

- `sample_article_data` - Sample article data dictionary

### API Client

- `api_client` - FastAPI TestClient for API testing

### Mocks

- `mock_celery_app` - Mocked Celery app for testing without broker

## Best Practices

1. **Use fixtures** - Leverage pytest fixtures for setup/teardown
2. **Test isolation** - Each test should be independent
3. **Mock external services** - Use mocks for Firestore, GCS, Celery
4. **Clear assertions** - Make assertions explicit and meaningful
5. **Test edge cases** - Don't just test happy paths
6. **Use markers** - Mark tests with `@pytest.mark.integration`, etc.

## Example: Writing a New Test

```python
def test_archive_validation(article_repository):
    """Test that invalid data raises appropriate errors."""
    # Test missing required field
    with pytest.raises(Exception):
        article_repository.create(item_id="", url="https://example.com")

    # Test invalid URL format
    # ...

    # Test duplicate ID handling
    article_repository.create(item_id="test", url="https://example.com")
    # Should handle gracefully or raise specific error
```

## Troubleshooting

### Import Errors

Make sure the shared package is installed:
```bash
pip install -e ../../shared
```

### Firestore Emulator (for real Firestore tests)

To test against real Firestore emulator:

```bash
# Install emulator
gcloud components install cloud-firestore-emulator

# Start emulator
gcloud beta emulators firestore start

# Set environment variable
export FIRESTORE_EMULATOR_HOST=localhost:8080

# Run tests
pytest
```

## Coverage Goals

- **Unit tests**: >80% coverage
- **Integration tests**: Cover critical workflows
- **End-to-end tests**: Cover main user journeys
