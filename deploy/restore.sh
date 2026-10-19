#!/bin/bash
# Restores a backup made by deploy/backup.sh. See DEPLOYMENT.md.
#
#   deploy/restore.sh drill [dump]
#       Restores the dump (the newest one by default) into a scratch database,
#       from either pg_dump's custom format or plain SQL,
#       reports what is in it and drops it again. The live site is not touched.
#
#   deploy/restore.sh live <dump> [media archive]
#       Replaces the live database with the dump and, if given, the uploaded
#       documents with the archive. The site is down while it runs.
set -euo pipefail

. "$(dirname "$0")/lib.sh"

SCRATCH_DB=restore_drill

usage() {
    sed -n '2,12s/^# \{0,1\}//p' "$0"
    exit 1
}

# Runs a command in the db container as the database's own user
db() {
    docker compose exec -T db sh -c 'export PGUSER="$POSTGRES_USER"; exec "$@"' sh "$@"
}

# Fills an empty database from a dump. backup.sh writes custom-format dumps,
# which start with PGDMP; anything else, such as demo/newspeak-demo.dump, is
# plain SQL and goes through psql instead.
load() {
    if [ "$(head -c 5 "$2")" = PGDMP ]; then
        db pg_restore --no-owner --exit-on-error -d "$1" < "$2"
    else
        db psql -q -v ON_ERROR_STOP=1 --single-transaction -d "$1" < "$2" > /dev/null
    fi
}

report() {
    db psql -d "$1" -At -F ': ' <<'SQL'
SELECT 'tables', count(*) FROM information_schema.tables WHERE table_schema = 'public';
SELECT 'migrations applied', count(*) FROM django_migrations;
SELECT 'users', count(*) FROM core_user;
SELECT 'statements', count(*) FROM core_bankstatement;
SELECT 'receipts', count(*) FROM core_receipt;
SQL
}

mode=${1:-}
dump=${2:-}

case "$mode" in
drill)
    [ -n "$dump" ] || dump=$(ls -1 "$BACKUP_DIR"/daily/db-*.dump 2> /dev/null | tail -n 1)
    [ -f "$dump" ] || die "No dump found. Give one, or run deploy/backup.sh first."

    echo "Restoring $dump into the scratch database $SCRATCH_DB"
    db dropdb --if-exists "$SCRATCH_DB"
    db createdb "$SCRATCH_DB"
    trap 'db dropdb --if-exists "$SCRATCH_DB"' EXIT
    load "$SCRATCH_DB" "$dump"
    report "$SCRATCH_DB"
    echo "Restore drill PASSED; the scratch database is dropped again."
    ;;

live)
    media=${3:-}
    [ -f "$dump" ] || usage
    [ -z "$media" ] || [ -f "$media" ] || die "$media does not exist."
    live_db=$(env_value POSTGRES_DB)

    echo "This REPLACES the live database with $dump"
    [ -z "$media" ] || echo "and ALL uploaded documents with $media"
    read -r -p "Type 'restore' to go on: " answer
    [ "$answer" = restore ] || die "Stopped; nothing was changed."

    # What is live now may be wanted back
    deploy/backup.sh

    echo "Stopping Django"
    docker compose stop web

    echo "Restoring the database"
    db dropdb --force --maintenance-db=postgres "$live_db"
    db createdb --maintenance-db=postgres "$live_db"
    load "$live_db" "$dump"

    if [ -n "$media" ]; then
        echo "Restoring the uploaded documents"
        docker compose run --rm --no-deps -T --entrypoint sh web -c \
            'find /app/document_storage -mindepth 1 -delete && tar -xzf - -C /app' < "$media"
    fi

    # Django applies any migrations that are newer than the dump as it starts
    echo "Starting Django"
    docker compose up -d --wait web
    report "$live_db"
    echo "Restore complete."
    ;;

*)
    usage
    ;;
esac
