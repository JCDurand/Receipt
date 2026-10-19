#!/bin/bash
# Builds and starts the production stack on the server. deploy/deploy.sh runs
# this after pulling; see DEPLOYMENT.md.

cd "$(dirname "$0")" || exit 1

# The web container runs as the user who starts it, and root cannot be that user
if [ "$(id -u)" = 0 ]; then
  echo "Run this script as your own user, not as root or with sudo."
  echo "If docker needs sudo, add yourself to the docker group first."
  exit 1
fi

# .env holds this server's own settings, so it is created once and then kept
if [ ! -f .env ]; then
  (umask 077 && cp .env.prod.example .env)
  echo "Created .env from .env.prod.example."
  echo "Fill in the empty values (DJANGO_ALLOWED_HOSTS and so on), then run this script again."
  exit 1
fi

# start_dev.sh leaves a development .env behind, which would run with debug on
if ! grep -q '^COMPOSE_FILE=.*docker-compose\.prod\.yml' .env; then
  echo ".env is not a production file. Move it aside and run this script again to get a new one."
  exit 1
fi

# Nginx and Django both refuse to serve a site they have no name for
for name in DOMAIN DJANGO_ALLOWED_HOSTS; do
  if ! grep -Eq "^$name=[\"']?[^\"'[:space:]]" .env; then
    echo "$name is empty in .env. Fill it in, then run this script again."
    exit 1
  fi
done

set -e

echo "Generating secrets..."
./generate_secrets.sh

# Compose can only take the CloudBeaver login from the environment
if ! grep -q '^DBEAVER_PASSWORD=' .env; then
  echo "DBEAVER_PASSWORD=$(cat secrets/dbeaver_password)" >> .env
fi

# The web image is built with the id of the user who owns secrets/
if ! grep -q '^APP_UID=' .env; then
  echo "APP_UID=$(id -u)" >> .env
fi

echo "Starting the Docker environment..."
# Recreated so it mounts the current secrets/postgres_password: a container
# left running from an earlier checkout still sees the file that checkout had
docker compose up -d --wait --force-recreate db

# A database volume from an earlier run still has its old password
docker compose exec -T db sh -c 'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v pw="$(cat /run/secrets/postgres_password)"' <<< "ALTER USER CURRENT_USER PASSWORD :'pw';"

# Returns once Django passes its health check and Nginx is running
docker compose up --build -d --wait

domain=$(sed -n "s/^DOMAIN=[\"']\{0,1\}\([^\"']*\).*/\1/p" .env)
echo "The stack is up. The site is served at https://$domain/"
