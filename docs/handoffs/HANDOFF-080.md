# HANDOFF-080 — the food flow can now be acted on

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** the food section told a driver a cook existed and then gave them **no way to
decide or to go** — no distance, no lot name, no navigate. All three now exist.

Read alongside **HANDOFF-079** (FR7 claim flow, the OSM pass) and **078** (consolidated platform
picture, §§6–11 still current).

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0045_m13_halal_claim** (none added) |
| Tests | **pytest 860 · vitest 334 · ruff clean · import-linter 30/30** |
| §23 decision log | 35 entries |
| Handoffs | 000 → 080 |
| Git | **17 commits local on `main`, no remote configured** |

## 2. The bug underneath the feature request

The owner's read was that the food section "didn't feel good". Walking the journey found why, and it
was not a missing feature — it was a field that had never been populated.

**`appearances_in_bbox` never passed an origin, so `distance_m` was null on every map entry.**
Meanwhile `corridor_vendors` DID compute a distance, and `CorridorStack` rendered it. The result was
exactly backwards: a driver saw how far away a cook was **only while moving**, where every tap is
deliberately deferred-safe and nothing can be acted on, and **never while stopped**, which is the only
moment the detour decision is actually made.

Two more gaps fell out of tracing it:

- **The vendor sheet had no Navigate.** It offered *Here now · Not here · Sold out · Rate · Mute* —
  every action except the one the flow exists to produce.
- **The vendor sheet never named the lot.** The card shows where you are, then the sheet replaced it
  with "Today · until 9pm" attached to no place at all. Ambiguous the moment a cook works two lots,
  and it made Navigate impossible to offer honestly.

## 3. What was built

| | |
|---|---|
| **F2** | `facility_distances(db, ids, lat, lon)` — one `ST_Distance` query. Facility geometry belongs to F2, so M13 grew no haversine of its own (the same discipline that has the corridor layer reading M1's geometry). |
| **M13** | `appearances_in_bbox` takes an optional origin; `/vendors/appearances` accepts `lat`/`lon`. |
| **API** | Every entry carries `facility_name`, `lat`, `lon`, resolved in one pass rather than per row. |
| **UI core** | `formatMiles` in `presentation.js`; `CorridorStack`'s two private mile helpers fold into it. `windowLabel` gives "opens 5pm" before the start and "5–9pm" once open. |
| **Sheet** | Lot named per appearance · window · distance · **Navigate as the primary CTA**, *Here now* secondary. |
| **Card** | The distance figure beside the window, Mono. |

### The three honesty rules that shaped it

1. **No location, no distance.** `MapSurface` holds a default centre (Dallas) until its first real fix.
   Sending that as the origin would print a confidently wrong figure, so `located` gates it and nothing
   renders at all — never a placeholder, never a zero.
2. **Whole miles.** A direct line rendered to one decimal implies routing precision a straight line
   does not have. The decimal survives only for corridor distances, measured along M1's geometry.
3. **No ETA.** §17 **Q9 truck routing is open**, so no arrival time is derived from a straight line. A
   test asserts the sheet contains no arrival language, so a future session cannot add one absent-mindedly.

### The reordering, surfaced rather than discovered

Q-3's final tie-breaker is distance. With `distance_m` null everywhere it was `inf` for every map
entry, so **that tie-breaker had never once fired**. It now does: two cooks tying on bucket, tier,
property approval and reliability sort nearest-first, and flip when the driver moves. Asserted in
`test_vendor_distance_api.py` rather than left to be noticed later.

## 4. Verified live

```
cook published at 'Loves 46eef8', opening in 2h
no location   -> distance_m=None   lot='Loves 46eef8'
located       -> distance_m=11109  (7 mi, as the sheet renders it)
lot coords    -> 43.0700, -89.4000 (what Navigate hands off)
window        -> starts 04:10  ends 08:10
```

## 5. Exact next task — recommendation

The food journey still has three gaps the owner named, in the order I'd take them:

1. **You can only be told about food you already found.** Cancellation notices go to drivers who
   previously *confirmed* that vendor, so the one notification that exists serves people who already
   ate there. There is no "follow this cook" and no "someone is cooking on your route tonight". The
   *suggest a cook* demand signal is recorded and nothing carries it back. This is the biggest
   remaining hole in the loop and it is a product decision as much as a build.
2. **Corridor food is inert.** At speed a driver sees three cooks ahead and can do nothing — not even
   "save for the next stop", which §11.4 explicitly contemplates as the deferred-safe pattern. Small,
   well-specified, and it makes the corridor layer worth having.
3. **No photos anywhere.** Deciding to detour for a meal is partly appetite; the sheet is entirely text
   and figures. Needs an owner decision on moderation before any driver-visible image ships.

**Carried and still first in line from 079 §5a:** the geohash-boundary duplicate miss in
`find_duplicate_candidates`, paired with the `merge_facilities` attribute staleness it compounds.

## 6. Blockers

- **No git remote — eight sessions running.** Seventeen commits sit locally on `main`.
- **`find_duplicate_candidates` misses duplicates straddling a geohash cell** (079 §5a): two
  `Blue Beacon Truck Wash #74` records 20.2 m apart, invisible to it.
- **`merge_facilities` may leave the survivor's attributes stale** — urgent once the above produces
  merges to perform.
- **The claimable universe is ten facilities**, and the ceiling is upstream in OSM, not our pipeline
  (079 §5). Growing it means loosening the hgv gate — an owner decision, untouched.
- **A vendor cannot delete their own listing or account** (§17 Q16).
- **Nothing rate-limits vendor registration.**
- **`categories` is collected and unused** — needs the structured treatment halal got.

## 7. Open questions (PRD §17)

Unchanged. **Q9 truck routing is now load-bearing for the food flow specifically**: everything about
"will I make the window" stops at a straight line until it is resolved. Also open: Q1 · Q2 · Q3 · Q4 ·
Q5 · Q7 · Q8 · Q13 · **Q15 conduct policy** · **Q16 hard delete** · Q6.

## 8. Working rules (unchanged — non-negotiable)

Docker-only · **local commits only, NEVER push** · **plan first**, owner approval, then code · **tests
with every change** · live pulls never in CI · **AI-CONTEXT comments only** · import-linter
authoritative · **design-prd governs ALL UI** (LAW 0 mobile-first, §18 for portals, tokens only, six
locales + pseudo) · §22.2 never improvises a token, component pattern, navigation structure or
notification class · session ends by writing the next HANDOFF.

Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

**Phase A holds:** no order, basket, total, checkout or billing column anywhere.

## 9. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-080 — distance, the lot, and a way to go
101bfdb The vendor sheet can now take you there
53febe7 Distance was null on the map and rendered only while driving
d4cd414 docs: the OSM service pass ran — 1 claimable site became 10
df663f0 docs: HANDOFF-079 — FR7 service-center claim flow
1379762 A weighbridge is not a business: one list for claim and curate
4b2cd99 The other end of the claim: what a driver actually sees
a0accd5 My site: the four places a claim flow can quietly disappoint someone
f5e33a9 FR7 discovery: a claimant has a business name, not a viewport
```

## 10. Key files touched

```
F2       api/app/foundation/f02_facility/domain/service.py (facility_distances)
         public.py
M13      api/app/modules/m13_vendor/domain/service.py (origin on appearances_in_bbox)
API      api/app/api/m13_vendor.py (_entries_out; lat/lon on /vendors/appearances)
TESTS    api/tests/api/test_vendor_distance_api.py (NEW, 5)
         api/tests/foundation/f02_facility/test_facility.py (+2)
UI       ui/src/core/presentation.js (formatMiles) · ui/src/core/vendors.js (windowLabel)
         ui/src/core/components/VendorSheet.vue (lot, window, distance, Navigate primary)
         ui/src/core/components/FacilityCard.vue · CorridorStack.vue (shared formatter)
         ui/src/surfaces/MapSurface.vue (`located` gate, navigateToVendor)
         ui/src/core/api.js (origin param) · ui/src/core/i18n/*.json (5 keys ×6)
         ui/test/food-decide.test.js (NEW, 17)
DOCS     design-prd.md §23 ×2 (entries 34–35) · HANDOFF-080.md · HANDOFF.md
```

## 11. Ports / env

**No port or env changes.** LOCKED: postgres **5438** · api **8008** · ui **9008**. No migration, no
new F13 flags — this rides the existing `m13_vendor` flag.

`make ci` leaves Postgres running, so `make up` straight afterwards fails preflight.
**`make down && make up`** is the sequence.
