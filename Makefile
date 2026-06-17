.PHONY: help build up down restart logs ps shell-api shell-db migrate makemigration test lint format backup deploy

help:
	@echo "FastSub — make commands"
	@echo ""
	@echo "  make up              — Запустить все сервисы"
	@echo "  make down            — Остановить все сервисы"
	@echo "  make restart         — Перезапустить"
	@echo "  make build           — Пересобрать образы"
	@echo "  make logs S=api      — Логи сервиса (api/advertiser_bot/admin_bot/...)"
	@echo "  make ps              — Список запущенных сервисов"
	@echo "  make shell-api       — Зайти в контейнер api"
	@echo "  make shell-db        — Зайти в psql"
	@echo "  make migrate         — Применить миграции"
	@echo "  make makemigration M='message' — Создать новую миграцию"
	@echo "  make test            — Запустить тесты"
	@echo "  make lint            — ruff + mypy"
	@echo "  make format          — ruff format"
	@echo "  make backup          — Запустить бэкап БД"
	@echo "  make deploy          — Деплой на сервер"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f --tail=200 $(S)

ps:
	docker compose ps

shell-api:
	docker compose exec api bash

shell-db:
	docker compose exec postgres psql -U $$POSTGRES_USER -d $$POSTGRES_DB

migrate:
	docker compose run --rm api alembic upgrade head

makemigration:
	@test -n "$(M)" || (echo "Usage: make makemigration M='your message'"; exit 1)
	docker compose run --rm api alembic revision --autogenerate -m "$(M)"

test:
	docker compose run --rm api pytest -v

lint:
	docker compose run --rm api ruff check src
	docker compose run --rm api mypy src

format:
	docker compose run --rm api ruff format src
	docker compose run --rm api ruff check --fix src

backup:
	bash deploy/scripts/backup.sh

deploy:
	bash deploy/scripts/deploy.sh
