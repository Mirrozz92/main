#!/usr/bin/env bash
# FastSub deployment script (без CI/CD, ручной запуск).
#
# Usage: ./deploy.sh [--no-backup] [--no-migrate]
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/fastsub}"
DO_BACKUP=1
DO_MIGRATE=1

for arg in "$@"; do
    case "${arg}" in
        --no-backup) DO_BACKUP=0 ;;
        --no-migrate) DO_MIGRATE=0 ;;
        *) echo "Unknown arg: ${arg}" >&2; exit 2 ;;
    esac
done

cd "${PROJECT_DIR}"

echo "==> Pulling latest changes"
git pull --ff-only

if [ "${DO_BACKUP}" -eq 1 ]; then
    echo "==> Pre-deploy backup"
    bash "${PROJECT_DIR}/deploy/scripts/backup.sh"
fi

echo "==> Building images"
docker compose build

echo "==> Bringing services up"
docker compose up -d --remove-orphans

if [ "${DO_MIGRATE}" -eq 1 ]; then
    echo "==> Waiting for postgres"
    for _ in {1..30}; do
        if docker compose exec -T postgres pg_isready -U "$(grep ^POSTGRES_USER .env | cut -d= -f2)" >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    echo "==> Running migrations"
    docker compose run --rm api alembic upgrade head
fi

echo "==> Health check"
sleep 3
for _ in {1..20}; do
    if curl -sf http://localhost:8000/health >/dev/null; then
        echo "==> Deployment successful ✓"
        exit 0
    fi
    sleep 1
done

echo "ERROR: health check failed" >&2
exit 1
