#!/bin/sh

set -e

python manage.py migrate --no-input
python manage.py collectstatic --no-input

GUNICORN_BIND=${GUNICORN_BIND:-0.0.0.0:8000}
GUNICORN_WORKERS=${GUNICORN_WORKERS:-3}
GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT:-90}
GUNICORN_MAX_REQUESTS=${GUNICORN_MAX_REQUESTS:-1000}
GUNICORN_MAX_REQUESTS_JITTER=${GUNICORN_MAX_REQUESTS_JITTER:-50}

exec gunicorn config.wsgi:application \
  --bind "${GUNICORN_BIND}" \
  --workers "${GUNICORN_WORKERS}" \
  --timeout "${GUNICORN_TIMEOUT}" \
  --max-requests "${GUNICORN_MAX_REQUESTS}" \
  --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER}" \
  --access-logfile "-" \
  --error-logfile "-"
