#!/bin/bash
# Stop if a step fails, rather than serving with a database that is behind
set -e

echo "Running database migrations..."
python manage.py migrate --noinput

# Nothing is parsing when the server has only just started
python manage.py fail_stale_processing

echo "Starting server..."
# exec, so the server receives docker's stop signal and can shut down cleanly
if [ "$DJANGO_DEBUG" = "1" ]; then
    exec python manage.py runserver 0.0.0.0:8000
else
    exec gunicorn config.wsgi:application -c gunicorn.conf.py
fi
