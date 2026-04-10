#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/home/ubuntu/ecommerce}"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env}"
BACKUP_DIR="${BACKUP_DIR:-/home/ubuntu/backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

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

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.sql.gz"

export PGPASSWORD="${DB_PASSWORD:-}"

pg_dump \
  --host "${DB_HOST:-127.0.0.1}" \
  --port "${DB_PORT:-5432}" \
  --username "${DB_USER:-postgres}" \
  --dbname "${DB_NAME:-ecommerce}" | gzip > "$BACKUP_FILE"

find "$BACKUP_DIR" -type f -name "*.sql.gz" -mtime "+$RETENTION_DAYS" -delete

echo "Backup created: $BACKUP_FILE"
