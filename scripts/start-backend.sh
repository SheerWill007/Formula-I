#!/bin/sh
# Container entrypoint: apply DB migrations, then serve the Flask API.
set -e

cd /app/apps/backend
echo "Running database migrations..."
alembic upgrade head

exec gunicorn "backend:create_app()" \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-1}" \
    --threads "${GUNICORN_THREADS:-8}" \
    --timeout "${GUNICORN_TIMEOUT:-120}" \
    --graceful-timeout 30 \
    --worker-tmp-dir /dev/shm \
    --access-logfile - \
    --error-logfile -
