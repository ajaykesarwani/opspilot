.PHONY: install lint format test test-integration eval up down logs demo load-test

COMPOSE = docker compose -f infra/docker-compose.yml

install:
	uv sync --frozen
	cd apps/frontend && npm ci

lint:
	uv run ruff check .
	uv run ruff format --check .
	cd apps/frontend && npm run lint

format:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest -m "not integration"

test-integration:  ## needs: $(COMPOSE) up -d postgres
	REQUIRE_DB_TESTS=1 uv run pytest -m integration

eval:
	uv run python services/evaluation/opspilot_evaluation/run_eval.py --check

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api worker

demo:
	uv run python scripts/demo.py

load-test:
	uv run python scripts/load_test.py
