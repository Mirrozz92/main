#!/usr/bin/env bash
# FastSub PostgreSQL backup script.
#
# - Создаёт сжатый pg_dump (zstd -19, custom format)
# - Хранит локально N часов (по умолчанию 24)
# - Копирует на удалённый storage-сервер через rsync (если настроен)
# - Опционально отправляет в Telegram-канал
#
# Запуск из cron: 0 */4 * * * /opt/fastsub/deploy/scripts/backup.sh
set -euo pipefail

# Загружаем env
if [ -f "/opt/fastsub/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source /opt/fastsub/.env
    set +a
else
    echo "ERROR: /opt/fastsub/.env not found" >&2
    exit 1
fi

TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
LOCAL_DIR="${BACKUP_LOCAL_DIR:-/var/backups/postgres}"
RETENTION_HOURS="${BACKUP_LOCAL_RETENTION_HOURS:-24}"
DUMP_FILE="${LOCAL_DIR}/fastsub_${TIMESTAMP}.dump.zst"
LOG_FILE="${LOCAL_DIR}/backup.log"

mkdir -p "${LOCAL_DIR}"

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "${LOG_FILE}"
}

log "Starting backup → ${DUMP_FILE}"

# pg_dump через docker compose
docker compose -f /opt/fastsub/docker-compose.yml exec -T postgres \
    pg_dump \
        -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" \
        -Fc \
        --no-owner \
        --no-privileges \
    | zstd -19 -q -o "${DUMP_FILE}"

SIZE="$(du -h "${DUMP_FILE}" | cut -f1)"
log "Local backup created: ${DUMP_FILE} (${SIZE})"

# --- Cleanup старых локальных бэкапов ---
find "${LOCAL_DIR}" -name 'fastsub_*.dump.zst' -mmin "+$((RETENTION_HOURS * 60))" -delete
log "Cleaned up local backups older than ${RETENTION_HOURS}h"

# --- Remote rsync ---
if [ -n "${BACKUP_REMOTE_HOST:-}" ] && [ -n "${BACKUP_REMOTE_USER:-}" ]; then
    log "Syncing to remote ${BACKUP_REMOTE_USER}@${BACKUP_REMOTE_HOST}:${BACKUP_REMOTE_PATH}"
    rsync -az \
        -e "ssh -i ${BACKUP_REMOTE_SSH_KEY} -o StrictHostKeyChecking=no -o ConnectTimeout=10" \
        "${DUMP_FILE}" \
        "${BACKUP_REMOTE_USER}@${BACKUP_REMOTE_HOST}:${BACKUP_REMOTE_PATH}/" \
        && log "Remote sync OK" \
        || log "WARNING: remote sync FAILED (will retry next run)"
else
    log "Remote sync skipped (BACKUP_REMOTE_HOST not set)"
fi

# --- Telegram backup (опционально, для маленьких БД до ~2GB) ---
if [ -n "${BACKUP_TG_CHAT_ID:-}" ] && [ -n "${ADMIN_BOT_TOKEN:-}" ]; then
    SIZE_BYTES="$(stat -c%s "${DUMP_FILE}")"
    MAX_BYTES=$((2 * 1024 * 1024 * 1024))  # 2 GB
    if [ "${SIZE_BYTES}" -lt "${MAX_BYTES}" ]; then
        # Шлём только раз в сутки (в 03:00)
        HOUR="$(date -u +%H)"
        if [ "${HOUR}" = "03" ]; then
            log "Sending backup to Telegram chat ${BACKUP_TG_CHAT_ID}"
            curl -sS -X POST \
                "https://api.telegram.org/bot${ADMIN_BOT_TOKEN}/sendDocument" \
                -F "chat_id=${BACKUP_TG_CHAT_ID}" \
                -F "document=@${DUMP_FILE}" \
                -F "caption=FastSub backup ${TIMESTAMP}" \
                > /dev/null \
                && log "Telegram backup OK" \
                || log "WARNING: Telegram backup FAILED"
        fi
    else
        log "Backup too large for Telegram (${SIZE_BYTES} bytes)"
    fi
fi

log "Backup completed successfully"
