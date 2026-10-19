#!/bin/bash

# The web container runs as the user who starts it, and root cannot be that user
if [ "$(id -u)" = 0 ]; then
  echo "Run this script as your own user, not as root or with sudo."
  echo "If docker needs sudo, add yourself to the docker group first."
  exit 1
fi

echo "Copying .env for dev environment"
cp .env.dev.example .env
printf '\n# Host user that the web container runs as\nAPP_UID=%s\n' "$(id -u)" >> .env

echo "Generating secrets..."
./generate_secrets.sh

echo "Starting the Docker environment..."
# Recreated so they mount the current files in secrets/: a container left
# running from an earlier checkout still sees the secrets that checkout had
docker compose up -d --wait --force-recreate db

# A database volume from an earlier run still has its old password
docker compose exec -T db sh -c 'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v pw="$(cat /run/secrets/postgres_password)"' <<< "ALTER USER CURRENT_USER PASSWORD :'pw';"


# Load the shared demo database on every development startup.
# This intentionally replaces all existing data in the configured dev database.
if [ ! -f demo/newspeak-demo.dump ]; then
  echo "ERROR: demo/newspeak-demo.dump not found."
  echo "Cannot reset the development database."
  exit 1
fi


echo "Stopping services that may be using the development database..."
if ! docker compose stop web frontend dbeaver; then
  echo "ERROR: Could not stop services before resetting the database."
  exit 1
fi

echo "Resetting the development database to the shared demo dataset..."
if ! docker compose exec -T db sh -c '
  dropdb --if-exists --force -U "$POSTGRES_USER" "$POSTGRES_DB" &&
  createdb -U "$POSTGRES_USER" -O "$POSTGRES_USER" "$POSTGRES_DB"
'; then
  echo "ERROR: Could not recreate the development database."
  exit 1
fi

echo "Restoring demo database..."
if ! docker compose exec -T db sh -c '
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
' < demo/newspeak-demo.dump; then
  echo "ERROR: Demo database restore failed."
  exit 1
fi

echo "Demo database restored successfully."

docker compose up --build -d --force-recreate

# The container used to run as root, and what it wrote back then is still owned
# by root on the host, where the new user cannot change it
docker compose exec -T --user root web sh -c 'for d in document_storage tmp text_layered staticfiles; do [ -e "$d" ] && chown -R "$0" "$d"; done; true' "$(id -u):$(id -g)"

echo "Waiting for servers..."
sleep 8

echo "Opening the app in your browser..."

if which xdg-open > /dev/null; then
  xdg-open http://localhost > /dev/null 2>&1 &
  xdg-open http://localhost:8978 > /dev/null 2>&1 &

elif which open > /dev/null; then
  open http://localhost > /dev/null 2>&1 &
  open http://localhost:8978 > /dev/null 2>&1 &
else
  echo "Could not detect OS web browser launcher. Open http://localhost and http://localhost:8978 manually."
fi