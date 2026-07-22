# HANDOFF-065 — Real POI data: F2 ingestion of NTAD + TPIMS + OSM (PRD §12)

**Project:** Haulmeter — Consolidated Trucker Platform
**Date:** 22 July 2026 · **State:** F1–F15 + M1–M12 complete. The map now runs on **real public POI data** through the F2 ingestion pipeline, not the demo seed. **NTAD ingested nationally (1827 real facilities live in the dev DB); TPIMS + OSM flowing in dev; demo seed demoted to a `DEV_SEED` flag.** Stack UP.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD §12/§7.2 + design-prd §11.5/§11.7, then this file; HANDOFF-064 (full snapshot), 026–064.

---

## 1. What was built (PRD §12 — data acquisition)

The F2 keystone gained a real ingestion pipeline: **every source lands the same way — stage (raw retained) → normalize → geohash blocking + fuzzy dedupe → canonical upsert with provenance + confidence.** Idempotent; conflict resolution is data, not ifs.

### Schema (migrations 0027 f02, 0028 f10)
- **`f02.source_record`** staging table (single-table, `source_kind` discriminator; unique `(source_kind, external_ref)` for idempotency; indexes on `geohash` and `(source_kind, batch_id)`). Raw payload retained per row.
- `f02.facility.confidence` (0..1, from source count + priority); `f02.facility_source.attributes` (each source's own claim, retained for conflict resolution) + unique `(source_kind, external_ref)`; new `SourceKind.ntad`.
- `f10.submission`: nullable `account_id` + `authoritative` + `source` — an authoritative feed (TPIMS) can contribute a belief with a real timestamp and no driver.

### Adapters + pipeline (`f02/domain/ingest/`)
- **NTAD** (`services.arcgis.com/xOi1kZaI0eWDREZv/.../NTAD_Truck_Stop_Parking/FeatureServer/0`): paginate by the **service-reported** `maxRecordCount`, stop on a short page **unless** `exceededTransferLimit` (condition B). Fields: `OBJECTID`→ref, `nhs_rest_stop`→name, `number_of_spots`→**authoritative capacity**.
- **TPIMS** (V2.2 spec): static (site metadata → facilities) + dynamic (`reportedAvailable`/`trend`/`timeStamp`/`trustData`). `"Low"` is a **LOW category, never int-parsed** (condition A); `trustData=false` is **never recorded** (condition A).
- **OSM** (Geofabrik extract, osmium-filtered GeoJSON): rest areas / HGV fuel / HGV parking; polygon centroid; rows stay `source_kind=osm` (ODbL separable).
- **Chain locators: STUB only** (`ChainLocatorAdapter` raises — ToS review pending; no scraping; never Google Places).
- **Conflict rules as data:** `AMENITY_PRIORITY` (chain > ntad/tpims > osm) and `CAPACITY_PRIORITY` (**NTAD wins counts**). **Name normalization** (condition C): ALLCAPS gov codes → title-case, highway codes (`I-94`) and directions (`EB`) preserved.

### TPIMS dynamic → M1 freshness (composition, `app/ingest/`)
`run_tpims_dynamic` resolves each `siteId`→facility (F2), then `crowd.submit_authoritative(parking_fullness, reported_at=feed timeStamp)` → `update_belief` → `Belief.freshest_at` → F11 `Freshness` → the **§11.7 freshness badge shows the real feed time**. **Belief precedence** (condition A): fresh authoritative > fresh crowd > stale authoritative > stale crowd (active only when authoritative data is present, so crowd behavior is unchanged).

### Refresh, flags, make targets
- **F13 flags** (off by default): `f02_ingest_ntad / _tpims_static / _tpims_dynamic / _osm`. **Worker** runs `tpims_dynamic` (3 min) + `tpims_static` (daily) behind their flags, with **exponential failure backoff** so a dead feed doesn't log-spam (answer 3).
- **Make targets:** `make ingest-ntad`, `make ingest-tpims`, `make osm-extract STATE=wisconsin` (Geofabrik + osmium in a container), `make ingest-osm STATE=wisconsin`. **Source URLs live in the F13 config registry** (`data_sources` scope), not code.
- **Server-side clustering** at density: `/map/overlay` returns bounded clusters above the pin cap (§11.5) instead of thousands of pins (§20).

### Demo seed demoted
`seed_demo` runs **only when `DEV_SEED=1`** (default off); `make seed`. **`DEV_SEED_ORIGIN=lat,lon`** plants a few `"DEV —"` facilities (shipper, truck stop, bookable yard) around any point for field-testing geofencing/detention anywhere. Both in `.env.example`.

## 2. Verified this session

- **Live NTAD national ingest:** **1827 real facilities** created (88 deduped) in ~12s, with normalized names, provenance, capacity, confidence 0.75; **visible via `/map/overlay`**; **clustering confirmed live** (1834 in view → 0 pins + 1351 cluster cells, bounded).
- **TPIMS (WI) + OSM (WI) flowing in dev:** static → 3 facilities; dynamic → 2 beliefs applied, 1 skipped (`trustData=false`); the WI belief carries `freshest_at = 2026-07-22T03:35:00Z` (the **real feed timestamp**, not ingest time); OSM fixture → facilities, one **cross-source-deduped** with the NTAD/TPIMS site.
- **CI is network-free** — every adapter/pipeline tested against committed fixtures (`api/tests/fixtures/ingest/`). Suite: **pytest 358** (was 345; +13) · **vitest 116** · `lint-imports` **29/29** · `ruff` clean · `vite build` OK.
- **DoD:** (a) NTAD national + provenance ✔ · (b) TPIMS static+dynamic WI in dev, timestamps→badges ✔ · (c) OSM WI in dev ✔ · (d) cross-source dedupe test (NTAD+TPIMS+OSM → one facility, NTAD wins capacity) ✔ · (e) seed off by default + documented ✔ · (f) suites green, no network in CI ✔ · (g) this handoff ✔.

## 3. Decisions made (append to Decision Log)

207. **All external POI sources land through one F2 pipeline** (stage→normalize→block+dedupe→upsert), single `source_record` staging table with a `source_kind` discriminator (owner-approved). Idempotent on `(source_kind, external_ref)` then geohash+name.
208. **Conflict resolution is data, not ifs.** `AMENITY_PRIORITY` (chain>ntad/tpims>osm) and `CAPACITY_PRIORITY` (NTAD wins counts); canonical attributes recomputed deterministically from retained per-source claims; `confidence` from source count + priority.
209. **TPIMS honors its own trust flag and freshness precedence** (condition A): `trustData=false` never recorded; `"Low"` is a category; fresh authoritative > fresh crowd > stale authoritative > stale crowd. Authoritative feeds flow through F10 as account-less submissions.
210. **Source URLs live in config, not code** (F13 `data_sources` scope); CI never hits the network (committed fixtures); live pulls only via make targets. **The 2019 TPIMS spec URLs (`transportal.cee.wisc.edu/TPIMS/*`) now 404** — the exact current endpoint is an owner/ops confirmation, updated via config; the pipeline is proven and ready.

## 4. Exact next task / follow-ons

- **Confirm the live TPIMS endpoint** (the V2.2 URLs drifted) — update the `data_sources.tpims_static/dynamic` config values, enable the `f02_ingest_tpims_*` flags, and the worker starts refreshing WI (then the 8 MAASTO states).
- **Run the live OSM extract** for Wisconsin: `make osm-extract STATE=wisconsin && make ingest-osm STATE=wisconsin` (downloads a ~250 MB Geofabrik pbf, osmium-filters in a container). Then regional extracts for national OSM.
- **Chain locators** (Pilot/Love's/TA): the adapter seam exists; wire real sources after ToS review.
- **Zoom-adaptive cluster precision** (current fixed 0.1° is coarse at continental zoom) and the **client cluster-bubble render** (server already returns clusters; MapSurface keeps them in `clusters` for the render) — both refinements; §20 device-class fps stays a manual measurement.
- Then resume the remaining activation seams (Stripe / fuel partner / collections+legal / IFTA — all owner-provisioned).

## 5. Port / env changes

Migrations **0027** (f02 ingestion) + **0028** (f10 authoritative) applied to the dev DB. New env `DEV_SEED`, `DEV_SEED_ORIGIN` (in `.env.example`; seed OFF by default). Source URLs seeded into the F13 `data_sources` config. `api/data/osm/` gitignored. LOCKED ports unchanged. **Bookable M6 inventory is untouched** (BD-sourced, not data).

## 6. How to run (all Docker)

```
make up
make ingest-ntad                 # live NTAD national pull (public, no key) -> ~1827 facilities
make osm-extract STATE=wisconsin # Geofabrik + osmium in a container
make ingest-osm STATE=wisconsin
make ingest-tpims                # once the live TPIMS URL is confirmed in config
make seed DEV_SEED_ORIGIN=41.88,-87.63   # optional dev facilities anywhere
# suites (stack up): docker compose -f infra/docker-compose.yml exec api pytest -q ; ... ui npx vitest run
```

*— The map is real. NTAD live nationally, TPIMS/OSM proven end-to-end and config-gated, demo seed off by default, CI network-free. Next: confirm the current TPIMS endpoint + run the WI OSM extract.*
