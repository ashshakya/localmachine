#!/bin/sh
set -eu

# This image is intentionally self-contained and always uses its persistent
# SQLite volume, even if a host env-file still contains legacy MySQL settings.
export DASHBOARD_DATABASE_ENGINE=sqlite
export SQLITE_DATABASE_PATH="${SQLITE_DATABASE_PATH:-/data/dashboard.sqlite3}"

echo "Database: SQLite (${SQLITE_DATABASE_PATH})"

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  attempt=1
  max_attempts="${MIGRATION_MAX_ATTEMPTS:-12}"
  until python manage.py migrate --noinput; do
    if [ "$attempt" -ge "$max_attempts" ]; then
      echo "Database migrations failed after ${attempt} attempts." >&2
      exit 1
    fi
    echo "Database is unavailable; retrying migrations (${attempt}/${max_attempts})..." >&2
    attempt=$((attempt + 1))
    sleep 5
  done
fi

if [ "${1:-}" = "serve" ]; then
  shift
  set -- gunicorn project_dashboard.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --access-logfile - \
    --error-logfile - \
    "$@"
fi

exec "$@"
