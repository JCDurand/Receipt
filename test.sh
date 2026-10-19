#!/bin/bash
set -e

echo "Starting Tests..."
docker compose exec -T web python manage.py test core
echo "Test execution complete"