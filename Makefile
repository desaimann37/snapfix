# SnapFix developer commands. Works with GNU make on macOS/Linux and on Windows (Git Bash or cmd).
COMPOSE ?= docker compose

.DEFAULT_GOAL := help
.PHONY: help dev down logs seed demo-reset test test-backend test-frontend test-e2e eval eval-mock db backend frontend

help: ## list commands
	@echo "make dev         build + start db, backend, frontend (http://localhost:3000)"
	@echo "make seed        reseed the demo database"
	@echo "make demo-reset  restore the exact demo starting state"
	@echo "make test        backend unit/integration tests + frontend typecheck/lint"
	@echo "make test-e2e    Playwright smoke test against the running stack"
	@echo "make eval        run the evaluation harness (live if ANTHROPIC_API_KEY is set, else mock)"
	@echo "make down        stop everything"
	@echo "Local (no Docker for app code): make db, then make backend and make frontend in two terminals"

dev: ## start the full stack and wait until it is healthy
	$(COMPOSE) up -d --build --wait
	@echo "SnapFix is up: frontend http://localhost:3000  |  API docs http://localhost:8000/docs"

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f backend frontend

seed: ## wipe + reseed demo data
	$(COMPOSE) exec backend python -m app.seed.generate

demo-reset: ## reseed + reset runtime toggles (calls the admin endpoint inside the container)
	$(COMPOSE) exec backend python -m app.demo_reset

test: test-backend test-frontend

test-backend:
	cd backend && uv run pytest

test-frontend:
	cd frontend && npm run typecheck && npm run lint

test-e2e:
	cd frontend && npx playwright test

eval:
	cd backend && uv run python ../eval/run_eval.py

eval-mock:
	cd backend && uv run python ../eval/run_eval.py --mock

db:
	$(COMPOSE) up -d --wait db

# Local runs talk to the dockerized Postgres on localhost (overrides the in-compose db hostname from .env).
backend: export DATABASE_URL = postgresql+psycopg://snapfix:snapfix@localhost:5432/snapfix
backend:
	cd backend && uv run alembic upgrade head && uv run python -m app.seed.generate --if-empty && uv run uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm install && npm run dev
