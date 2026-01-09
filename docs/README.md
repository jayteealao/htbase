# HTBase Documentation

Complete documentation for HTBase - a web archiving service designed for programmatic access by developers and AI agents.

## Quick Links

- **[API Quickstart](API_QUICKSTART.md)** - Get started in 5 minutes
- **[Error Codes Reference](ERROR_CODES.md)** - Complete error code documentation
- **[Agent Best Practices](AGENT_GUIDE.md)** - Patterns for AI agents
- **[Code Examples](../examples/)** - Python, JavaScript, and curl examples

## Documentation Structure

### Getting Started
- [API Quickstart](API_QUICKSTART.md) - 5-minute getting started guide with curl examples
- [Code Examples](../examples/) - Working code samples in multiple languages

### Core Concepts
- [Error Codes Reference](ERROR_CODES.md) - All error codes with resolution steps
- [Agent Best Practices](AGENT_GUIDE.md) - Architecture patterns and optimization strategies

### Planned Features
- [Authentication Guide](AUTHENTICATION.md) - API key setup (not yet implemented)
- [Webhooks Guide](WEBHOOKS.md) - Real-time notifications (not yet implemented)

### Architecture & Technical
- [Rearchitecture Plan](REARCHITECTURE_PLAN.md) - Comprehensive technical architecture
- [Transaction Boundaries](TRANSACTION_BOUNDARIES.md) - Database transaction patterns
- [Transaction Flow Diagram](TRANSACTION_FLOW_DIAGRAM.md) - Visual flow documentation

### Migration
- [Migration Runbook](migration/MIGRATION_RUNBOOK.md) - Step-by-step migration guide
- [Rollback Procedure](migration/ROLLBACK_PROCEDURE.md) - Emergency rollback steps
- [Implementation Summary](migration/IMPLEMENTATION_SUMMARY.md) - Migration implementation details

## What is HTBase?

HTBase is a web archiving service that captures web pages in multiple formats:

- **Readability** - Clean text extraction (ideal for AI/LLM processing)
- **Monolith** - Single HTML file with embedded assets
- **SingleFile** - High-fidelity complete page preservation
- **PDF** - Print-ready PDF rendering
- **Screenshot** - Visual PNG snapshots

### Key Features

✅ **Multiple Archivers** - Choose the format that fits your use case
✅ **Batch Operations** - Archive hundreds of URLs efficiently
✅ **Task Tracking** - Poll or webhook for completion status
✅ **AI Summaries** - Automatic LLM-powered summarization
✅ **Storage Flexibility** - Local filesystem or Google Cloud Storage
✅ **Agent-Friendly** - Designed for programmatic access

## Quick Start

### 1. Start the Server

```bash
docker compose up -d
```

### 2. Archive Your First URL

```bash
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "my-first-save",
    "url": "https://example.com"
  }'
```

### 3. Retrieve the Archive

```bash
curl http://localhost:8000/api/retrieve?id=my-first-save&archiver=readability \
  --output my-first-save.html
```

**That's it!** See [API Quickstart](API_QUICKSTART.md) for more examples.

## Common Workflows

### Archive a News Article for AI Processing

```bash
# 1. Archive with readability (clean text)
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Content-Type: application/json' \
  -d '{"id": "news-article", "url": "https://example.com/article"}'

# 2. Automatic summarization happens in background

# 3. Retrieve clean HTML
curl "http://localhost:8000/api/retrieve?id=news-article&archiver=readability" \
  --output article.html
```

### Archive Multiple URLs from RSS Feed

```bash
# 1. Submit batch request
curl -X POST http://localhost:8000/api/batch/readability \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {"id": "article-1", "url": "https://example.com/1"},
      {"id": "article-2", "url": "https://example.com/2"},
      {"id": "article-3", "url": "https://example.com/3"}
    ]
  }'

# Response: {"task_id": "batch-abc123", "count": 3}

# 2. Check status
curl http://localhost:8000/api/tasks/batch-abc123
```

See [Agent Best Practices](AGENT_GUIDE.md) for complete examples.

### Preserve Complete Website

```bash
# Archive with all formats
curl -X POST http://localhost:8000/api/save/all \
  -H 'Content-Type: application/json' \
  -d '{"id": "website-backup", "url": "https://example.com"}'

# Download all formats as tarball
curl "http://localhost:8000/api/retrieve?id=website-backup&archiver=all" \
  --output website-backup.tar.gz
```

## Available Archivers

| Archiver | Speed | Output | Best For |
|----------|-------|--------|----------|
| **readability** | Fast (5-10s) | Clean HTML + JSON metadata | AI/LLM processing, text extraction |
| **monolith** | Fast (5-15s) | Single HTML file | Quick preservation, offline viewing |
| **singlefile-cli** | Slow (15-30s) | High-fidelity HTML | Complete preservation, exact rendering |
| **pdf** | Medium (10-25s) | PDF document | Print-ready documents, archival |
| **screenshot** | Fast (5-10s) | PNG image | Visual verification, thumbnails |
| **all** | Slow (30-60s) | All formats | Comprehensive archiving |

## Core Endpoints

```
POST /api/save/{archiver}        # Archive single URL
POST /api/batch/{archiver}       # Archive multiple URLs
GET  /api/tasks/{task_id}        # Check task status
GET  /api/retrieve               # Download archive
POST /api/admin/summarize        # Generate AI summary
GET  /api/health                 # Health check
```

See [API Quickstart](API_QUICKSTART.md) for complete endpoint documentation.

## Error Handling

HTBase uses standard HTTP status codes and archiver exit codes:

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | None |
| 404 | URL not found | Verify URL is correct |
| 21 | Chromium lock error | Restart service |
| 400 | Bad request | Fix request format |
| 500 | Server error | Check logs |

See [Error Codes Reference](ERROR_CODES.md) for complete documentation.

## Production Deployment

### Prerequisites

Before deploying to production:

1. ✅ Review [Rearchitecture Plan](REARCHITECTURE_PLAN.md)
2. ⚠️  Implement [Authentication](AUTHENTICATION.md) (P0 - not yet implemented)
3. ⚠️  Set up rate limiting (P0 - not yet implemented)
4. ✅ Configure storage backend (GCS recommended)
5. ✅ Set up PostgreSQL for persistence
6. 🔄 Optionally enable [Webhooks](WEBHOOKS.md) (P2 - not yet implemented)

### Deployment Checklist

- [ ] Enable authentication with API keys
- [ ] Configure rate limiting per key
- [ ] Set up GCS for file storage
- [ ] Configure PostgreSQL with connection pooling
- [ ] Enable HTTPS
- [ ] Set up monitoring and alerts
- [ ] Configure backup strategy
- [ ] Test failover procedures

See [Rearchitecture Plan](REARCHITECTURE_PLAN.md) for deployment architecture.

## Development

### Running Locally

```bash
# Clone repository
git clone https://github.com/your-org/htbase.git
cd htbase

# Start services
docker compose up --build

# Run examples
cd examples/python
python simple_archive.py
```

### Running Tests

```bash
# Unit tests
pytest tests/

# Integration tests
pytest tests/integration/

# With coverage
pytest --cov=app tests/
```

### Environment Variables

Key configuration options:

```bash
# Data directory
DATA_DIR=./data

# Logging
LOG_LEVEL=INFO

# Storage
STORAGE_PROVIDERS=local,gcs
GCS_BUCKET=your-bucket-name

# Features
SUMMARIZATION_ENABLED=true
SKIP_EXISTING_SAVES=true

# Database
DATABASE_URL=postgresql://user:pass@localhost/htbase
```

See [Rearchitecture Plan](REARCHITECTURE_PLAN.md) for complete configuration reference.

## Architecture Overview

HTBase uses a modular architecture:

```
┌─────────────────────────────────────────────────┐
│              FastAPI Server                     │
│  ┌─────────┐  ┌────────┐  ┌────────────────┐   │
│  │  Saves  │  │ Tasks  │  │  Admin         │   │
│  │   API   │  │  API   │  │   API          │   │
│  └────┬────┘  └───┬────┘  └────┬───────────┘   │
│       │           │            │               │
│  ┌────▼───────────▼────────────▼──────────┐    │
│  │         Archiver Factory               │    │
│  │  ┌──────────┐ ┌──────────┐ ┌────────┐  │    │
│  │  │Readability│ │ Monolith │ │  PDF   │  │    │
│  │  └──────────┘ └──────────┘ └────────┘  │    │
│  └────────────────┬──────────────────────┘    │
│                   │                           │
│  ┌────────────────▼──────────────────────┐    │
│  │      Storage Layer                    │    │
│  │  ┌──────────┐  ┌─────────────────┐    │    │
│  │  │   GCS    │  │   PostgreSQL    │    │    │
│  │  └──────────┘  └─────────────────┘    │    │
│  └───────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

See [Rearchitecture Plan](REARCHITECTURE_PLAN.md) for detailed architecture documentation.

## Agent Integration Examples

### Python

```python
import requests

def archive_url(url, item_id):
    response = requests.post(
        "http://localhost:8000/api/save/readability",
        json={"url": url, "id": item_id}
    )
    return response.json()

result = archive_url("https://example.com", "article-123")
```

### JavaScript

```javascript
async function archiveUrl(url, itemId) {
  const response = await fetch('http://localhost:8000/api/save/readability', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, id: itemId })
  });
  return response.json();
}
```

See [Code Examples](../examples/) for complete implementations.

## FAQ

### Q: Which archiver should I use?
**A:** For AI/LLM work, use `readability`. For preservation, use `singlefile-cli`.

### Q: How do I avoid re-archiving URLs?
**A:** Set `SKIP_EXISTING_SAVES=true` and use consistent IDs.

### Q: Can I use HTBase in production without authentication?
**A:** No, implement authentication first. See [Issue #002](../.claude/todos/002-pending-p0-authentication-system-missing.md).

### Q: What's the best way to handle errors?
**A:** Implement retry with exponential backoff. See [Error Handling Example](../examples/python/error_handling.py).

### Q: How do I scale HTBase?
**A:** See [Rearchitecture Plan](REARCHITECTURE_PLAN.md) for microservices architecture.

## Support

- **Documentation Issues:** Open an issue on GitHub
- **Bug Reports:** Use the issue tracker
- **Feature Requests:** Submit via GitHub issues
- **Security Issues:** Email security@example.com

## Contributing

Contributions welcome! Please:

1. Read [CONTRIBUTING.md](../CONTRIBUTING.md) (if exists)
2. Open an issue to discuss changes
3. Submit a pull request
4. Ensure tests pass

## License

[License information here]

---

**Ready to get started?** → [API Quickstart](API_QUICKSTART.md)
