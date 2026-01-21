# Archive Task Failures Runbook

## Alert: HTBaseLowArchiveSuccessRate / HTBaseVeryLowArchiveSuccessRate

### Symptoms
- Archive tasks failing at elevated rate
- Alert fires when success rate < 80% (warning) or < 50% (critical)
- Users may see failed archive statuses in their items

### Impact
- Users not receiving complete archives
- Retries consuming worker capacity
- Potential data loss if not addressed

### Quick Diagnosis

1. **Identify which archiver is failing:**
   ```promql
   # In Grafana/Prometheus
   sum(rate(htbase_archive_tasks_total{status="failed"}[10m])) by (archiver)
   ```

2. **Check worker logs for specific archiver:**
   ```bash
   # Replace ARCHIVER with: singlefile, monolith, readability, pdf, screenshot
   docker compose logs archive-worker-ARCHIVER --tail=100 | grep -i error
   ```

3. **Check Sentry** for grouped exceptions and stack traces

### Per-Archiver Debugging

#### SingleFile Archiver Failures

**Common causes:**
- Browser crashes (Chrome/Puppeteer issues)
- Page timeouts (slow websites)
- JavaScript rendering failures

**Resolution:**
```bash
# Check shared memory allocation
docker compose exec archive-worker-singlefile df -h /dev/shm

# If OOM, increase shm_size in docker-compose.yml
# Current: shm_size: 2gb

# Check for zombie Chrome processes
docker compose exec archive-worker-singlefile ps aux | grep chrome
docker compose restart archive-worker-singlefile
```

#### Monolith Archiver Failures

**Common causes:**
- Network timeouts
- SSL certificate issues
- Resource download failures

**Resolution:**
```bash
# Test URL directly
docker compose exec archive-worker-monolith curl -I https://example.com

# Check monolith binary
docker compose exec archive-worker-monolith which monolith
docker compose exec archive-worker-monolith monolith --version
```

#### Readability Archiver Failures

**Common causes:**
- Non-article content (homepage, video pages)
- Malformed HTML
- Content extraction failures

**Note:** Readability failures are often expected for non-article content. Focus on success rate trends rather than individual failures.

#### PDF Archiver Failures

**Common causes:**
- Chrome/Puppeteer crashes
- Page rendering issues
- Memory exhaustion

**Resolution:**
```bash
# Similar to SingleFile - check shared memory
docker compose exec archive-worker-pdf df -h /dev/shm
docker compose restart archive-worker-pdf
```

#### Screenshot Archiver Failures

**Common causes:**
- Viewport issues
- Page load timeouts
- Browser crashes

**Resolution:**
```bash
# Check worker health
docker compose exec archive-worker-screenshot curl localhost:8080/health
docker compose restart archive-worker-screenshot
```

### GCS Upload Failures

**Symptoms:** Tasks complete but GCS upload fails

**Resolution:**
```bash
# Check GCS credentials
docker compose exec archive-worker-singlefile python -c "
from google.cloud import storage
client = storage.Client()
print(list(client.list_buckets()))
"

# Check bucket permissions
gsutil iam get gs://YOUR_BUCKET

# Check bucket exists and is accessible
gsutil ls gs://YOUR_BUCKET/
```

### Timeout Errors

**Symptoms:** Logs show "Command timed out" or "Task time limit exceeded"

**Resolution:**
1. Check current timeout settings in `docker-compose.yml`
2. Increase timeouts if needed:
   ```yaml
   environment:
     ARCHIVER_TIMEOUT: 600  # 10 minutes
   ```
3. Consider if the URLs being archived are unusually slow

### Scaling Workers

If failures are due to resource constraints:

```bash
# Scale specific archiver
docker compose up -d --scale archive-worker-singlefile=3

# Monitor queue depth after scaling
watch -n 5 'docker compose exec redis redis-cli llen archive.singlefile'
```

### Restart Procedure

```bash
# Graceful restart (allows current tasks to complete)
docker compose stop archive-worker-singlefile
docker compose start archive-worker-singlefile

# Force restart (kills running tasks)
docker compose restart archive-worker-singlefile
```

---

## Alert: HTBaseSlowArchiveTasks

### Symptoms
- P95 task duration > 5 minutes
- Queue buildup due to slow processing

### Diagnosis

1. **Identify slow tasks:**
   ```promql
   histogram_quantile(0.95, rate(htbase_archive_task_duration_seconds_bucket[10m])) by (archiver)
   ```

2. **Check for problematic URLs:**
   - Review recent tasks in logs
   - Look for patterns (specific domains, large pages)

### Remediation

1. Increase worker timeout if legitimate slow pages
2. Add slow domains to a skiplist if consistently problematic
3. Scale workers to handle increased processing time

---

## Alert: HTBaseNoArchiveTasksProcessed

### Symptoms
- Workers appear stopped
- Queue has tasks but none being processed

### Diagnosis

```bash
# Check if workers are running
docker compose ps | grep archive-worker

# Check Celery worker status
docker compose exec archive-worker-singlefile celery -A shared.infrastructure.celery inspect active

# Check for worker errors
docker compose logs archive-worker-singlefile --tail=50
```

### Remediation

1. **If workers are crashed:**
   ```bash
   docker compose restart archive-worker-singlefile
   ```

2. **If workers are stuck:**
   ```bash
   # Kill and restart
   docker compose kill archive-worker-singlefile
   docker compose up -d archive-worker-singlefile
   ```

3. **If Redis is the issue:**
   ```bash
   docker compose restart redis
   # Workers will reconnect automatically
   ```
