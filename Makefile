COMPOSE = docker compose -f infra/docker-compose.yml
.DEFAULT_GOAL := help

.PHONY: help env preflight build up down logs migrate test test-api test-ui lint fmt ci

help:
	@echo "LONGHAUL make targets:"
	@echo "  env        copy infra/.env.example -> infra/.env if missing"
	@echo "  preflight  verify all host ports are free (fails loud with PID)"
	@echo "  up         preflight, then start the full compose stack"
	@echo "  down       stop the stack"
	@echo "  migrate    run alembic migrations in the api container"
	@echo "  test       run the full suite (api + ui) in compose"
	@echo "  lint       run ruff + import-linter in the api container"
	@echo "  ci         preflight + lint + test (compose parity with CI)"

env:
	@test -f infra/.env || (cp infra/.env.example infra/.env && echo "created infra/.env from example")

preflight:
	@bash scripts/check_ports.sh

up: env preflight
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

migrate: env
	$(COMPOSE) run --rm api alembic upgrade head

test: test-api test-ui

test-api: env
	$(COMPOSE) run --rm api pytest -q

test-ui:
	$(COMPOSE) run --rm --no-deps ui npm test --silent

lint: env
	$(COMPOSE) run --rm --no-deps api sh -c "ruff check . && lint-imports --config importlinter.ini"

fmt:
	$(COMPOSE) run --rm --no-deps api ruff format .

ci: env preflight lint test
