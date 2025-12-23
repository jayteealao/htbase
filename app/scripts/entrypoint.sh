#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/app"
cd "$APP_DIR"
export ALEMBIC_CONFIG="/app/alembic.ini"

# Use .env.default if no .env file is present
# if [ ! -f /app/.env ] && [ -f /app/.env.default ]; then
#     echo "[entrypoint] No .env file found, using .env.default..."
#     cp /app/.env.default /app/.env
# fi

echo "=== Container Startup Diagnostics ==="
echo "[entrypoint] Current directory: $(pwd)"
echo "[entrypoint] Python version: $(python --version 2>&1 || echo 'Python not found')"
echo "[entrypoint] Alembic version: $(alembic --version 2>&1 || echo 'Alembic not found')"
echo ""
echo "[entrypoint] Database Configuration:"
echo "  DB_HOST: ${DB_HOST:-<not set>}"
echo "  DB_PORT: ${DB_PORT:-<not set>}"
echo "  DB_NAME: ${DB_NAME:-<not set>}"
echo "  DB_USER: ${DB_USER:-<not set>}"
echo "  DB_PASSWORD: ${DB_PASSWORD:+<set (${#DB_PASSWORD} chars)>}"
echo "  DB_PASSWORD: ${DB_PASSWORD:-<not set>}"
echo ""
echo "[entrypoint] Testing database connectivity..."
if command -v psql >/dev/null 2>&1 && [ -n "${DB_HOST:-}" ]; then
    echo "[entrypoint] Attempting connection to ${DB_HOST}:${DB_PORT}..."
    timeout 5 bash -c "cat < /dev/null > /dev/tcp/${DB_HOST}/${DB_PORT}" 2>&1 && \
        echo "[entrypoint] ✓ TCP connection successful" || \
        echo "[entrypoint] ✗ TCP connection failed - cannot reach ${DB_HOST}:${DB_PORT}"
else
    echo "[entrypoint] Skipping connectivity test (psql not available or DB_HOST not set)"
fi
echo "===================================="
echo ""

echo "[entrypoint] Applying DB migrations..."
retries=${ALEMBIC_RETRIES:-3}
delay=${ALEMBIC_RETRY_DELAY:-3}
for i in $(seq 1 "$retries"); do
  echo "[entrypoint] Migration attempt $i of $retries..."
  if alembic -c "$ALEMBIC_CONFIG" upgrade head 2>&1; then
    echo "[entrypoint] ✓ Migrations complete."
    break
  fi
  migration_exit_code=$?
  if [[ "$i" -eq "$retries" ]]; then
    echo "" >&2
    echo "=====================================" >&2
    echo "[entrypoint] ✗ Migration FAILED after $retries attempts." >&2
    echo "[entrypoint] Last exit code: $migration_exit_code" >&2
    echo "[entrypoint] This usually means:" >&2
    echo "  1. Database credentials are incorrect or not set" >&2
    echo "  2. Database server is unreachable from Cloud Run" >&2
    echo "  3. Database does not exist or user lacks permissions" >&2
    echo "" >&2
    echo "[entrypoint] Check Cloud Build logs for DB_* substitution values" >&2
    echo "[entrypoint] Check database server allows connections from Cloud Run IP ranges" >&2
    echo "=====================================" >&2
    exit 1
  fi
  echo "[entrypoint] Migration attempt $i failed (exit code: $migration_exit_code), retrying in ${delay}s..."
  sleep "$delay"
done

echo ""
echo "[entrypoint] Starting uvicorn..."
PORT=${PORT:-8080}
echo "[entrypoint] Listening on 0.0.0.0:$PORT"
exec uvicorn server:app --host 0.0.0.0 --port "$PORT"
