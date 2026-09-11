.PHONY: help up down build logs migrate seed test lint format

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# === Docker ===

up: ## Start all services
	docker compose up -d

down: ## Stop all services
	docker compose down

build: ## Build Docker images
	docker compose build

rebuild: ## Force rebuild and start
	docker compose up -d --build --force-recreate

logs: ## Tail logs all services
	docker compose logs -f

logs-app: ## Tail app logs only
	docker compose logs -f app

logs-db: ## Tail postgres logs only
	docker compose logs -f postgres

restart-app: ## Restart app service only
	docker compose restart app

# === Database ===

migrate: ## Run Alembic migrations
	docker compose exec app alembic upgrade head

migrate-new: ## Create new migration. Usage: make migrate-new MSG="add poi table"
	docker compose exec app alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback one migration
	docker compose exec app alembic downgrade -1

migrate-history: ## Show migration history
	docker compose exec app alembic history

# === Seed Data ===

seed: seed-poi seed-kb ## Seed all data

seed-poi: ## Seed POI data 30 records
	docker compose exec app python -m scripts.seed_poi

seed-kb: ## Seed Knowledge Base 25 articles with embedding
	docker compose exec app python -m scripts.seed_kb

# === App ===

run-local: ## Run app locally without Docker
	uvicorn src.travelmate.main:app --reload --host 0.0.0.0 --port 8000

shell: ## Open shell in app container
	docker compose exec app bash

db-shell: ## Open psql in postgres container
	docker compose exec postgres psql -U travelmate -d travelmate_db

redis-cli: ## Open redis-cli
	docker compose exec redis redis-cli

# === Testing ===

test: ## Run all tests
	docker compose exec app pytest tests/ -v

test-unit: ## Run unit tests
	docker compose exec app pytest tests/unit/ -v

test-integration: ## Run integration tests
	docker compose exec app pytest tests/integration/ -v

test-regression: ## Run regression tests golden set
	docker compose exec app pytest tests/regression/ -v

test-cov: ## Run tests with coverage
	docker compose exec app pytest tests/ --cov=src/travelmate --cov-report=term-missing

# === Code Quality ===

lint: ## Run linter ruff
	docker compose exec app ruff check src/ tests/

format: ## Format code ruff
	docker compose exec app ruff format src/ tests/

typecheck: ## Run type checker mypy
	docker compose exec app mypy src/travelmate

# === Evaluation ===

eval: ## Run Langfuse evaluation with golden set
	docker compose exec app python -m scripts.eval_langfuse

# === Cleanup ===

clean: ## Remove volumes and orphans
	docker compose down -v --remove-orphans

reset: clean up migrate seed ## Full reset: clean + up + migrate + seed
