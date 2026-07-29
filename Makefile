COMPOSE = docker compose -f infra/docker-compose.yml
.DEFAULT_GOAL := help

.PHONY: help env preflight build up down logs migrate test test-api test-ui lint fmt ci vapid-keys \
        seed seed-wallet purge-demo ingest-ntad ingest-tpims ingest-osm osm-extract repair-scales \
        repair-fuel ui-layout ui-layout-only

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
	@echo "  ui-layout-only STATE=x   ONE layout state (~45s) — prefer this while building"

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

# AI-CONTEXT: the VAPID keypair a deployment needs for Web Push (§23 entry 111). Prints
# rather than writes: the private key is a secret and infra/.env is never generated over
# (rule 9), so the operator pastes it in deliberately. Rotating invalidates every stored
# subscription, which is why this is not run automatically by `make env`.
# scripts/ is outside the api build context, so it is mounted rather than baked in.
vapid-keys:
	@$(COMPOSE) run --rm --no-deps -v $(PWD)/scripts:/scripts api python /scripts/vapid_keys.py

lint: env
	$(COMPOSE) run --rm --no-deps api sh -c "ruff check . && lint-imports --config importlinter.ini"

fmt:
	$(COMPOSE) run --rm --no-deps api ruff format .

# AI-CONTEXT: the LAW 0 harness (design-prd §22.3). Deliberately NOT part of `make
# test`: the unit suite finishes in seconds and putting a browser on that path would
# cost the tight red-green loop. `make ci` runs both.
#
# `up -d ui` is load-bearing, and its absence made `make ci` unrunnable. The harness
# targets http://ui:9008, which only resolves while the ui SERVICE is up — but
# `compose run` replaces the container's command, so the one-off runner never starts
# vite and nothing is listening. That left the two gates mutually exclusive:
# `preflight` demands the host ports be FREE, `ui-layout` demands the dev server be
# UP, so `make ci` could not pass in either state. It failed with
# `net::ERR_NAME_NOT_RESOLVED` on all 466 checks from a cold stack, and had evidently
# never been run end to end — everyone ran `make up` and then `make ui-layout`.
ui-layout: env
	$(COMPOSE) up -d ui
	$(COMPOSE) run --rm --entrypoint sh ui -c "npx --yes playwright install --with-deps chromium >/dev/null 2>&1 || npx --yes playwright install chromium; npm run layout"

# AI-CONTEXT: RUN THIS, NOT THE FULL SWEEP, unless you have a reason.
#
# `ui-layout` is the slowest thing in the project. Running it after every edit is what
# made it feel unusable — and a check that is painful to run stops being run, which
# costs more than any assertion in it can pay back.
#
# The policy, so nobody has to rediscover it:
#   · while building a screen  -> `ui-layout-only STATE=<that screen>`  (~45 s)
#   · touched a shared token, a global stylesheet, or layout.spec itself -> full sweep
#   · before a handoff, and in `make ci` -> full sweep
# Nothing else needs the full sweep. A change to one surface cannot break another's
# geometry unless it went through something shared, and that case is named above.
#   make ui-layout-only STATE=load-calc
#   make ui-layout-only STATE="sheet-map"      # every map sheet
ui-layout-only: env
	@test -n "$(STATE)" || (echo "usage: make ui-layout-only STATE=<name or pattern>"; exit 1)
	$(COMPOSE) up -d ui
	$(COMPOSE) run --rm --entrypoint sh ui -c "npx --yes playwright install --with-deps chromium >/dev/null 2>&1 || npx --yes playwright install chromium; npx playwright test -g '$(STATE)'"

# preflight runs FIRST, while everything is still down; ui-layout then brings up the
# one service it needs. Order matters — reversing them puts the port check after the
# thing that binds the port.
ci: env preflight lint test ui-layout

# --- Real POI data (PRD §12) — live pulls only, never in CI ---
# Dev seed is OFF by default; this forces it on for local field-testing.
# Optional: DEV_SEED_ORIGIN=lat,lon plants a few "DEV —" facilities around a point.
seed:
	$(COMPOSE) exec -e DEV_SEED=1 -e DEV_SEED_ORIGIN="$(DEV_SEED_ORIGIN)" api python -m scripts.seed_demo

# put a realistic document wallet on an account so the Docs tab has something to
# show. Defaults to the most recently registered account: `make seed-wallet`, or
# `make seed-wallet EMAIL=you@example.com`.
seed-wallet:
	$(COMPOSE) exec api python -m scripts.seed_wallet "$(EMAIL)"

# delete demo/test leftovers (admin-only facilities) from the dev DB
purge-demo:
	$(COMPOSE) exec api python -m scripts.purge_demo

ingest-ntad:
	$(COMPOSE) exec api python -m scripts.ingest_ntad

ingest-tpims:
	$(COMPOSE) exec api python -m scripts.ingest_tpims

# probe unverified TPIMS state feeds (KY/MN) — reachability + spec-shape, never CI
probe-tpims:
	$(COMPOSE) exec api python -m scripts.probe_tpims

# EIA weekly regional diesel baseline (M1-FR5). Needs EIA_API_KEY in infra/.env
# (free at eia.gov/opendata). Or pass FIXTURE=path to load a saved payload key-free.
ingest-eia:
	$(COMPOSE) exec api python -m scripts.ingest_eia $(FIXTURE)

# reads api/data/osm/$(STATE).geojson (produced by `make osm-extract`)
ingest-osm:
	$(COMPOSE) exec api python -m scripts.ingest_osm /app/data/osm/$(STATE).geojson

# one-off repair for facilities ingested before the co-located-amenity rule existed.
# Prints what it would do; DRY_RUN=0 applies. Idempotent.
repair-scales:
	$(COMPOSE) exec api python -m scripts.repair_colocated_scales

# E3.3: the same for branded service areas mis-typed as rest areas and for fuel
# islands that drew a second pin on their own truck stop. DRY_RUN=0 applies.
repair-fuel:
	$(COMPOSE) exec api python -m scripts.repair_colocated_fuel

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
	    nwr/amenity=weighbridge,weigh_station \
	    -o /data/$(STATE)-filtered.osm.pbf --overwrite && \
	  osmium export /data/$(STATE)-filtered.osm.pbf -o /data/$(STATE).geojson --overwrite'
	@echo "wrote api/data/osm/$(STATE).geojson"
