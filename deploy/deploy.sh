#!/bin/bash
# Deploys the app on the server: back up, update the code, rebuild, restart,
# and check that the site answers. Run as the deploy user.
#
#   deploy/deploy.sh          the newest commit of the current branch
#   deploy/deploy.sh <ref>    a given commit or tag, e.g. to roll back
#
# SKIP_PULL=1 deploys the code as it is on disk (when it was copied with rsync).
# SKIP_BACKUP=1 and SKIP_PUBLIC_CHECK=1 skip those steps.
set -euo pipefail

. "$(dirname "$0")/lib.sh"

DOMAIN=$(env_value DOMAIN)
[ -n "$DOMAIN" ] || die "DOMAIN is empty in .env."

# Nothing to back up on the first deploy, before the database exists
if [ "${SKIP_BACKUP:-0}" != 1 ] && [ -n "$(docker compose ps -q --status running db)" ]; then
    echo "==> Backing up before the deploy"
    deploy/backup.sh
fi

if [ "${SKIP_PULL:-0}" != 1 ]; then
    echo "==> Updating the code"
    if [ $# -ge 1 ]; then
        git fetch --tags origin
        git checkout --detach "$1"
    else
        git pull --ff-only
    fi
fi
echo "Deploying $(git log -1 --format='%h %s' 2>/dev/null || echo 'the code on disk')"

# Builds the images and starts the stack. Django applies the migrations before
# Gunicorn starts, and Compose waits for its health check.
echo "==> Building and starting"
./start_prod.sh

# Asks until the answer is 200, for up to a minute
wait_for_health() {
    local i
    for i in $(seq 1 20); do
        if curl -fsS -m 10 -o /dev/null "$@" "https://$DOMAIN/api/health/"; then
            return 0
        fi
        sleep 3
    done
    return 1
}

failed() {
    echo
    docker compose ps
    docker compose logs --tail 40 web frontend
    die "$1 The deploy has FAILED; see DEPLOYMENT.md for the rollback."
}

# First straight to this server's Nginx, then the way a visitor comes in
echo "==> Checking https://$DOMAIN/api/health/"
wait_for_health --resolve "$DOMAIN:443:127.0.0.1" \
    || failed "The health check does not return 200 on this server."
if [ "${SKIP_PUBLIC_CHECK:-0}" != 1 ]; then
    wait_for_health \
        || failed "The health check works on this server but not through the public address."
fi

docker image prune -f > /dev/null
echo "==> Deployed. https://$DOMAIN/api/health/ returns 200."
