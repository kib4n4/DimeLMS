#!/usr/bin/env bash
set -e

# Only Postgres needs a wait-for-it step; sqlite is a local file and is always "ready".
if [ "${DEBUG}" = "False" ] || [ "${DEBUG}" = "false" ]; then
  echo "[entrypoint] DEBUG=False -> waiting for Postgres at ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}"
  until python - <<'PYEOF'
import os, socket, sys
host = os.environ.get("POSTGRES_HOST", "db")
port = int(os.environ.get("POSTGRES_PORT", "5432"))
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect((host, port))
except OSError:
    sys.exit(1)
sys.exit(0)
PYEOF
  do
    echo "[entrypoint] Postgres not ready yet, retrying in 2s..."
    sleep 2
  done
  echo "[entrypoint] Postgres is up."
fi

mkdir -p /app/data  # sqlite lives here (DEBUG=True) so it persists across container rebuilds

echo "[entrypoint] Running migrations..."
python manage.py migrate --noinput

echo "[entrypoint] Compiling translation messages (es/fr/ru)..."
django-admin compilemessages || echo "[entrypoint] compilemessages skipped/failed (non-fatal)"

echo "[entrypoint] Collecting static files..."
python manage.py collectstatic --noinput

if [ -n "${DJANGO_SUPERUSER_EMAIL}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD}" ]; then
  echo "[entrypoint] Ensuring superuser exists..."
  python manage.py createsuperuser --noinput || echo "[entrypoint] Superuser already exists, skipping."
fi

echo "[entrypoint] Starting gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --access-logfile - \
    --error-logfile -