COMPOSE = docker compose -f infra/docker-compose.yml
.DEFAULT_GOAL := help

.PHONY: help env preflight build up down logs migrate test test-api test-ui lint fmt ci vapid-keys \
        seed seed-where seed-wallet purge-demo ingest-ntad ingest-tpims ingest-osm osm-extract repair-scales \
        repair-fuel repair-contact repair-duplicates osm-publish ingest-remote ui-layout ui-layout-only

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

# AI-CONTEXT: the PWA check (§23 entry 143). Builds, previews and drives a real browser
# offline — the only thing that proves the shell cache exists. Not part of `ui-layout`:
# it needs the built output, and the dev server deliberately ships no service worker.
ui-pwa: env
	$(COMPOSE) run --rm --entrypoint sh ui -c "npx --yes playwright install --with-deps chromium >/dev/null 2>&1 || npx --yes playwright install chromium; npx vite build && npx playwright test --config=playwright.pwa.config.js"

# AI-CONTEXT: the image pipeline in a REAL browser. `prepareImage` falls back to the
# original blob whenever the browser cannot downscale, which is correct and silent —
# happy-dom has no `OffscreenCanvas` or `createImageBitmap`, so every vitest upload
# assertion exercises the passthrough and would stay green if the downscale never ran.
# Same argument as ui-pwa: a manifest check that reads the manifest is how `"icons": []`
# shipped. Needs the dev server, which it brings up itself.
ui-image: env
	$(COMPOSE) up -d ui
	$(COMPOSE) run --rm --entrypoint sh ui -c "npx --yes playwright install --with-deps chromium >/dev/null 2>&1 || npx --yes playwright install chromium; npx playwright test --config=playwright.image.config.js"

# preflight runs FIRST, while everything is still down; ui-layout then brings up the
# one service it needs. Order matters — reversing them puts the port check after the
# thing that binds the port.
ci: env preflight lint test ui-layout ui-pwa ui-image

# --- Real POI data (PRD §12) — live pulls only, never in CI ---
# Dev seed is OFF by default; this forces it on for local field-testing.
# Plants three "DEV —" facilities (shipper, truck stop, bookable yard) around a point:
#   make seed ORIGIN=27.9506,-82.4572
# ORIGIN is a short alias for DEV_SEED_ORIGIN, which still works. The alias exists
# because this is typed beside a browser's spoofed coordinates, and the long name was
# long enough that the documented invocation was the raw `docker compose run` form.
ORIGIN ?= $(DEV_SEED_ORIGIN)
seed:
	$(COMPOSE) exec -e DEV_SEED=1 -e DEV_SEED_ORIGIN="$(ORIGIN)" api python -m scripts.seed_demo

# WHERE did I seed? The env was not self-describing, and that made the whole stop
# auto-pilot unwalkable: a browser spoofed to Tampa against pins seeded around Madison
# shows an empty map, with both halves working exactly as built. Prints the ORIGIN to
# paste into DevTools Sensors, each DEV facility's distance from it, and the geofence
# radius an EXIT has to clear.
seed-where:
	$(COMPOSE) exec api python -m scripts.seed_where

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

# AI-CONTEXT: M14-FR2 — ONE REAL POLL, BY HAND, against the real provider.
#
# The F-01 lesson is the whole reason this exists: F8 recorded every detention notice as
# sent while every one went to a container, and the suite stayed green because it asserted
# against the gateway it faked. A connector is that shape with a different third party. So
# a connector ships with an end-to-end proof against the REAL provider, observed, before
# its flag is eligible — and this target is how that observation happens.
#
# Never in CI. Needs a real pasted key and M14_CONNECTOR_KEY on the box.
#   make m14-poll-once FLEET=<fleet_uuid>
m14-poll-once:
	$(COMPOSE) exec api python -m scripts.m14_poll_once

# AI-CONTEXT: STEP 4 of the M14 kickoff — prove geofence events fire from ELD pings.
# The kickoff is explicit that a green unit test is not this: it drives the REAL F3
# evaluator over fake-provider breadcrumbs walking into the seeded Tampa DEV shipper, on a
# stop armed through the existing rate-con path, and prints the event rows. Leaves nothing
# behind (rolls back). Its output belongs in the handoff.
m14-prove:
	$(COMPOSE) exec api python -m scripts.m14_prove_events

# AI-CONTEXT: the 15-minute pilot path (M14 slice 1). Guided, one step at a time, run on
# a phone call: paste key -> encrypted connector -> list the fleet's vehicles -> map each
# to a driver -> one real poll -> where it stands. Chosen over a portal surface because a
# vehicle->driver mapping needs a two-column picker that does not exist, and §22.2 does
# not let a session invent a component pattern. The key is never echoed after paste.
#   make m14-onboard FLEET=<uuid> [KEY=<pasted>]
m14-onboard:
	$(COMPOSE) exec api python -m scripts.m14_onboard

# AI-CONTEXT: E2-FR2's validation, one command. Ground truth per stop with a REQUIRED
# source; a source naming the provider is refused in code, because Motive validating
# Motive proves only that the poller copies faithfully. Output pastes into
# docs/validation/m14-slice1.md.
#   make m14-validate FLEET=<uuid> [FILE=ground-truth.csv]
m14-validate:
	$(COMPOSE) exec api python -m scripts.m14_validate

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

# A5: promote phone/opening_hours out of the stored osm_tags blob for facilities
# ingested before the adapter read them. DRY_RUN=0 applies.
repair-contact:
	$(COMPOSE) exec api python -m scripts.repair_contact

# AI-CONTEXT: the durable home for an ingest source. A deploy ships CODE — `api/data`
# is excluded from the bundle — so an extract copied into the api container evaporates
# on the next deploy, and one copied to /tmp on the host evaporates on the next VM
# restart. Both happened. The bucket is the copy that survives; the container's is
# disposable and treated that way.
osm-publish:
	@test -f api/data/osm/$(NAME).geojson || (echo "no api/data/osm/$(NAME).geojson — run osm-extract first"; exit 1)
	gzip -c api/data/osm/$(NAME).geojson > /tmp/$(NAME).geojson.gz
	gcloud storage cp /tmp/$(NAME).geojson.gz gs://haulmeter-sources/osm/$(NAME).geojson.gz
	@rm -f /tmp/$(NAME).geojson.gz
	@echo "published gs://haulmeter-sources/osm/$(NAME).geojson.gz"

# pull that extract onto the DEPLOYED box and ingest it, then print the snapshot row
# so what the box is running is answerable (A12 req 3)
ingest-remote:
	@bash scripts/ingest_remote.sh $(NAME)

# A9 §5: merge the duplicates the OLD geohash blocking missed — "Flying J Travel
# Center" twice, 3 m apart, because a cell boundary ran between them. DRY_RUN=0 applies.
repair-duplicates:
	$(COMPOSE) exec api python -m scripts.repair_duplicates

# OSM extract: download a Geofabrik state pbf (host curl), then osmium-filter +
# export truck-relevant features in a container. Output -> api/data/osm/ (gitignored).
#
# The tag list is RENDERED from the ingest rules (scripts/osm_filter_args.py), never
# written here. A hand-kept copy lived in this recipe and drifted from the rules until
# six of the eight service rules were starved of the tags they read — no tire shop or
# repair yard could enter the registry by any path. Do not inline the tags again.
# A9 §2: "Batch by Geofabrik region rather than by state — four downloads instead of
# 51." A region lives one path level up from a state (north-america/us-midwest vs
# north-america/us/wisconsin), so NAME carries whichever you asked for and GEO_PATH
# resolves it. `make osm-extract STATE=wisconsin` and `make osm-extract REGION=us-midwest`
# both work, and everything downstream — the rendered tag filter, osm-publish,
# ingest-remote — is identical either way.
NAME = $(if $(REGION),$(REGION),$(STATE))
GEO_PATH = $(if $(REGION),$(REGION),us/$(STATE))

osm-extract:
	mkdir -p api/data/osm
	curl -fSL -o api/data/osm/$(NAME).osm.pbf \
	  https://download.geofabrik.de/north-america/$(GEO_PATH)-latest.osm.pbf
	TAGS="$$($(COMPOSE) run --rm --no-deps -T api python -m scripts.osm_filter_args)"; \
	test -n "$$TAGS" || (echo "osm_filter_args produced nothing — refusing to extract" && exit 1); \
	docker run --rm -v "$(PWD)/api/data/osm:/data" $(OSMIUM_IMAGE) sh -c "\
	  apt-get update -qq && apt-get install -y -qq --no-install-recommends osmium-tool >/dev/null && \
	  osmium tags-filter /data/$(NAME).osm.pbf $$TAGS \
	    -o /data/$(NAME)-filtered.osm.pbf --overwrite && \
	  osmium export /data/$(NAME)-filtered.osm.pbf -o /data/$(NAME).geojson --overwrite"
	@echo "wrote api/data/osm/$(NAME).geojson"
