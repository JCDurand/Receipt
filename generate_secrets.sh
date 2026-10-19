#!/bin/bash
# Generates the files behind the Docker secrets in docker-compose.yml.
# Existing secrets are kept: a new Django key would log every user out, and
# Postgres only reads its password when the data volume is first created.
set -euo pipefail

cd "$(dirname "$0")"

# Only the owner may read what is written below
umask 077
mkdir -p secrets

generate() {
    local file="secrets/$1"
    local bytes="$2"

    if [ -s "$file" ]; then
        echo "Keeping existing $file"
        return
    fi

    # Hex only, so the value is safe in SQL, connection strings and shells
    openssl rand -hex "$bytes" > "$file"
    echo "Generated $file"
}

generate django_secret_key 50
generate postgres_password 32
generate dbeaver_password 32
