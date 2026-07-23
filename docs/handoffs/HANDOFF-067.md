# HANDOFF-067 — Fuel prices on the map (crowd + EIA regional baseline)

**Project:** Haulmeter — Consolidated Trucker Platform
**Date:** 23 July 2026 · **State:** F1–F15 + M1–M12 complete. Real fuel stations now
show a **diesel price + honest source label** and a **"Report diesel price"** action —
fixing the "gas stations show no price / only View facility" report. Prices come from
**per-station network feed → crowd consensus (M7-FR5) → EIA regional average (M1-FR5)**.
Stack UP. Dev DB: 4111 real facilities; 6 EIA regional prices loaded (from fixture).
**Read order each session:** `HANDOFF.md` (Session 0) + PRD §8.7/§12 + design-prd
§11.2/§11.7/§12.2, then this file; HANDOFF-066 (viewport map fix), 065, 064, 026–064.

---

## 1. The report & the diagnosis

"Gas stations are not showing any price info and it is showing View facility." **Not a
regression** — fuel prices only ever came from the demo seed (`set_station_pricing`),
purged in HANDOFF-066. Real OSM/NTAD stations had **zero** pricing → no `fuel_net` badge
→ card fell back to Navigate + View facility (its *designed* no-price fallback). The
crowd path (M7-FR5) was built on the backend but **had no map UI to feed it** and
`fuel_summary` never read the crowd belief back. PRD §17 open-Q#4 (feed source) — owner
chose **crowd + EIA baseline**.

## 2. What was built

**Backend — EIA regional baseline (M1-FR5)**
- Migration `0030`: `m07.regional_fuel_price` (region PK, `gross_cents_per_gal`, `week_of`).
- `m7.parse_eia` / `ingest_eia_prices` (keep freshest week/region, diesel-only, drop non-PADD),
  `region_for(lat, lon)` (coarse PADD partition, US fallback — border states approximate by design),
  `upsert_regional_price`. `scripts/ingest_eia.py` + `make ingest-eia` (live pull, or a JSON path
  key-free). `EIA_API_KEY` in `infra/.env.example` (free at eia.gov/opendata; flows via `env_file`).
  Fixture `api/tests/fixtures/ingest/eia_diesel.json`.

**Backend — `fuel_summary` priority + freshness**
- Now `fuel_summary(db, ref, lat=, lon=)`: **network feed → crowd consensus (belief `freshest_at`
  + `sample_size`) → EIA regional (`indicative`)**. Returns `{net, gross, savings, is_network,
  source, indicative, as_of, sample_size}`. `_enrich` (m01_map) passes the pin's lat/lon; the
  `fuel_net` badge carries `source`/`indicative`/`as_of`/`sample_size`.

**UI**
- `FacilityCard`: shows the price for **any** fuel station with an honest label — network savings,
  crowd `40m · N drivers` (§11.7), or `regional avg` (with a `~` on the indicative figure). Adds a
  **"Report diesel price"** action (`report-price`).
- `PriceReportSheet.vue`: glove-friendly ±1¢ stepper, seeded from the shown price, emits cents/gal.
- `MapSurface`: `reportPrice`/`submitPrice` → `api.confirmFuelPrice` → **queued** POST `/fuel/confirm-price`
  (F12 offline), then refetches the overlay. 8 new i18n keys × **6 locales** (337 each).

## 3. Tests (all green)

- **API pytest 375** (+7): `region_for` mapping; EIA parse (diesel-only, freshest week, non-PADD dropped);
  regional ingest upsert; `fuel_summary` priority (regional fallback, crowd-over-regional, none-without-loc);
  overlay badge carries the indicative regional price.
- **Vitest 125** (+4): card shows regional `~$` + "regional avg" (never "Fuel here"); crowd price + `N drivers`
  freshness; emits `report-price`; MapSurface opens the price sheet from a fuel pin and POSTs `/fuel/confirm-price`.
- **Lint** ruff clean · **import-linter 29/29**.

## 4. Live verification (real Mapbox token, headless Chromium, 360×800)

Opened a real Wisconsin fuel station's card on the GL map: **`~$3.78 net/gal · regional avg`**, a
**"Report diesel price"** pump action, Navigate primary, View facility tertiary. Overlay API for the
WI viewport returns the regional badge on all 29 fuel pins. (Temp `window.__hmMap` camera seam used to
script `jumpTo`, then **reverted** — tree clean.)

## 5. How prices come alive (operational)

- **Crowd** works now, no key: a driver taps *Report diesel price* → one confirmation forms a consensus
  that becomes a per-station `station_pricing(source=crowd)` row → the pin shows the real price + freshness,
  displacing the regional baseline.
- **EIA baseline** is loaded from the fixture in dev. For live weekly data: get a **free EIA key**
  (https://www.eia.gov/opendata/ → Register), put `EIA_API_KEY=…` in `infra/.env`, run `make ingest-eia`.
  Re-run weekly (EIA updates Mondays). Without a key the map still shows crowd prices.
- **Network feed** (real net/discount + "Fuel here" + pump code) stays partner-gated (PRD §471).

## 6. Exact next task

Owner's call — the fuel-price gap is closed. Candidates:
- Provide a **free EIA API key** so the baseline reflects live weekly regional diesel (I wired everything;
  it's one env var + `make ingest-eia`).
- **TPIMS live token** (HANDOFF-066) still blocked on registration.
- Consider seeding a couple of **crowd fuel reports** in `seed_demo` so DEV_SEED stations show a real
  per-station price (currently demo stations use network pricing).

## 7. Rules (unchanged)

Plan-first · Docker-only · **local commits only, NEVER push** · tests with every change · design-prd §22.3
DoD (mobile-first 360dp, tokens-only, 6 locales, offline, DRIVING-state, a11y) · suites in-container while
the stack is up. Commit messages end with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## 8. Key files

```
api/app/modules/m07_fuel/domain/{models,service}.py  RegionalFuelPrice + region_for/parse_eia/fuel_summary
api/app/modules/m07_fuel/public.py                   exports
api/app/api/m01_map.py                               _enrich passes lat/lon; badge source/indicative/as_of
api/migrations/versions/0030_m07_regional_fuel_price.py
api/scripts/ingest_eia.py · Makefile (ingest-eia) · infra/.env.example (EIA_API_KEY)
api/tests/fixtures/ingest/eia_diesel.json
ui/src/core/components/FacilityCard.vue              price + source label + Report diesel price
ui/src/core/components/PriceReportSheet.vue          NEW price-entry sheet
ui/src/surfaces/MapSurface.vue                       report-price flow (queued)
ui/src/core/api.js                                   confirmFuelPrice
ui/src/core/i18n/*.json                              +8 keys × 6 locales
api/tests/{modules/m07_fuel,api}/... · ui/test/ui-components.test.js   +7 API, +4 vitest
```
