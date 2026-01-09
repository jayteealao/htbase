# HTBase Examples

This directory contains code examples demonstrating how to use HTBase in various programming languages.

## Directory Structure

```
examples/
├── python/           # Python examples
├── javascript/       # JavaScript/Node.js examples
├── curl/             # Curl command examples
└── README.md         # This file
```

## Available Examples

### Python Examples

- **simple_archive.py** - Archive a single URL
- **batch_archive.py** - Archive multiple URLs efficiently
- **error_handling.py** - Robust error handling with retry and fallback
- **rss_archiver.py** - Archive all articles from RSS feeds

**Requirements:**
```bash
pip install requests feedparser
```

**Usage:**
```bash
cd python
python simple_archive.py
python batch_archive.py
python error_handling.py
python rss_archiver.py
```

### JavaScript Examples

- **simple_archive.js** - Archive a single URL
- **batch_archive.js** - Archive multiple URLs with task polling

**Requirements:**
```bash
npm install node-fetch
```

**Usage:**
```bash
cd javascript
node simple_archive.js
node batch_archive.js
```

### Curl Examples

- **basic_examples.sh** - Basic archiving operations
- **batch_examples.sh** - Batch operations and task polling
- **advanced_examples.sh** - Advanced features (PDF, screenshots, summaries)

**Requirements:**
- `curl` (usually pre-installed)
- `jq` (optional, for JSON formatting)

**Usage:**
```bash
cd curl
bash basic_examples.sh
bash batch_examples.sh
bash advanced_examples.sh
```

## Quick Start

### 1. Start HTBase Server

```bash
docker compose up -d
```

### 2. Run an Example

**Python:**
```bash
cd examples/python
python simple_archive.py
```

**JavaScript:**
```bash
cd examples/javascript
npm install node-fetch
node simple_archive.js
```

**Curl:**
```bash
cd examples/curl
bash basic_examples.sh
```

## Common Patterns

### Archive a URL

**Python:**
```python
import requests

response = requests.post(
    "http://localhost:8000/api/save/readability",
    json={"url": "https://example.com", "id": "my-article"}
)
result = response.json()
```

**JavaScript:**
```javascript
const fetch = require('node-fetch');

const response = await fetch('http://localhost:8000/api/save/readability', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ url: 'https://example.com', id: 'my-article' })
});
const result = await response.json();
```

**Curl:**
```bash
curl -X POST http://localhost:8000/api/save/readability \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com", "id": "my-article"}'
```

### Batch Archive

**Python:**
```python
response = requests.post(
    "http://localhost:8000/api/batch/readability",
    json={
        "items": [
            {"url": "https://example.com/1", "id": "article-1"},
            {"url": "https://example.com/2", "id": "article-2"}
        ]
    }
)
task_id = response.json()["task_id"]
```

### Check Task Status

**Python:**
```python
response = requests.get(f"http://localhost:8000/api/tasks/{task_id}")
status = response.json()
```

**JavaScript:**
```javascript
const response = await fetch(`http://localhost:8000/api/tasks/${taskId}`);
const status = await response.json();
```

**Curl:**
```bash
curl http://localhost:8000/api/tasks/{task_id}
```

### Retrieve Archive

**Python:**
```python
response = requests.get(
    "http://localhost:8000/api/retrieve",
    params={"id": "my-article", "archiver": "readability"}
)
with open("output.html", "wb") as f:
    f.write(response.content)
```

**Curl:**
```bash
curl "http://localhost:8000/api/retrieve?id=my-article&archiver=readability" \
  --output output.html
```

## Available Archivers

- `readability` - Clean text extraction (fast, great for AI/LLM)
- `monolith` - Single HTML file with embedded assets
- `singlefile-cli` - High-fidelity single file archive
- `pdf` - PDF rendering
- `screenshot` - PNG screenshot
- `all` - All archivers

## Error Handling

All examples include basic error handling. For production use, implement:

1. **Retry logic** with exponential backoff
2. **Fallback archivers** if primary fails
3. **Timeout handling** for long-running operations
4. **Rate limiting** to respect API quotas

See `python/error_handling.py` for a complete example.

## Configuration

All examples use default settings:

```
BASE_URL = "http://localhost:8000"
```

To use a different server:

**Python:**
```python
BASE_URL = "https://htbase.example.com"
```

**JavaScript:**
```javascript
const BASE_URL = 'https://htbase.example.com';
```

**Bash:**
```bash
BASE_URL="https://htbase.example.com"
```

## Authentication

When authentication is implemented, add API key to requests:

**Python:**
```python
headers = {"Authorization": f"Bearer {API_KEY}"}
response = requests.post(url, json=data, headers=headers)
```

**JavaScript:**
```javascript
const headers = { 'Authorization': `Bearer ${API_KEY}` };
```

**Curl:**
```bash
curl -H "Authorization: Bearer $API_KEY" ...
```

See [docs/AUTHENTICATION.md](../docs/AUTHENTICATION.md) for details.

## Resources

- [API Quickstart](../docs/API_QUICKSTART.md) - 5-minute getting started guide
- [Error Codes Reference](../docs/ERROR_CODES.md) - Complete error documentation
- [Agent Best Practices](../docs/AGENT_GUIDE.md) - Patterns for AI agents
- [Architecture Docs](../docs/REARCHITECTURE_PLAN.md) - Technical details

## Contributing

Have a useful example? Submit a pull request!

Guidelines:
- Include comments explaining the code
- Add error handling
- Keep examples focused and simple
- Test before submitting

## Questions?

Open an issue on GitHub or refer to the [documentation](../docs/).
