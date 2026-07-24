# HANDOFF-069 — Live data + honesty pass (viewport map · fuel prices · EIA · TPIMS-IL · crowd integrity)

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 24 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).
**State in one line:** F1–F15 + M1–M12 complete; the map is **viewport-driven over real national
data**, fuel stations show **honestly-labeled prices** (network net / crowd / EIA regional estimate),
and **two live feeds are ON** — EIA weekly diesel + TPIMS Illinois real-time parking.

**Read order each session:** `HANDOFF.md` (Session 0) → PRD §6/§12/§8.7 → design-prd §11.2/§11.5/§11.7 →
this file → HANDOFF-068 (live-data activation), 067 (fuel), 066 (viewport map), 065 (ingestion), 064 (snapshot).

---

## 0. Current data state (dev DB, live)

| Thing | Value |
|---|---|
| Facilities | **4154** — OSM 2321 · NTAD 1827 · TPIMS 54 · admin/DEV_SEED 11 |
| EIA regional baseline | **6 regions**, week_of **2026-07-20** (PADD1 $5.19 · PADD2 $4.99 · PADD3 $4.94 · PADD4 $4.93 · PADD5 $5.88 · US $5.13) |
| TPIMS parking beliefs | 17 (IL feed, feed-timestamped) |
| Ingest flags ON | `m07_ingest_eia` (weekly) · `f02_ingest_tpims_static` (daily) · `f02_ingest_tpims_dynamic` (~3 min) |
| Ingest flags off (manual make targets) | `f02_ingest_ntad` · `f02_ingest_osm` |
| Tests | **pytest 381 · vitest 129 · ruff clean · import-linter 29/29** |

---

## 1. What this session built (newest first)

### F10 crowd integrity — count distinct drivers, not resubmissions (`c1cd2c3`, §11.7)
One driver re-tapping "Report status" inflated both the belief weight and the "N drivers" count
(3 reports → "3 drivers"). `aggregate_belief` now keeps **each contributor's freshest submission**
before scoring (`_latest_per_contributor`): a driver keyed by account, a feed by source, else the row.
So one driver counts once (their latest opinion wins), distinct drivers still accrue, a feed's repeated
readings collapse to its latest. Account-less test rows stay distinct → precedence semantics unchanged.

### Honest fuel-price labels (`9a90946`)
"net" means AFTER a network discount — but crowd/regional prices were also labeled "net/gal", making an
EIA estimate look like a precise per-station price (the "why are they all the same?" confusion). Now:
network → `$3.94 net/gal · save 25¢`; crowd → `$3.69/gal · 40m · 3 drivers`; regional →
`~$4.99 /gal · regional avg · wk of Jul 20`. Same fix on the price-report sheet.

### TPIMS/DOT freshness attribution (`f6f8e85`, §11.7)
The badge read "7m · 1 driver" for an authoritative TPIMS reading. The winning parking belief carries
`source="tpims"` (absent for crowd), now threaded F11 `Freshness.source` → overlay pin → card;
`freshnessLabel` renders **"16m · official feed"** (localized ×6) for a feed reading, never "drivers".
If a fresher crowd report wins, it correctly reverts to drivers.

### Live data activation — EIA weekly + TPIMS Illinois (`f4dcb71`, HANDOFF-068)
- **EIA (M1-FR5):** HTTP in `m7.fetch_eia()`; weekly worker job `eia_regional` (flag `m07_ingest_eia`,
  604800s, backoff; EIA publishes Mondays ~5pm ET; idempotent upsert). `EIA_API_KEY` in `infra/.env`
  (api+worker recreated to load it). Card labels the **EIA period** ("wk of Jul 20"), not ingest time.
- **TPIMS-IL:** config → Travel Midwest IL feed; adapter hardened from **real IL rows** —
  `reportedAvailable:"Unknown"` → no reading (never int-parsed), `trend:"Unknown"` → null, `open:null`
  tolerated; `has_usable_reading` gates belief creation so **Unknown/untrusted → NO belief regardless of
  trustData**. Live ingest: static 51 → **32 created + 19 deduped** (vs NTAD); dynamic **8 applied,
  43 skipped**. Pins carry `availability` (int OR `"Low"`, never int-parsed) + `capacity` → card shows
  `1 · 12 spots` / `Low · 13 spots`.
- **KY/MN probe** (`make probe-tpims`): KY = HTTP 200 `text/html` (not spec JSON); MN = ConnectTimeout →
  **both left unconfigured**. `http://` is fetched fine by httpx.

### Fuel prices on the map — crowd + EIA baseline (`684a027` / `d9ab61f`, HANDOFF-067)
Real fuel stations were priceless (only demo seed set prices, since purged). `fuel_summary` priority:
**network feed → crowd consensus (M7-FR5) → EIA regional (indicative)**. Card shows a price for any
station + a **"Report diesel price"** action → queued `POST /fuel/confirm-price`. `seed_demo` adds a
crowd-priced "Indie Fuel Stop" (3 reports → $3.89) + get-or-create seeders (re-runnable after purge).

### Viewport-driven map overlay (`c574766`, HANDOFF-066)
`/map/overlay` was point+fixed-radius, load-only → blank map on 4000+ national facilities. Now a **bbox
is primary** (F2 `in_bbox` → F11 `overlay_pins_bbox` → M1 `map_overlay_view_bbox` with a `MAX_BBOX_DEG2`
area cap); MapCanvas opens continental, emits `bounds` on load + every pan/zoom; MapSurface refetches
**debounced ~300ms with AbortController**. Migration 0029 `is_dev`; `make purge-demo` removed 51 demo
facilities + 39 test loads. Tab title → **Haulmeter**.

## 2. Live verification (real Mapbox token, headless Chromium, 360×800)

- **Map:** WI 49 pins · IL 25 pins · continental 126 cluster bubbles (§11.5).
- **Fuel card:** `~$4.99 /gal · regional avg · wk of Jul 20` + "Report diesel price".
- **TPIMS card (IL I-74, Spoon River WB):** `Some · 1 · 12 spots · 16m · official feed`.
- Method: a temporary `window.__hmMap` camera seam to script `jumpTo`, **added then reverted every time**
  (tree always left clean). See §6 if you need to re-verify.

## 3. Live feeds — how to operate

| Feed | Command | Cadence / notes |
|---|---|---|
| EIA regional diesel | `make ingest-eia` (or worker `eia_regional`) | Weekly; needs `EIA_API_KEY` in `infra/.env`. `make ingest-eia FIXTURE=tests/fixtures/ingest/eia_diesel.json` for a key-free pull. |
| TPIMS IL dynamic | worker `tpims_dynamic` (flag ON) | ~3 min, backoff. `data_sources.tpims_dynamic` = Travel Midwest IL. |
| TPIMS IL static | worker `tpims_static` (flag ON) | Daily. Dedupes against NTAD. |
| KY/MN probe | `make probe-tpims` | Re-check; config only if it reports LIVE spec-shaped JSON. |
| NTAD / OSM | `make ingest-ntad` / `make ingest-osm STATE=…` | Manual, national/state pulls. |

**Never commit `infra/.env`.** `env_file` is read at container-create — after editing `.env`, run
`docker compose -f infra/docker-compose.yml up -d api worker` so containers pick up new vars.

## 4. Decision Log (PRD §17 / design-prd §23)

1. **Fuel-price source = crowd + EIA baseline** (owner decision; PRD §17 open-Q#4). Commercial per-station
   feed (OPIS) still deferred. Network net-price + pump-code stays partner-gated (PRD §471).
2. **"net" is network-only.** Crowd/regional prices read plain `/gal`; a regional figure is prefixed `~`
   and captioned `regional avg · wk of <date>` — an estimate, never presented as a confirmed net price.
3. **Freshness attribution follows the winning reading's provenance** — feed → "official feed", crowd →
   "N drivers" (distinct drivers only). §11.7 honesty.
4. **TPIMS source = Travel Midwest IL** (WI transportal dead). KY (HTML) / MN (unreachable) not activated.
5. **EIA cadence = weekly interval** (no cron in the worker; weekly + idempotent upsert makes Monday
   alignment unnecessary).
6. **Card enrichments composed from existing tokens** (EIA week, TPIMS `<avail> · <cap> spots`,
   feed-source label) — no new color/type/spacing/nav/notification, so no §23 escalation.

## 5. Exact next tasks (owner's call — nothing is blocking)

1. **Differentiate in-region fuel prices with real data.** The EIA baseline is uniform within a PADD by
   design; real per-station prices only appear via crowd reports or a feed. Options: (a) make a price-less
   station's card lead with "Be the first to report the price here" to pull crowd data; (b) scope a
   commercial feed (OPIS/GasBuddy) — cost + BD decision. Both are product calls.
2. **KY/MN TPIMS** need a different endpoint (KY serves HTML; MN unreachable) — re-probe / discovery.
3. **Expand TPIMS beyond IL** as MAASTO state feeds verify (IN/IA/KS/KY/MI/MN/OH/WI) — same adapter, add
   config URLs after `make probe-tpims` confirms each.
4. **Points-farming guard (optional):** `submit()` still awards points per submission; the *belief* is now
   spam-proof, but a driver could still farm points by re-reporting. Consider a per-facility/per-signal
   award cooldown if points become a live incentive.
5. Resume the PRD §6 module worklist wherever HANDOFF-064 left off, if pivoting back to feature build.

## 6. Working rules (unchanged — non-negotiable)

Docker-only (dev = CI parity) · **local commits only, NEVER push** · plan-first for non-trivial work ·
**tests with every change** (no FR without a test; red CI blocks everything) · **live pulls never in CI**
(fixtures drive tests) · **AI-CONTEXT comments only** · maximum modularity (import-linter authoritative:
core < foundation < modules, `.public` only) · **design-prd governs ALL UI** (mobile-first 360dp, tokens
only, §22.3 DoD: six locales, offline, DRIVING-state, a11y) · session ends by writing the next HANDOFF.
Commit messages end with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

Browser re-verification uses a temporary `window.__hmMap` seam in `MapCanvas.vue` (after `new mapboxgl.Map`)
to script `map.jumpTo(...)` from Playwright, then `git checkout -- ui/src/core/components/MapCanvas.vue`.
Playwright: `~/.npm/_npx/.../node_modules` (symlink as `node_modules` in scratch), chromium-1140 cached.
Gotcha: never return the Mapbox `map` object from `page.evaluate` (circular → hangs); wrap in `{ }`.

## 7. Commits this session (local only, on `main`)

```
9a90946 Honest fuel-price labels: "net" is network-only, estimates say "/gal"
c1cd2c3 Count distinct drivers, not resubmissions, in belief aggregation (§11.7)
f6f8e85 Attribute TPIMS/DOT freshness to the feed, not "N drivers" (§11.7)
f4dcb71 Live data: EIA weekly diesel baseline + TPIMS real-time (Illinois)
d9ab61f seed_demo: crowd-priced fuel station (M7-FR5 demo) + re-runnable seeders
684a027 M7/M1: fuel prices on the map — crowd reporting + EIA regional baseline
b57517b docs: HANDOFF-066 — record live browser pass results
c574766 F11/M1: viewport-driven map overlay (fixes empty map on real data)
```

## 8. Key files touched (by area)

```
MAP        api/app/{foundation/f02_facility,foundation/f11_map,modules/m01_map}/… + api/app/api/m01_map.py
           ui/src/core/components/MapCanvas.vue · ui/src/surfaces/MapSurface.vue · ui/src/core/api.js
FUEL       api/app/modules/m07_fuel/domain/{models,service}.py (fetch_eia/parse_eia/region_for/fuel_summary)
           ui/src/core/components/{FacilityCard,PriceReportSheet}.vue
CROWD      api/app/foundation/f10_crowd/domain/service.py (_latest_per_contributor)
INGEST     api/app/ingest/{flags,runners,sources}.py · api/app/worker.py
           api/app/foundation/f02_facility/domain/ingest/adapters.py (Unknown/trend hardening)
SCRIPTS    api/scripts/{ingest_eia,probe_tpims,purge_demo,seed_demo}.py · Makefile
MIGRATIONS 0029 f02.is_dev · 0030 m07.regional_fuel_price
I18N       ui/src/core/i18n/*.json (+ fuel.week_of, facility.spots, freshness.feed, report/price keys ×6)
FIXTURES   api/tests/fixtures/ingest/{eia_diesel,tpims_il_static,tpims_il_dynamic}.json
```
