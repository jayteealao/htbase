# Queue Backlog Runbook

## Alert: HTBaseHighQueueDepth / HTBaseVeryHighQueueDepth

### Symptoms
- Queue depth > 100 (warning) or > 500 (critical)
- Tasks taking longer to start
- Users experiencing delays in archive completion

### Impact
- Increased latency for archive requests
- Potential task timeouts if backlog persists
- Memory pressure on Redis if queue grows too large

### Quick Diagnosis

1. **Check queue depths for all queues:**
   ```bash
   docker compose exec redis redis-cli EVAL "
     local queues = {'archive.singlefile', 'archive.monolith', 'archive.readability', 'archive.pdf', 'archive.screenshot', 'summarization'}
     local result = {}
     for _, q in ipairs(queues) do
       local len = redis.call('LLEN', q)
       table.insert(result, q .. ': ' .. len)
     end
     return result
   " 0
   ```

2. **Check worker status:**
   ```bash
   docker compose ps | grep -E "(archive|summarization)-worker"
   ```

3. **Check if workers are processing:**
   ```bash
   docker compose logs --tail=20 archive-worker-singlefile | grep "Task"
   ```

### Identify Bottlenecks

1. **Is it a specific queue?**
   ```promql
   # In Grafana/Prometheus
   htbase_celery_queue_depth
   ```

2. **Is traffic higher than normal?**
   ```promql
   sum(rate(htbase_http_requests_total{endpoint=~".*archives.*"}[5m]))
   ```

3. **Are workers slower than normal?**
   ```promql
   histogram_quantile(0.95, rate(htbase_archive_task_duration_seconds_bucket[10m]))
   ```

### Remediation Options

#### Option 1: Scale Workers (Preferred)

```bash
# Scale the specific queue's workers
# Example: If archive.singlefile has high backlog
docker compose up -d --scale archive-worker-singlefile=4

# Verify workers are running
docker compose ps | grep singlefile

# Monitor queue depth decreasing
watch -n 5 'docker compose exec redis redis-cli llen archive.singlefile'
```

#### Option 2: Increase Worker Concurrency

Edit `docker-compose.yml` to increase concurrency for the affected worker:

```yaml
archive-worker-singlefile:
  environment:
    WORKER_CONCURRENCY: ${SINGLEFILE_CONCURRENCY:-4}  # Increase from 2
```

Then restart:
```bash
docker compose up -d archive-worker-singlefile
```

#### Option 3: Temporarily Pause New Tasks

If the system is overwhelmed, temporarily pause accepting new requests:

1. Scale down API gateway to limit incoming traffic
2. Let workers drain the queue
3. Scale API gateway back up

```bash
# Reduce API gateway instances
docker compose up -d --scale api-gateway=1

# Wait for queues to drain
watch -n 10 'docker compose exec redis redis-cli llen archive.singlefile'

# Scale back up
docker compose up -d --scale api-gateway=3
```

### Draining Queues Safely

If you need to clear a queue (data loss!):

```bash
# WARNING: This discards all pending tasks
# Only use if you need to recover from a catastrophic backlog

# Clear specific queue
docker compose exec redis redis-cli DEL archive.singlefile

# Clear all archive queues
docker compose exec redis redis-cli EVAL "
  local queues = {'archive.singlefile', 'archive.monolith', 'archive.readability', 'archive.pdf', 'archive.screenshot'}
  for _, q in ipairs(queues) do
    redis.call('DEL', q)
  end
  return 'Cleared'
" 0
```

### Preventing Future Backlogs

1. **Set up rate limiting** at the API gateway level
2. **Monitor queue depth trends** in Grafana dashboards
3. **Set up autoscaling** if using Kubernetes
4. **Review capacity planning** based on peak load patterns

### Capacity Planning

| Queue | Tasks/Hour | Workers Needed | Memory/Worker |
|-------|------------|----------------|---------------|
| archive.singlefile | 100 | 2-4 | 4GB |
| archive.monolith | 200 | 2-3 | 4GB |
| archive.readability | 500 | 3-5 | 2GB |
| archive.pdf | 200 | 2-3 | 2GB |
| archive.screenshot | 200 | 2-3 | 2GB |

Adjust based on actual throughput requirements.

---

## Queue Health Monitoring

### Redis Memory Usage

If Redis memory is high due to large queues:

```bash
# Check memory usage
docker compose exec redis redis-cli info memory

# If using too much memory, the queue is too large
# Either scale workers or drain queues
```

### Task Visibility

To inspect pending tasks:

```bash
# View first 10 tasks in queue (without removing)
docker compose exec redis redis-cli LRANGE archive.singlefile 0 9
```

### Flower Dashboard

Use the Flower dashboard for visual queue monitoring:
- URL: `https://your-domain.com/flower`
- Shows real-time queue depths
- Shows worker status and active tasks

---

## Escalation

If queue backlog persists after scaling:

1. Check if there's an unusual traffic pattern (DDoS, batch import)
2. Check if workers are actually processing (not stuck)
3. Review recent code changes that might affect processing speed
4. Consider temporarily rejecting new requests if system is overwhelmed
