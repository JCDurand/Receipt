# Shared by the scripts in this folder. Leaves the shell in the repo root,
# where docker compose finds .env and the Compose files.

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

die() {
    echo "ERROR: $*" >&2
    exit 1
}

# Prints the value of a key in .env, without quotes
env_value() {
    sed -n "s/^$1=[\"']\{0,1\}\([^\"']*\).*/\1/p" .env | tail -n 1
}

[ -f .env ] || die ".env is missing. Run ./start_prod.sh first."
grep -q '^COMPOSE_FILE=.*docker-compose\.prod\.yml' .env || die ".env is not a production file."

BACKUP_DIR=${BACKUP_DIR:-/mnt/data/backups/expense-tracker}
