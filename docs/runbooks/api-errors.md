# API Gateway Errors Runbook

## Alert: HTBaseHighErrorRate

### Symptoms
- API Gateway returning 5xx errors
- Alert fires when error rate > 5% for 5 minutes
- Users may see "Internal Server Error" responses

### Impact
- Users unable to submit archive requests
- Existing archive tasks continue processing (workers unaffected)
- Webhooks may not be delivered if tasks can't be dispatched

### Quick Diagnosis

1. **Check API Gateway logs:**
   ```bash
   # If using Docker Compose
   docker compose logs api-gateway --tail=100 | grep -i error

   # If using kubectl
   kubectl logs -l app=api-gateway --tail=100 | grep -i error
   ```

2. **Check Sentry dashboard** for error groupings and stack traces

3. **Check recent deployments:**
   ```bash
   git log --oneline -10
   # Check if error timing correlates with a deployment
   ```

### Common Causes & Remediation

#### 1. Redis Connection Failures
**Symptoms:** Logs show `ConnectionRefusedError` or `redis.exceptions.ConnectionError`

**Resolution:**
```bash
# Check Redis health
docker compose exec redis redis-cli ping

# Check Redis memory
docker compose exec redis redis-cli info memory

# If OOM, increase memory limit or clear old data
docker compose exec redis redis-cli FLUSHDB
```

#### 2. Firestore Connection Issues
**Symptoms:** Logs show `google.api_core.exceptions.ServiceUnavailable`

**Resolution:**
- Check GCP status page: https://status.cloud.google.com/
- Verify service account credentials are valid
- Check if Firestore quotas are exceeded in GCP Console

#### 3. Celery Task Dispatch Failures
**Symptoms:** Logs show "Failed to dispatch Celery tasks"

**Resolution:**
```bash
# Check Celery broker connection
docker compose exec api-gateway python -c "from shared.infrastructure.celery import celery_app; celery_app.control.ping()"

# Restart API Gateway
docker compose restart api-gateway
```

#### 4. Memory Exhaustion
**Symptoms:** Container OOMKilled or very high memory usage

**Resolution:**
```bash
# Check container stats
docker stats api-gateway

# If memory is high, restart
docker compose restart api-gateway

# Consider increasing memory limits in docker-compose.yml
```

### Rollback Procedure

If the error correlates with a recent deployment:

```bash
# Roll back to previous version
docker compose pull htbase/api-gateway:previous-tag
docker compose up -d api-gateway

# Or if using Git-based deployments
git revert HEAD
git push origin main
```

### Escalation

If the issue persists after 15 minutes of investigation:
1. Check #htbase-alerts Slack channel for related issues
2. Page on-call engineer via PagerDuty
3. Document findings in incident channel

---

## Alert: HTBaseHighLatencyP95 / HTBaseVeryHighLatencyP99

### Symptoms
- API requests taking longer than expected
- P95 latency > 2s or P99 latency > 5s

### Quick Diagnosis

1. **Identify slow endpoints:**
   ```promql
   # In Grafana/Prometheus
   histogram_quantile(0.95, sum(rate(htbase_http_request_duration_seconds_bucket[5m])) by (endpoint, le))
   ```

2. **Check downstream services:**
   - Redis latency
   - Firestore latency
   - GCS latency

### Common Causes

1. **High load** - Check if request volume has spiked
2. **Slow Firestore queries** - Check if index is missing
3. **Network issues** - Check container network connectivity
4. **Resource contention** - Check CPU/memory pressure

### Remediation

1. Scale API Gateway horizontally:
   ```bash
   docker compose up -d --scale api-gateway=3
   ```

2. Check for slow queries in application logs

3. Verify network connectivity between services

---

## Alert: HTBaseNoTraffic

### Symptoms
- No requests reaching API Gateway
- May indicate routing or load balancer issue

### Quick Diagnosis

1. **Check if service is running:**
   ```bash
   docker compose ps api-gateway
   curl -f http://localhost:8080/health
   ```

2. **Check Traefik/load balancer:**
   ```bash
   # Check Traefik logs
   docker compose logs traefik --tail=50

   # Verify routing rules
   curl -H "Host: your-domain.com" http://localhost/health
   ```

3. **Check DNS resolution:**
   ```bash
   dig your-domain.com
   ```

### Remediation

1. If service is down, restart:
   ```bash
   docker compose restart api-gateway
   ```

2. If routing is broken, check Traefik configuration

3. If DNS is wrong, update DNS records
