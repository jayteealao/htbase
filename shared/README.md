# HTBase Shared Library

Shared library for HTBase microservices containing common code, configuration, database access, and utilities.

## Installation

Install in editable mode for development:

```bash
pip install -e .
```

Or install from a service:

```bash
# In services/api-gateway/requirements.txt
-e ../../shared
```

## Modules

- **config** - Environment-based configuration with Pydantic
- **firestore/** - Firestore database access layer (articles, artifacts, summaries, etc.)
- **firestore_client** - Firestore client singleton
- **celery_config** - Celery application and queue configuration
- **models** - Pydantic request/response models
- **storage/** - GCS file storage abstraction
- **summarization/** - AI summarization service
- **auth** - API key authentication
- **rate_limit** - Rate limiting middleware
- **utils/** - Helper functions

## Usage

```python
from shared.config import get_settings
from shared.firestore import create_article, get_article
from shared.celery_config import celery_app

# Configuration
settings = get_settings()

# Database access
article = create_article(item_id="123", url="https://example.com")

# Celery tasks
@celery_app.task
def my_task():
    pass
```

## Development

Run tests:

```bash
pytest
```

Format code:

```bash
black .
ruff check .
```

Type checking:

```bash
mypy .
```
