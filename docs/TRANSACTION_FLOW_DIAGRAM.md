# Archive Worker Transaction Flow Diagrams

## Before Fix (Broken Pattern)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Archive Task Execution (BROKEN)              │
└─────────────────────────────────────────────────────────────────┘

 Time │ Database Transaction │ Worker State         │ Artifact Status
──────┼──────────────────────┼──────────────────────┼─────────────────
      │                      │                      │
  1   │ ┌─ BEGIN TX 1        │ Task starts          │ pending
      │ │  UPDATE status     │                      │
      │ │  = 'in_progress'   │                      │
  2   │ └─ COMMIT TX 1 ✓     │ Status committed     │ in_progress
      │                      │                      │
  3   │                      │ Running archiver...  │ in_progress
      │                      │                      │
  4   │                      │ 💥 WORKER CRASH!     │ in_progress
      │                      │                      │
  5   │                      │ (worker dead)        │ in_progress ← STUCK!
      │                      │                      │
  6   │ ❌ TX 2 NEVER RUNS   │ (never reached)      │ in_progress ← ZOMBIE!
      │                      │                      │

Problems:
❌ Status stuck in 'in_progress' forever
❌ File may or may not exist (inconsistent state)
❌ No automatic recovery
❌ Manual intervention required
```

## After Fix (Correct Pattern)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Archive Task Execution (FIXED)               │
└─────────────────────────────────────────────────────────────────┘

 Time │ Database Transaction │ Worker State         │ Artifact Status
──────┼──────────────────────┼──────────────────────┼─────────────────
      │                      │                      │
  1   │ ┌─ BEGIN TX          │ Task starts          │ pending
      │ │  SELECT FOR UPDATE │ Acquire row lock 🔒  │
      │ │                    │                      │
  2   │ │  UPDATE status     │ Status updated       │ (uncommitted)
      │ │  = 'in_progress'   │ (in transaction)     │ in_progress
      │ │  FLUSH             │                      │ (not visible)
      │ │                    │                      │
  3   │ │ (still in TX)      │ Running archiver...  │ (uncommitted)
      │ │                    │                      │ in_progress
      │ │                    │                      │ (not visible)
  4   │ │ (still in TX)      │ 💥 WORKER CRASH!     │ (uncommitted)
      │ │                    │                      │
  5   │ └─ ROLLBACK ⏪       │ (worker dead)        │ pending ✓
      │    (automatic)       │                      │ (never changed!)
      │                      │                      │
  6   │                      │ Celery retries task  │ pending
      │                      │                      │

Benefits:
✅ Automatic rollback on crash
✅ Artifact returns to 'pending' for retry
✅ No zombie tasks from crash
✅ Atomic execution
```

## Successful Archive Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│              Successful Archive (Single Transaction)                     │
└─────────────────────────────────────────────────────────────────────────┘

 Step │ Action                          │ Database State
──────┼─────────────────────────────────┼───────────────────────────────────
      │                                 │
  1   │ BEGIN TRANSACTION               │ Transaction started
      │                                 │ Isolation level: READ COMMITTED
      │                                 │
  2   │ SELECT ... FOR UPDATE           │ Row locked 🔒
      │ WHERE id = artifact_id          │ Other transactions wait
      │                                 │
  3   │ UPDATE artifact                 │ Status: pending → in_progress
      │   SET status = 'in_progress'    │ task_started_at = NOW()
      │       task_started_at = NOW()   │ last_heartbeat = NOW()
      │       last_heartbeat = NOW()    │ (NOT COMMITTED - in transaction)
      │                                 │
  4   │ FLUSH                           │ Changes visible in current TX
      │                                 │ Still invisible to other sessions
      │                                 │
  5   │ archiver.archive_with_storage() │ External operation
      │                                 │ (creates file on disk)
      │ ⏳ Takes 10-30 seconds          │ Transaction held open
      │                                 │
  6   │ UPDATE artifact                 │ Status: in_progress → success
      │   SET status = 'success'        │ success = true
      │       success = true            │ saved_path = '/path/to/file'
      │       saved_path = '...'        │ size_bytes = 123456
      │       size_bytes = 123456       │ exit_code = 0
      │       exit_code = 0             │ (NOT COMMITTED - in transaction)
      │       updated_at = NOW()        │
      │                                 │
  7   │ COMMIT ✓                        │ All changes committed atomically
      │                                 │ Row lock released 🔓
      │                                 │ Changes visible to all sessions
      │                                 │
  8   │ (context exit)                  │ Status: success ✓
      │                                 │ File exists ✓
      │                                 │ Database updated ✓
```

## Failed Archive Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│              Failed Archive (Archiver Returns Failure)                   │
└─────────────────────────────────────────────────────────────────────────┘

 Step │ Action                          │ Database State
──────┼─────────────────────────────────┼───────────────────────────────────
      │                                 │
  1   │ BEGIN TRANSACTION               │ Transaction started
      │                                 │
  2   │ SELECT ... FOR UPDATE           │ Row locked 🔒
      │                                 │
  3   │ UPDATE status = 'in_progress'   │ Status changed (in transaction)
      │                                 │
  4   │ FLUSH                           │ Changes visible in TX only
      │                                 │
  5   │ archiver.archive_with_storage() │ Archiving...
      │                                 │
  6   │ ❌ Archiver returns failure     │ exit_code = 1
      │    (exit_code = 1)              │ success = false
      │                                 │
  7   │ UPDATE artifact                 │ Status: in_progress → failed
      │   SET status = 'failed'         │ success = false
      │       success = false           │ exit_code = 1
      │       exit_code = 1             │ (NOT COMMITTED - in transaction)
      │       updated_at = NOW()        │
      │                                 │
  8   │ COMMIT ✓                        │ All changes committed atomically
      │                                 │ Row lock released 🔓
      │                                 │
  9   │ (context exit)                  │ Status: failed ✓
      │                                 │ Marked for retry
```

## Worker Crash Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│              Worker Crash (Exception or Kill Signal)                     │
└─────────────────────────────────────────────────────────────────────────┘

 Step │ Action                          │ Database State
──────┼─────────────────────────────────┼───────────────────────────────────
      │                                 │
  1   │ BEGIN TRANSACTION               │ Transaction started
      │                                 │
  2   │ SELECT ... FOR UPDATE           │ Row locked 🔒
      │                                 │
  3   │ UPDATE status = 'in_progress'   │ Status changed (in transaction)
      │                                 │
  4   │ FLUSH                           │ Changes visible in TX only
      │                                 │
  5   │ archiver.archive_with_storage() │ Archiving...
      │                                 │
  6   │ 💥 WORKER CRASH!                │ Exception / SIGKILL / OOM
      │    (RuntimeError / SIGKILL)     │ Connection lost
      │                                 │
  7   │ (no code executed)              │ Connection closed
      │                                 │ Transaction NOT committed
      │                                 │
  8   │ ⏪ AUTOMATIC ROLLBACK            │ Database detects connection loss
      │    (by database)                │ All changes rolled back
      │                                 │ Row lock released 🔓
      │                                 │
  9   │ (worker dead)                   │ Status: pending ✓ (never changed!)
      │                                 │ File may exist but DB unchanged
      │                                 │ Ready for retry
      │                                 │
 10   │ Celery requeues task            │ Task retried by Celery
      │    (acks_late=True)             │ (up to 3 retries)
```

## Concurrent Execution Prevention

```
┌─────────────────────────────────────────────────────────────────────────┐
│              Two Workers Try Same Artifact (Row Locking)                 │
└─────────────────────────────────────────────────────────────────────────┘

 Time │ Worker 1                │ Worker 2                │ Database
──────┼─────────────────────────┼─────────────────────────┼──────────────────
      │                         │                         │
  1   │ BEGIN TX                │                         │ TX1 started
      │                         │                         │
  2   │ SELECT ... FOR UPDATE   │                         │ Row locked 🔒 by TX1
      │ ✓ Lock acquired         │                         │
      │                         │                         │
  3   │ UPDATE status           │ BEGIN TX                │ TX2 started
      │ = 'in_progress'         │                         │
      │                         │                         │
  4   │ Archiving...            │ SELECT ... FOR UPDATE   │ TX2 waits for lock
      │                         │ ⏳ Waiting...           │ (blocked by TX1)
      │                         │                         │
  5   │ Archiving...            │ ⏳ Still waiting...     │ TX2 still blocked
      │                         │                         │
      │                         │                         │
  6   │ UPDATE status           │ ⏳ Still waiting...     │ TX2 still blocked
      │ = 'success'             │                         │
      │                         │                         │
  7   │ COMMIT ✓                │ ⏳ Still waiting...     │ TX1 commits
      │                         │                         │ Lock released 🔓
      │                         │                         │
  8   │ (done)                  │ ✓ Lock acquired         │ TX2 gets lock
      │                         │                         │
  9   │                         │ ❌ Status already       │ TX2 sees 'success'
      │                         │    'success'            │ (Worker 1 finished)
      │                         │                         │
 10   │                         │ ROLLBACK                │ TX2 aborts
      │                         │ (no work to do)         │

Result:
✅ Only Worker 1 processes artifact
✅ Worker 2 prevented from duplicate work
✅ No race condition
✅ Serialized execution
```

## Zombie Task Cleanup Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│              Zombie Task Cleanup (Every 15 Minutes)                      │
└─────────────────────────────────────────────────────────────────────────┘

 Time │ Action                          │ Database State
──────┼─────────────────────────────────┼───────────────────────────────────
      │                                 │
  1   │ Worker crashed 2 hours ago      │ Status: in_progress (stale)
      │ (unhandled crash, no cleanup)   │ updated_at: 2 hours ago
      │                                 │
  2   │ Celery Beat triggers            │ Every 15 minutes
      │ cleanup_zombie_tasks()          │
      │                                 │
  3   │ BEGIN TX                        │ Cleanup transaction started
      │                                 │
  4   │ SELECT * FROM                   │ Query using partial index:
      │   archive_artifact              │   idx_zombie_tasks
      │ WHERE                           │
      │   status = 'in_progress'        │ Efficient lookup (indexed)
      │   AND updated_at < NOW() - 1h   │
      │ FOR UPDATE                      │ Lock zombie rows
      │                                 │
  5   │ Found 1 zombie task             │ Row locked 🔒
      │                                 │
  6   │ UPDATE artifact                 │ Status: in_progress → failed
      │   SET status = 'failed'         │ success = false
      │       success = false           │ (in transaction)
      │       updated_at = NOW()        │
      │                                 │
  7   │ LOG WARNING:                    │ Logged for monitoring
      │   "Zombie task cleaned up"      │
      │   - artifact_id                 │
      │   - archiver                    │
      │   - task_started_at             │
      │                                 │
  8   │ COMMIT ✓                        │ Zombie marked as failed
      │                                 │ Row lock released 🔓
      │                                 │
  9   │ Return statistics:              │ Monitoring metrics
      │   zombies_found = 1             │
      │   zombies_failed = 1            │

Schedule:
⏰ Runs every 15 minutes (Celery Beat)
⏱️  1 hour threshold (configurable)
📊 Metrics logged for monitoring
```

## Transaction Isolation Levels

```
┌─────────────────────────────────────────────────────────────────────────┐
│              PostgreSQL READ COMMITTED Isolation                         │
└─────────────────────────────────────────────────────────────────────────┘

Session 1 (Archive Worker)     │ Session 2 (API Query)
───────────────────────────────┼────────────────────────────────────────
                               │
BEGIN;                         │
                               │
SELECT ... FOR UPDATE;         │
🔒 Row locked                  │
                               │
UPDATE status = 'in_progress'; │ SELECT * FROM archive_artifact
(not committed)                │ WHERE id = 123;
                               │
                               │ → Returns: status = 'pending'
                               │   (sees old committed value)
                               │
Archiving... (30 seconds)      │
                               │ SELECT * FROM archive_artifact
                               │ WHERE id = 123;
                               │
                               │ → Returns: status = 'pending'
                               │   (still sees old value)
                               │
UPDATE status = 'success';     │
(not committed)                │
                               │
COMMIT; ✓                      │
🔓 Lock released               │
                               │ SELECT * FROM archive_artifact
                               │ WHERE id = 123;
                               │
                               │ → Returns: status = 'success'
                               │   (now sees new committed value)

Key Points:
✅ Uncommitted changes invisible to other sessions
✅ Row lock prevents concurrent updates
✅ Atomic visibility - all changes appear together at COMMIT
✅ Other sessions see either old or new state (never partial)
```

## Performance Characteristics

```
┌─────────────────────────────────────────────────────────────────────────┐
│              Transaction Duration and Lock Holding Time                  │
└─────────────────────────────────────────────────────────────────────────┘

Archiver Type    │ Typical Duration │ Lock Held │ Max Lock Time
─────────────────┼──────────────────┼───────────┼──────────────
SingleFile       │ 10-30 seconds    │ Full      │ 10 minutes
Monolith         │ 5-15 seconds     │ Full      │ 10 minutes
PDF              │ 15-45 seconds    │ Full      │ 10 minutes
Screenshot       │ 10-20 seconds    │ Full      │ 10 minutes
Readability      │ 1-5 seconds      │ Full      │ 10 minutes

Notes:
- Lock held for entire archiving operation
- Different artifacts can be processed in parallel
- Same artifact serialized (one at a time)
- Task timeout: 10 minutes (hard limit)
- After timeout: SIGTERM → SIGKILL → transaction rolled back
```

## Summary

### Key Improvements

1. **Single Transaction Scope**
   - All changes committed atomically
   - Automatic rollback on failure
   - No partial state possible

2. **Row-Level Locking**
   - SELECT FOR UPDATE prevents concurrent updates
   - Serializes access to same artifact
   - No race conditions

3. **Zombie Cleanup**
   - Periodic detection every 15 minutes
   - Automatic failure marking
   - No manual intervention needed

4. **Automatic Recovery**
   - Worker crash → rollback → retry
   - Database connection loss → rollback
   - OOM kill → rollback

### Transaction Guarantees

✅ **Atomicity** - All or nothing
✅ **Consistency** - Valid state always
✅ **Isolation** - No interference between transactions
✅ **Durability** - Committed changes persist
