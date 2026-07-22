COMPOSE = docker compose -f infra/docker-compose.yml
.DEFAULT_GOAL := help

.PHONY: help env preflight build up down logs migrate test test-api test-ui lint fmt ci \
        seed ingest-ntad ingest-tpims ingest-osm osm-extract

STATE ?= wisconsin
# osmium-tool is packaged in Debian/Ubuntu; install it in a slim base at run time
# (no dependency on a specific published osmium image).
OSMIUM_IMAGE ?= debian:stable-slim

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

# --- Real POI data (PRD §12) — live pulls only, never in CI ---
# Dev seed is OFF by default; this forces it on for local field-testing.
# Optional: DEV_SEED_ORIGIN=lat,lon plants a few "DEV —" facilities around a point.
seed:
	$(COMPOSE) exec -e DEV_SEED=1 -e DEV_SEED_ORIGIN="$(DEV_SEED_ORIGIN)" api python -m scripts.seed_demo

ingest-ntad:
	$(COMPOSE) exec api python -m scripts.ingest_ntad

ingest-tpims:
	$(COMPOSE) exec api python -m scripts.ingest_tpims

# reads api/data/osm/$(STATE).geojson (produced by `make osm-extract`)
ingest-osm:
	$(COMPOSE) exec api python -m scripts.ingest_osm /app/data/osm/$(STATE).geojson

# OSM extract: download a Geofabrik state pbf (host curl), then osmium-filter +
# export truck-relevant features in a container. Output -> api/data/osm/ (gitignored).
osm-extract:
	mkdir -p api/data/osm
	curl -fSL -o api/data/osm/$(STATE).osm.pbf \
	  https://download.geofabrik.de/north-america/us/$(STATE)-latest.osm.pbf
	docker run --rm -v "$(PWD)/api/data/osm:/data" $(OSMIUM_IMAGE) sh -c '\
	  apt-get update -qq && apt-get install -y -qq --no-install-recommends osmium-tool >/dev/null && \
	  osmium tags-filter /data/$(STATE).osm.pbf \
	    nwr/highway=rest_area,services nwr/amenity=truck_stop nwr/hgv nwr/access=hgv \
	    -o /data/$(STATE)-filtered.osm.pbf --overwrite && \
	  osmium export /data/$(STATE)-filtered.osm.pbf -o /data/$(STATE).geojson --overwrite'
	@echo "wrote api/data/osm/$(STATE).geojson"
