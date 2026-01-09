# Testing Guide for Transaction Boundary Fixes

## Quick Start

### 1. Apply Database Migration

```bash
# Navigate to project root
cd /path/to/hbase

# Check current migration status
alembic current

# Show migration details
alembic show 0006_add_task_tracking_columns

# Apply migration
alembic upgrade head

# Verify columns added
psql -U postgres -d htbase -c "\d archive_artifact"
```

Expected output should include:
```
task_started_at | timestamp without time zone |
last_heartbeat  | timestamp without time zone |
```

### 2. Run Tests

```bash
# Install test dependencies (if not already installed)
pip install pytest pytest-mock

# Run transaction boundary tests
pytest tests/unit/test_archive_transactions.py -v

# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/test_archive_transactions.py --cov=services.archive-worker.app.tasks --cov-report=html
```

### 3. Manual Testing (Optional)

#### Test Normal Archive Flow

```python
# Start archive worker
celery -A shared.celery_config worker -Q archive.singlefile -l info

# Trigger archive task (from another terminal)
from services.archive_worker.app.tasks import archive_singlefile
from celery import group

# Mock self parameter
class MockRequest:
    id = "test-123"

class MockSelf:
    request = MockRequest()

# Execute task
result = archive_singlefile(
    MockSelf(),
    item_id="test-item",
    url="https://example.com",
    archived_url_id=1,
    artifact_id=1,
)

print(result)
```

#### Test Zombie Cleanup

```bash
# 1. Create a zombie task in database
psql -U postgres -d htbase << EOF
UPDATE archive_artifact
SET status = 'in_progress',
    updated_at = NOW() - INTERVAL '2 hours',
    task_started_at = NOW() - INTERVAL '2 hours'
WHERE id = <artifact_id>;
EOF

# 2. Run cleanup task manually
python -c "
from services.archive_worker.app.tasks import cleanup_zombie_tasks
result = cleanup_zombie_tasks()
print(result)
"

# 3. Verify artifact marked as failed
psql -U postgres -d htbase -c "
SELECT id, status, success, updated_at
FROM archive_artifact
WHERE id = <artifact_id>;
"
```

#### Test Worker Crash Scenario

```python
# Add crash simulation to archiver
# In services/archive-worker/app/archivers/<archiver>.py

def archive_with_storage(self, url: str, item_id: str):
    import time
    time.sleep(2)  # Simulate work
    raise RuntimeError("Simulated worker crash!")  # Crash!

# Execute task and observe behavior:
# - Transaction should rollback
# - Artifact should remain in 'pending' state
# - No partial updates committed
```

## Test Scenarios

### Scenario 1: Successful Archive

**Expected behavior:**
1. Artifact status: pending → in_progress → success
2. All changes committed atomically
3. `task_started_at` and `last_heartbeat` set
4. File created and metadata updated

**Verification:**
```sql
SELECT id, status, success, task_started_at, last_heartbeat, saved_path
FROM archive_artifact
WHERE id = <artifact_id>;
```

### Scenario 2: Archive Failure

**Expected behavior:**
1. Archiver returns failure
2. Artifact status: pending → in_progress → failed
3. All changes committed atomically
4. No file created

**Verification:**
```sql
SELECT id, status, success, exit_code
FROM archive_artifact
WHERE id = <artifact_id>;
```

### Scenario 3: Worker Crash

**Expected behavior:**
1. Artifact status update to in_progress
2. Worker crashes (SIGKILL, exception, OOM)
3. Transaction rolls back
4. Artifact remains in 'pending' state
5. Celery retries task

**Simulation:**
```bash
# Kill worker during archiving
ps aux | grep "celery.*archive"
kill -9 <pid>
```

**Verification:**
```sql
-- Should be pending, not in_progress
SELECT id, status, success, task_started_at
FROM archive_artifact
WHERE id = <artifact_id>;
```

### Scenario 4: Zombie Detection

**Expected behavior:**
1. Task stuck in in_progress for > 1 hour
2. Zombie cleanup runs (every 15 minutes)
3. Task marked as failed
4. Warning logged

**Setup:**
```sql
-- Create zombie
UPDATE archive_artifact
SET status = 'in_progress',
    updated_at = NOW() - INTERVAL '2 hours'
WHERE id = <artifact_id>;
```

**Run cleanup:**
```python
from services.archive_worker.app.tasks import cleanup_zombie_tasks
result = cleanup_zombie_tasks()
print(f"Found {result['zombies_found']} zombies")
```

**Verify:**
```sql
SELECT id, status, success FROM archive_artifact WHERE id = <artifact_id>;
-- Should be 'failed', false
```

### Scenario 5: Concurrent Execution

**Expected behavior:**
1. Two workers try to process same artifact
2. First acquires row lock
3. Second waits for lock release
4. Serialized execution (no race condition)

**Simulation:**
```python
import threading
from services.archive_worker.app.tasks import archive_singlefile

def execute_task():
    # Both threads try same artifact
    result = archive_singlefile(
        mock_self,
        item_id="test",
        url="https://example.com",
        archived_url_id=1,
        artifact_id=1,  # Same ID!
    )

thread1 = threading.Thread(target=execute_task)
thread2 = threading.Thread(target=execute_task)

thread1.start()
thread2.start()
thread1.join()
thread2.join()
```

**Expected:** One succeeds, one waits or errors (not both running concurrently)

## Monitoring During Testing

### Watch Celery Logs

```bash
# Archive worker logs
tail -f logs/celery-archive-worker.log

# Look for:
# - "Starting <archiver> archive"
# - "archive completed"
# - Transaction errors
# - Lock timeouts
```

### Watch Beat Scheduler Logs

```bash
# Beat scheduler logs
tail -f logs/celery-beat.log

# Look for zombie cleanup every 15 minutes:
# - "Starting zombie task cleanup"
# - "Found N zombie tasks"
# - "Zombie task cleanup completed"
```

### Monitor Database

```sql
-- Active transactions
SELECT * FROM pg_stat_activity
WHERE query LIKE '%archive_artifact%'
AND state = 'active';

-- Long-running transactions (> 1 minute)
SELECT pid, now() - xact_start AS duration, query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
AND now() - xact_start > interval '1 minute';

-- Current in_progress tasks
SELECT id, archiver, task_started_at,
       NOW() - updated_at AS duration
FROM archive_artifact
WHERE status = 'in_progress'
ORDER BY updated_at;
```

## Test Coverage Report

After running tests with coverage:

```bash
pytest tests/unit/test_archive_transactions.py --cov=services.archive-worker.app.tasks --cov-report=html

# Open report
open htmlcov/index.html
```

**Expected coverage:**
- `_execute_archive_task()`: 100%
- `cleanup_zombie_tasks()`: 100%
- All archive tasks: 100%

## Common Issues

### Issue: "No module named 'celery'"

**Solution:** Activate virtual environment
```bash
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
```

### Issue: "Artifact not found"

**Solution:** Create test artifact first
```sql
INSERT INTO archived_urls (url, item_id)
VALUES ('https://example.com/test', 'test-item')
RETURNING id;

INSERT INTO archive_artifact (archived_url_id, archiver, status)
VALUES (<archived_url_id>, 'singlefile', 'pending')
RETURNING id;
```

### Issue: "Lock timeout"

**Solution:** Increase lock timeout or check for deadlocks
```sql
-- Set lock timeout
SET lock_timeout = '10s';

-- Check for locks
SELECT * FROM pg_locks WHERE NOT granted;
```

### Issue: "Migration already applied"

**Solution:** Check migration status
```bash
alembic current
alembic history
```

## Performance Testing

### Test Transaction Duration

```python
import time
from services.archive_worker.app.tasks import archive_singlefile

start = time.time()
result = archive_singlefile(mock_self, ...)
duration = time.time() - start

print(f"Transaction duration: {duration:.2f}s")
# Should be < 60 seconds for most archivers
```

### Test Zombie Cleanup Performance

```python
# Create 100 zombie tasks
for i in range(100):
    # Insert zombies...

# Time cleanup
import time
start = time.time()
result = cleanup_zombie_tasks()
duration = time.time() - start

print(f"Cleaned {result['zombies_found']} zombies in {duration:.2f}s")
# Should be < 1 second with partial index
```

## Integration Testing

### Full End-to-End Test

```bash
# 1. Start all services
docker-compose up -d postgres redis

# 2. Apply migrations
alembic upgrade head

# 3. Start workers
celery -A shared.celery_config worker -Q archive.singlefile,archive.monolith -l info &
celery -A shared.celery_config beat -l info &

# 4. Submit archive task via API
curl -X POST http://localhost:8000/api/archive \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "archivers": ["singlefile"]}'

# 5. Monitor progress
watch -n 1 "psql -U postgres -d htbase -c 'SELECT id, status, updated_at FROM archive_artifact ORDER BY id DESC LIMIT 5'"

# 6. Verify success
psql -U postgres -d htbase -c "SELECT * FROM archive_artifact WHERE id = <artifact_id>;"
```

## Cleanup

```bash
# Stop workers
pkill -f "celery.*worker"
pkill -f "celery.*beat"

# Clean test data
psql -U postgres -d htbase << EOF
DELETE FROM archive_artifact WHERE archived_url_id IN (
  SELECT id FROM archived_urls WHERE item_id LIKE 'test-%'
);
DELETE FROM archived_urls WHERE item_id LIKE 'test-%';
EOF
```

## Checklist

Before considering testing complete:

- [ ] Database migration applied successfully
- [ ] All unit tests passing
- [ ] Successful archive test completed
- [ ] Failed archive test completed
- [ ] Worker crash rollback verified
- [ ] Zombie cleanup tested
- [ ] Concurrent execution tested
- [ ] All 5 archiver tasks tested
- [ ] Celery Beat running cleanup every 15 minutes
- [ ] Monitoring queries working
- [ ] Documentation reviewed

## Next Steps

1. ✅ Run all tests
2. ✅ Verify migration applied
3. ⏳ Deploy to staging
4. ⏳ Monitor for 24 hours
5. ⏳ Check for zombie tasks
6. ⏳ Deploy to production
