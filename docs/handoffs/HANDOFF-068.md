# HANDOFF-068 — Live data activation: EIA diesel baseline (weekly) + TPIMS real-time (Illinois)

**Project:** Haulmeter — Consolidated Trucker Platform
**Date:** 23 July 2026 · **State:** F1–F15 + M1–M12 complete. Two live feeds are now
ON: **EIA** weekly regional diesel (real prices, week-dated) and **TPIMS Illinois**
real-time parking availability (worker-refreshed, feed-timestamped). Stack UP.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD §12/§8.7 + design-prd
§11.5/§11.7, then this file; HANDOFF-067 (fuel prices), 066 (viewport map), 065, 064.

---

## 1. Part A — EIA live weekly baseline (M1-FR5)

- **Live pull ON.** `EIA_API_KEY` set in `infra/.env` (api+worker recreated to load it).
  `make ingest-eia` replaced the fixture with real weekly prices — **6 regions, week_of
  2026-07-20**: PADD1 $5.19 · PADD2 $4.99 · PADD3 $4.94 · PADD4 $4.93 · PADD5 $5.88 · US $5.13.
- **HTTP moved into `m7.fetch_eia()`** so the script and the worker share one code path.
- **Weekly worker job** `eia_regional` (flag `m07_ingest_eia`, **ON**): interval 604800s;
  EIA publishes **Mondays ~5pm ET**; upsert is idempotent so alignment is immaterial. Same
  exponential backoff as TPIMS. Worker ran it live at enable: `eia_regional ok: {'regions': 6}`.
  Fixture-based test (`test_eia_runner_upserts_regional_prices_from_fixture`); live pull never in CI.
- **Card freshness honesty (§11.7):** the regional label now carries the **EIA period**, e.g.
  `regional avg · wk of Jul 20`, from the badge `as_of` (week_of) — not ingest time.

## 2. Part B — TPIMS Illinois (verified live)

- **Config → IL** (`data_sources`, overwrote the dead WI transportal URLs):
  `tpims_dynamic = https://truckparking.travelmidwest.com/TPIMS_Dynamic.json`, `…/TPIMS_Static.json`.
- **Adapter hardening from REAL IL rows** (`adapters.py`): `reportedAvailable:"Unknown"` → no reading
  (never int-parsed, `parse_available`); `trend:"Unknown"` → null (`_parse_trend`); `open:null` → open.
  New `has_usable_reading(status)` — a belief needs a known availability OR a closed station; **"Unknown"
  on an open site yields NO belief regardless of trustData** (`run_tpims_dynamic` skips it).
- **Live ingest counts:** IL static **51 staged → 32 created + 19 deduped** (matched against NTAD
  nationals). IL dynamic **8 beliefs applied, 43 skipped** (Unknown/untrusted) — matches the live
  feed (only 8 of 51 rows are trusted with a real reading).
- **Flags ON:** `f02_ingest_tpims_static` (daily) + `f02_ingest_tpims_dynamic` (~3 min); the worker
  refreshes on cadence with backoff.
- **KY/MN probe** (`make probe-tpims`, in-container, never CI) — **recorded:**
  - KY `http://www.trimarc.org/dat/tpims/TPIMS_{Dynamic,Static}.json` → **HTTP 200 but `text/html`**
    (not spec JSON) → **not configured**.
  - MN `http://iris.dot.state.mn.us/iris/TPIMS_{dynamic,static}` → **ConnectTimeout (unreachable)** → **not configured**.
  - Confirmed `http://` is fetched by httpx (KY returned 200 over http); the "allowlist" is the
    `data_sources` config registry (only admin-set URLs are fetched).
- **UI availability (condition A / §11.7):** pins now carry `availability` (int count OR the `"Low"`
  category, **never int-parsed**) + `capacity`; the card shows a caption like `1 · 12 spots` or
  `Low · 13 spots`, composed from existing caption tokens.

## 3. Live browser verify (360×800, real token, over IL I-74)

Opened **Spoon River WB** (real IL TPIMS site): status pill **Some**, availability **`1 · 12 spots`**
(count + capacity, never Low-as-number), freshness **`7m`** derived from the **feed timestamp**
(08:59:17Z), not ingest time. (Temp `window.__hmMap` camera seam used, then **reverted** — tree clean.)

## 4. Tests / quality

- **pytest 379** (fixture EIA-runner job path; IL Unknown/untrusted → no belief; crowd-report-over-Unknown;
  IL adapter hardening; F11 availability serialization). **vitest 128** (card: EIA `wk of` label;
  TPIMS `Low`/count + capacity; feed-timestamp badge). **ruff clean · import-linter 29/29.**
- New fixtures **built from real IL feed rows**: `tpims_il_static.json` (5 sites), `tpims_il_dynamic.json`
  (2 usable → full+some, 3 no-belief incl. a derived trusted-Unknown guard case + open=null).

## 5. Decision Log (PRD §17 / design-prd §23)

1. **TPIMS source = Travel Midwest IL feed** (WI transportal was dead, HANDOFF-065). Stored in
   `data_sources` config; code DEFAULTS updated to match.
2. **EIA cadence = weekly interval** (604800s), not weekday-pinned — the simple worker scheduler has no
   cron; EIA is weekly + upsert-idempotent, so exact Monday alignment is unnecessary. Recorded in the flag desc.
3. **KY/MN not activated** (KY serves HTML, MN unreachable). Re-probe with `make probe-tpims`; config only if LIVE.
4. **Card enrichment** (EIA `wk of <date>`; TPIMS `<avail> · <cap> spots`) composed from existing type/color
   tokens — no new component/color/type/nav/notification (design-prd §22, no §23 escalation needed).

## 6. Known follow-up (not blocking)

- **Freshness attribution wording:** the badge reads `7m · 1 driver` even for an authoritative TPIMS
  feed. The **timestamp is correct** (feed time, §11.7); only the "driver" noun is off for a DOT source.
  Fix = thread `belief.authoritative`/`source` → pin → a feed-aware `freshnessLabel` (e.g. `· IDOT`).
- **KY** likely needs a different path/host (returns an HTML page); **MN** needs a reachable endpoint or allowlisting.

## 7. Rules (unchanged)

Docker-only · **local commits only, never push** · tests with every change · **live pulls never in CI**
(fixtures drive tests) · AI-CONTEXT comments only · design-prd governs UI. Commit messages end with
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## 8. Key files

```
api/app/modules/m07_fuel/domain/service.py   fetch_eia + EIA_URL/DUOAREAS + MissingEIAKey
api/app/ingest/{flags,runners,sources}.py    FLAG_EIA, run_eia, IL TPIMS config, has_usable_reading skip
api/app/worker.py                            eia_regional weekly job
api/app/foundation/f02_facility/domain/ingest/adapters.py   Unknown/trend hardening + has_usable_reading
api/app/foundation/f11_map/domain/service.py + api/app/api/m01_map.py   pin availability + capacity
api/scripts/{ingest_eia,probe_tpims}.py · Makefile (probe-tpims)
api/tests/fixtures/ingest/tpims_il_{static,dynamic}.json   real IL rows
ui/src/core/components/FacilityCard.vue      EIA week label + TPIMS availability caption
ui/src/core/i18n/*.json                      +2 keys (fuel.week_of, facility.spots) × 6 locales
tests: test_ingest_runners.py, test_ingest.py, ui-components.test.js
```
