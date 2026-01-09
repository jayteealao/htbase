# Archive Worker Tasks

This directory contains Celery tasks for the archive worker service.

## Tasks

### webhooks.py

Webhook notification tasks for async completion callbacks.

#### `notify_webhook(workflow_id, webhook_url, webhook_secret, status_data, event_type)`

Sends webhook notification when task completes.

- **Retry Logic:** 5 retries with exponential backoff (max 10 minutes)
- **Timeout:** 10 seconds per request
- **Signature:** HMAC-SHA256 with webhook_secret
- **Retries On:** 5xx errors, timeouts, network errors
- **No Retry On:** 4xx client errors

**Headers:**
- `Content-Type: application/json`
- `X-HTBase-Signature: sha256=<hex>` (if secret provided)
- `X-HTBase-Event: <event_type>`
- `User-Agent: HTBase-Webhook/1.0`

#### `gather_status(previous_results, task_id)`

Gathers workflow status from database for webhook payload.

Queries all artifacts for a given workflow/task ID and builds a status summary including:
- Overall status (completed, failed, partial, unknown)
- Individual item statuses
- Exit codes and saved paths

## Usage

These tasks are automatically chained to save endpoints when `webhook_url` is provided:

```python
# In saves.py
if request.webhook_url:
    workflow = chain(
        task_group,
        celery_app.signature(
            "services.archive_worker.tasks.gather_status",
            kwargs={"task_id": workflow_id},
        ),
        celery_app.signature(
            "services.archive_worker.tasks.notify_webhook",
            kwargs={
                "workflow_id": workflow_id,
                "webhook_url": str(request.webhook_url),
                "webhook_secret": request.webhook_secret,
                "event_type": "task.completed",
            },
        ),
    )
```

## Security

- **HMAC-SHA256 Signatures:** All webhooks include signatures when `webhook_secret` is provided
- **No Redirect Following:** Webhooks won't follow redirects for security
- **Constant-Time Comparison:** Use `hmac.compare_digest()` for signature verification
- **HTTPS Only:** Always use HTTPS URLs for webhooks in production

## Testing

See `tests/unit/test_webhooks.py` for unit tests including:
- Signature generation and verification
- Status gathering logic
- Retry behavior
- Payload format validation

## Error Handling

- **4xx Errors:** Logged and not retried (permanent errors)
- **5xx Errors:** Retried with exponential backoff (transient errors)
- **Timeouts:** Retried (network issues)
- **Connection Errors:** Retried (network issues)

## Monitoring

Monitor webhook delivery in logs:
- `"Sending webhook notification"` - Webhook delivery started
- `"Webhook delivered successfully"` - Delivery succeeded
- `"Webhook endpoint returned {status_code}, retrying"` - Transient error
- `"Webhook rejected by endpoint: {status_code}"` - Permanent error
- `"Webhook delivery failed after all retries"` - Final failure

## Related Documentation

- [Webhook Guide](../../../../docs/WEBHOOK_GUIDE.md) - Full webhook documentation
- [Webhook Quick Start](../../../../docs/WEBHOOK_QUICK_START.md) - Get started quickly
- [Celery Config](../../../../shared/celery_config.py) - Task routing configuration
