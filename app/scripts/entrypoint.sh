#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/app"
cd "$APP_DIR"
export ALEMBIC_CONFIG="/app/alembic.ini"

echo "[entrypoint] Applying DB migrations..."
retries=${ALEMBIC_RETRIES:-3}
delay=${ALEMBIC_RETRY_DELAY:-3}
for i in $(seq 1 "$retries"); do
  if alembic -c "$ALEMBIC_CONFIG" upgrade head; then
    echo "[entrypoint] Migrations complete."
    break
  fi
  if [[ "$i" -eq "$retries" ]]; then
    echo "[entrypoint] Migration failed after $retries attempts." >&2
    exit 1
  fi
  echo "[entrypoint] Migration attempt $i failed, retrying in ${delay}s..."
  sleep "$delay"
done

exec uvicorn server:app --host 0.0.0.0 --port 8000
