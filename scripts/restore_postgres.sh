#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/backup.sql.gz" >&2
  exit 1
fi

BACKUP_FILE="$1"
PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/ecommerce}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env}"

if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

if [[ "${DB_ENGINE:-sqlite}" != "postgres" ]]; then
  echo "DB_ENGINE is not postgres. Current value: ${DB_ENGINE:-unset}" >&2
  exit 1
fi

export PGPASSWORD="${DB_PASSWORD:-}"

gunzip -c "$BACKUP_FILE" | psql \
  --host "${DB_HOST:-127.0.0.1}" \
  --port "${DB_PORT:-5432}" \
  --username "${DB_USER:-postgres}" \
  --dbname "${DB_NAME:-ecommerce}"

echo "Restore completed from: $BACKUP_FILE"
