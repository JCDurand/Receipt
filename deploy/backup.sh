#!/bin/bash
# Backs up the database and the uploaded documents to $BACKUP_DIR, checks the
# result, removes old backups and copies the new ones off the server.
# Run nightly by deploy/systemd/expense-tracker-backup.timer, and by
# deploy/deploy.sh before each deploy. See DEPLOYMENT.md.
#
# Kept on the server: every backup of the last 7 days that have one, and one
# per week for the last 4 weeks.
set -euo pipefail

. "$(dirname "$0")/lib.sh"

# Only the owner may read what is written below
umask 077
mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

# One backup at a time
exec 9> "$BACKUP_DIR/.lock"
flock -n 9 || die "Another backup is still running."

stamp=$(date -u +%Y%m%dT%H%M%SZ)
week=$(date -u +%G-W%V)
dump="$BACKUP_DIR/daily/db-$stamp.dump"
media="$BACKUP_DIR/daily/media-$stamp.tar.gz"

# A backup that failed halfway must not be mistaken for a good one
finished=0
trap '[ "$finished" = 1 ] || { rm -f "$dump" "$media"; echo "ERROR: the backup FAILED" >&2; }' EXIT

echo "Dumping the database to $dump"
docker compose exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$dump"

# pg_restore can only list a dump that is complete and readable
docker compose exec -T db pg_restore --list < "$dump" > /dev/null
[ -s "$dump" ] || die "The dump is empty."

# A one-off container on the same image and volume, so this also works while
# the web container is stopped
echo "Archiving the uploaded documents to $media"
docker compose run --rm --no-deps -T --entrypoint tar web -czf - -C /app document_storage > "$media"
tar -tzf "$media" > /dev/null

# The first backup of each week is also kept as that week's backup
[ -e "$BACKUP_DIR/weekly/db-$week.dump" ] || ln "$dump" "$BACKUP_DIR/weekly/db-$week.dump"
[ -e "$BACKUP_DIR/weekly/media-$week.tar.gz" ] || ln "$media" "$BACKUP_DIR/weekly/media-$week.tar.gz"

# Keeps the backups of the newest $2 days or weeks in $1. A name is db- or
# media-, then 8 characters that give the day (20261013) or the week (2026-W42).
prune() {
    local dir=$1 keep=$2 key
    for key in $(find "$dir" -maxdepth 1 -type f -printf '%f\n' \
                     | sed -E 's/^[a-z]+-//' | cut -c 1-8 | sort -u | head -n "-$keep"); do
        echo "Removing old backup $dir/*-$key*"
        rm -f "$dir"/db-"$key"* "$dir"/media-"$key"*
    done
}
prune "$BACKUP_DIR/daily" 7
prune "$BACKUP_DIR/weekly" 4

# From here on the local backup is good, whatever happens to the copy
finished=1

# Copied, not mirrored: removing a backup here does not remove it there. The
# bucket's own lifecycle rule removes what is older than 30 days.
remote=$(env_value BACKUP_RCLONE_REMOTE)
if [ -n "$remote" ]; then
    echo "Copying to $remote"
    rclone copy "$BACKUP_DIR/daily" "$remote/daily"
else
    echo "NOTE: BACKUP_RCLONE_REMOTE is empty in .env, so this backup exists on this server only."
fi

echo "Backup complete: $(du -h "$dump" | cut -f1) database, $(du -h "$media" | cut -f1) documents"
