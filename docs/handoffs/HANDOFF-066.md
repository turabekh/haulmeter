# HANDOFF-066 — Map overlay: viewport-driven fetching (fixes empty map on real data)

**Project:** Haulmeter — Consolidated Trucker Platform
**Date:** 23 July 2026 · **State:** F1–F15 + M1–M12 complete. The map now **fetches by
viewport** (pan/zoom driven), so real national POI data renders everywhere — not just
near a hardcoded city. Dev DB has **4111 real facilities** (OSM 2321 · NTAD 1827 · TPIMS 3),
**0 demo/test leftovers, 0 test loads**. Stack UP.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD §12/§7.2 + design-prd
§11.5/§11.7, then this file; HANDOFF-065 (real-data ingestion), 064 (full snapshot), 026–064.

---

## 1. The bug (why the map looked empty)

`GET /map/overlay` was **point + fixed `radius_m=8000`**, fetched **only on load/geolocate**,
never on pan/zoom. With 4162 facilities spread nationally, the ~8 km disc around the
default center (Dallas 32.78,-96.8) caught only demo leftovers — everywhere else was blank.

## 2. The fix (5 parts, all shipped)

### Server — bbox is now the primary overlay mode
- **F2** `in_bbox(db, min_lat, min_lon, max_lat, max_lon, facility_type=None)` — `ST_MakeEnvelope` +
  `ST_Intersects`, `BBOX_QUERY_LIMIT=5000` DB ceiling (`f02_facility/domain/service.py`, exported in `public.py`).
- **F11** `overlay_pins_bbox(...)` + `_facilities_in_bbox(...)` mirror the radius path (`f11_map/domain/service.py`, exported).
- **M1** `map_overlay_view_bbox(...)` (`m01_map/domain/service.py`, exported): clusters by pin count
  (existing §11.5 logic) with precision from the **bbox span** (`_bbox_precision_deg`); **area cap
  `MAX_BBOX_DEG2=100`** forces clusters-only for continental-span viewports regardless of count.
- **Endpoint** `GET /map/overlay` (`api/m01_map.py`): accepts `min_lat/min_lon/max_lat/max_lon`
  (**primary**); `lat/lon/radius_m` still work (**secondary**, corridor/nearby); neither → **422**.

### Client — viewport-driven, debounced, abortable
- **`api.js` `fetchOverlay({bbox, lat, lon, radiusM, preset, signal})`** — bbox params when given;
  direct `fetch` with an `AbortSignal` (bypasses the offline cache; offline still falls back to fixtures).
- **`MapCanvas.vue`** — opens on the **continental US** (`US_CENTER=[-98.5,39.8]`, `US_ZOOM=3.5`), never a
  city. Emits **`bounds`** on `load` + every `moveend` (pan/zoom). No more auto-fit-to-pins — the
  viewport is driver-controlled; `syncPins` still reprojects on `move`. GPS recenter → its `moveend` → refetch.
- **`MapSurface.vue`** — `onBounds(bbox)` **debounced ~300 ms**; each `loadOverlay` **aborts the prior
  in-flight fetch** (`AbortController`) so a fast pan never paints stale pins. Preset flip refetches the
  current viewport (`lastBbox`). Mounts on the `CONTINENTAL_US` default until the map reports bounds.

### Data hygiene — `is_dev` + a real purge
- **Migration 0029** `f02.facility.is_dev` (bool, default false). DEV_SEED facilities are **map-visible**
  but **excluded from real-data dedupe** (`find_duplicate_candidates` gains `~Facility.is_dev`), so NTAD/OSM
  never merge into throwaway records. `create_facility(..., is_dev=False)`; `seed_demo` now sets `is_dev=True`.
- **`scripts/purge_demo.py`** (`make purge-demo`) — deletes admin-only facilities **and their whole test
  subtree**: demo loads/stops (F05), armed geofences + presence/events (F03), crowd submissions/beliefs (F10),
  M2 profiles/reviews. Scoped to the admin-only id set; real POI untouched; **idempotent**. Purged **51
  facilities + 39 demo loads** from the dev DB (4162 → 4111; loads 39 → 0).

### Rename
- `ui/index.html` `<title>` → **Haulmeter**. The wordmark was already centralized as `Haulmeter` in
  `ui/src/core/brand.js`; only the tab title lagged. All other `longhaul` strings are infra
  (Docker/DB/MinIO creds, `longhaul-api`, evidence-hash namespace) and deliberately stay.

## 3. Tests (all green)

- **API pytest 368 passed** (was 361; +7): `test_m01_map.py` — bbox pins-in-view, dense→clusters,
  **area-cap forces clusters**, **bbox preset filter**; `test_map_api.py` — bbox is primary over HTTP,
  no-bbox-no-point → 422; `test_ingest.py` — **is_dev excluded from dedupe**.
- **Vitest 121 passed** (was 117; +4): mount fetches by bbox + **moveend refetches (debounced)**;
  **burst debounced to one**; **rapid pan aborts the in-flight fetch** (asserts `signal.aborted`);
  **preset change refetches**.
- **Lint** ruff clean · **import-linter 29/29**.

## 4. Live verification (dev DB, real data, via `GET /map/overlay`)

| Viewport | bbox | Result |
|---|---|---|
| Wisconsin (state zoom) | 43.0,-91.0 → 45.5,-88.0 | **100 real pins** (NTAD safety/weight, rest areas) — was empty |
| Illinois (pan east) | 38.5,-91.0 → 42.5,-87.5 | **94 real pins** (rest stops, Coalfield NB/SB) — IL loads on pan |
| Continental (national default) | 24,-125 → 50,-66 | **clustered: 3549 facilities → 80 bubbles** (bounded payload) |

### Live browser pass — real Mapbox token, headless Chromium (Playwright), 360×800 mobile viewport

Drove the actual GL map at `localhost:9008/map` (authenticated, geolocation spoofed to WI 44.5,-89.5).
Each viewport transition fired a fresh **debounced bbox fetch** and the map repainted. **No token/console errors.**

| Viewport | `/map/overlay` bbox | On-map render |
|---|---|---|
| Wisconsin (state, z7) | lat[43.3..45.7] lon[-90.5..-88.5] | **49 real pins** (rest-area + fuel pucks: Wausau, Stevens Point, Madison) |
| Illinois (pan, z7) | lat[38.7..41.3] lon[-90.0..-88.0] | **25 real pins** (truck stops: Bloomington, Springfield, Decatur, Effingham) |
| Continental (z3.5) | lat[23.9..52.7] lon[-109.7..-87.3] | **126 cluster bubbles** (§11.5 count + dominant-status color, incl. amber chips) |

Auto-geolocate correctly opened tight (z15) on the WI GPS dot; the empty-map bug is gone at every zoom.
(Method: temporary `window.__hmMap` seam in MapCanvas to script `jumpTo` — added, used, **reverted**; tree clean.)

## 5. Exact next task

Owner's call — the map fix is complete and verified end-to-end (unit + API + **live browser pass**, §4). Candidates:
- **TPIMS live token** still blocked on registration (only 3 dev sites); when it lands, `make ingest-tpims`.
- Resume the module build order per PRD §6 where HANDOFF-064 left the module worklist.

## 6. Rules (unchanged)

Plan-first · Docker-only · **local commits only, NEVER push** · tests with every change · design-prd governs
UI (360 dp first, tokens-only, §22.3 DoD) · run suites in-container while the stack is up. Commit messages end
with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## 7. Key files touched

```
api/app/foundation/f02_facility/domain/{models,service}.py   is_dev + in_bbox
api/app/foundation/f02_facility/public.py                     export in_bbox
api/app/foundation/f11_map/domain/service.py                 overlay_pins_bbox
api/app/foundation/f11_map/public.py                          export overlay_pins_bbox
api/app/modules/m01_map/domain/service.py                    map_overlay_view_bbox + MAX_BBOX_DEG2
api/app/modules/m01_map/public.py                            exports
api/app/api/m01_map.py                                        bbox-primary /map/overlay
api/migrations/versions/0029_f02_is_dev.py                   is_dev column
api/scripts/{seed_demo,purge_demo}.py                        is_dev seeding + cascade purge
Makefile                                                      purge-demo target
ui/src/core/api.js                                           fetchOverlay bbox + AbortSignal
ui/src/core/components/MapCanvas.vue                         bounds event, continental default
ui/src/surfaces/MapSurface.vue                               debounced/abortable viewport fetch
ui/index.html                                                title -> Haulmeter
api/tests/{modules/m01_map,api,foundation/f02_facility}/...  +7 API tests
ui/test/ui-components.test.js                                +4 vitest
```
