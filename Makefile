
# =============================================================================

# BoxUp — Developer Commands

# =============================================================================

# Usage: make <command>

# Run `make help` to see all commands.

.PHONY: help install up down logs ps reset migrate seed dev lint test

# Default target

help:

	@echo ""

	@echo "BoxUp — Available Commands"

	@echo "─────────────────────────────────────────"

	@echo "  make install    Install all Python + JS dependencies"

	@echo "  make up         Start all infrastructure (Kafka, DB, Redis, MLflow)"

	@echo "  make down       Stop all infrastructure"

	@echo "  make logs       Tail logs from all services"

	@echo "  make ps         Show running containers and health status"

	@echo "  make reset      DANGER: Stop everything and delete all data"

	@echo "  make migrate    Run database migrations"

	@echo "  make seed       Ingest sample F1 sessions (2024 British GP)"

	@echo "  make dev        Show the commands for local backend + frontend dev"

	@echo "  make lint       Run ruff + mypy on all Python code"

	@echo "  make test       Run pytest across all packages"

	@echo "─────────────────────────────────────────"

	@echo ""

# ── Dependencies ──────────────────────────────────────────────────────────────

install:

	uv sync

	cd apps/frontend && pnpm install

# ── Infrastructure ────────────────────────────────────────────────────────────

up:

	docker compose -f infra/docker-compose.yml up -d

	@echo ""

	@echo "Infrastructure started:"

	@echo "   Kafka UI   → http://localhost:8080"

	@echo "   MLflow     → http://localhost:5001"

	@echo "   Postgres   → localhost:5432"

	@echo "   Redis      → localhost:6379"

	@echo ""

	@echo "Run 'make ps' to check health status."

down:

	docker compose -f infra/docker-compose.yml down

logs:

	docker compose -f infra/docker-compose.yml logs -f

ps:

	docker compose -f infra/docker-compose.yml ps

reset:

	@echo " This will DELETE all data (database, kafka, redis). Are you sure?"

	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ]

	docker compose -f infra/docker-compose.yml down -v

	@echo "All data wiped."

# ── Database ──────────────────────────────────────────────────────────────────

migrate:

	uv run alembic -c apps/backend/alembic.ini upgrade head

seed:
	uv run python -m ingestion.ingest_session --year 2024 --gp "British" --session Q
	uv run python -m ingestion.ingest_session --year 2024 --gp "British" --session R
	uv run python -m ingestion.ingest_session --year 2024 --gp "British" --session FP2 --skip-telemetry
	uv run python -m ingestion.ingest_session --year 2024 --gp "Monaco" --session Q
	uv run python -m ingestion.ingest_session --year 2024 --gp "Monaco" --session R
	uv run python -m ingestion.ingest_session --year 2024 --gp "Monaco" --session FP2 --skip-telemetry
	uv run python -m ingestion.ingest_session --year 2024 --gp "Monza" --session Q
	uv run python -m ingestion.ingest_session --year 2024 --gp "Monza" --session R
	uv run python -m ingestion.ingest_session --year 2024 --gp "Monza" --session FP2 --skip-telemetry

# Backfill historical sessions (resumable — already-ingested sessions are skipped).
#   make backfill START_YEAR=2022 END_YEAR=2025
#   make backfill START_YEAR=2024 END_YEAR=2024 SKIP_TELEMETRY=1
#   make backfill START_YEAR=2022 END_YEAR=2025 DRY_RUN=1
backfill:
	uv run python -m ingestion.backfill --start-year $(START_YEAR) --end-year $(END_YEAR) \
		$(if $(SKIP_TELEMETRY),--skip-telemetry,) \
		$(if $(DRY_RUN),--dry-run,)


# ── Development ───────────────────────────────────────────────────────────────

dev:
	@echo "Run these in separate terminals:"
	@echo "  make backend   # API at http://localhost:8000"
	@echo "  make frontend  # App at http://localhost:3000"

# ── Code Quality ──────────────────────────────────────────────────────────────

lint:

	uv run ruff check apps/ packages/

	uv run ruff format --check apps/ packages/

lint-fix:

	uv run ruff check --fix apps/ packages/

	uv run ruff format apps/ packages/

type-check:

	uv run mypy apps/ packages/

test:

	uv run pytest apps/ packages/ -v --cov --cov-report=term-missing

# ── Utilities ─────────────────────────────────────────────────────────────────

# Connect to the database directly (useful for debugging)

db-shell:

	docker exec -it pitwall-timescaledb psql -U pitwall -d pitwall

# Open a Redis CLI session

redis-shell:

	docker exec -it pitwall-redis redis-cli

topics :

	@bash infra/kafka/create-topics.sh

backend:
	uv run flask --app apps/backend/src/backend run --port 8000 --debug

frontend:
	cd apps/frontend && pnpm dev

test-backend:
	uv run pytest apps/backend/tests/ -v --cov=apps/backend/src --cov-report=term-missing

worker:
	uv run celery -A workers.celery_app worker --loglevel=info --concurrency=2

beat:
	uv run celery -A workers.celery_app beat --loglevel=info

monitor-now:
	uv run celery -A workers.celery_app call workers.tasks.monitor.check_completed_sessions

ingest-weekend:
	uv run celery -A workers.celery_app call workers.tasks.ingest.ingest_weekend \
		--args='[$(YEAR), "$(GP)", $(SPRINT)]'

storage-report:
	uv run celery -A workers.celery_app call workers.tasks.retention.storage_report
