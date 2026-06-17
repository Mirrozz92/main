#!/usr/bin/env bash
# FastSub restore script.
# Usage: ./restore.sh /path/to/backup.dump.zst
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup-file.dump.zst>" >&2
    exit 1
fi

BACKUP_FILE="$1"
if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERROR: file not found: ${BACKUP_FILE}" >&2
    exit 1
fi

if [ -f "/opt/fastsub/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source /opt/fastsub/.env
    set +a
fi

echo "!!! WARNING: this will DROP and RESTORE database ${POSTGRES_DB}"
echo "Press Ctrl+C to abort, or Enter to continue."
read -r

echo "==> Stopping app services (keeping postgres running)"
docker compose stop api advertiser_bot admin_bot checker_bots worker scheduler

echo "==> Dropping and recreating database"
docker compose exec -T postgres psql -U "${POSTGRES_USER}" -d postgres -c \
    "DROP DATABASE IF EXISTS ${POSTGRES_DB};"
docker compose exec -T postgres psql -U "${POSTGRES_USER}" -d postgres -c \
    "CREATE DATABASE ${POSTGRES_DB};"

echo "==> Restoring from ${BACKUP_FILE}"
zstd -dc "${BACKUP_FILE}" | docker compose exec -T postgres \
    pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --no-owner --no-privileges

echo "==> Restarting services"
docker compose up -d

echo "==> Done ✓"
