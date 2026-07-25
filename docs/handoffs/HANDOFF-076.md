# HANDOFF-076 — E3.1 weigh stations: ingestion, driver reporting, map + corridor

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).
**State in one line:** extension-PRD **§E3.1 is closed** and **trucker request #4** is answered —
weigh stations are ingested from OSM, reported open/closed by drivers through the ordinary F10 crowd
pipeline, and surfaced on the Drive preset and the corridor behind their own flag.

**Read order each session:** `HANDOFF.md` (pointer → this file) → PRD §6/§7 → design-prd §11/§16/§22/§23
→ this file → HANDOFF-075 (Admin Console 2.0c).

---

## 0. Current state

| Thing | Value |
|---|---|
| Migrations | head **0043_f01_impersonation** (E3.1 added none) |
| Tests | **pytest 775 · vitest 256 · ruff clean · import-linter 30/30** |
| `make ci` | **PASSES COLD** |
| New flag | `m01_weigh_stations` — registered, **default OFF** |
| Live ingest run | **none** — see §3 |

---

## 1. The source question, answered honestly

The brief said: *"If no verified source exists, say so and ship OSM-only — do not scrape ad-hoc pages."*

**No verified authoritative source exists.** What was actually checked, not assumed:

| Candidate | What it turned out to be | Verdict |
|---|---|---|
| NTAD ArcGIS org (1,025 services) | one weigh-related service: `NTAD_Weigh_in_Motion_Stations` | inspected → rejected |
| `NTAD_Weigh_in_Motion_Stations` | **763 rows**; fields `functional_class, station_id, Counts_Year, Sum_Weight_Year, Num_Days_Active` — **no name, no enforcement flag** | it is a **traffic-sensor inventory**, not a list of scales |
| Bypass programs (Drivewyze / PrePass) | explicitly out of scope per the brief | not pursued |
| State DOT pages | scraping was explicitly forbidden | not pursued |

Shipping the WIM layer would have planted ~763 pins at places drivers never stop. **OSM-only, stated
plainly** — and the ingest flag stays separate from the display flag so we can look at what we pulled
before showing it to anybody.

**The OSM tag map is grounded in taginfo, not memory.** This mattered:

```
amenity=weighbridge        12,178 uses   -> the tag that actually carries these
amenity=weigh_station          38 uses   -> marginal but real, one tuple entry
highway=weigh_station           0 uses   -> DOES NOT EXIST. A rule for it would have
                                            been dead code that looked like coverage.
amenity=vehicle_inspection 13,344 uses   -> deliberately NOT mapped
```

That last line is the one worth remembering: `vehicle_inspection` is MOT/state safety inspection and
has nothing to do with weighing. It **outnumbers real weighbridges**, so mapping it — the obvious
thing to do from the name — would have more than doubled the layer with pins a driver never stops at.
There is a negative test for it.

## 2. What was built

### Ingest (F2)

- `SERVICE_SCALE` — a weighbridge is carried as a **service as well as a kind**. That is what makes
  one mapped *inside* an existing truck stop **enrich that facility** under E3.2's union rule instead
  of planting a second pin on top of it. No new pipeline code; the composite rule did the work.
- Two kinds, because they are two different facts to a driver: a CAT-scale-branded weighbridge is
  `scale` (a service you pay for), a public one is `weigh_station` (a stop you cannot skip).
- **Not hgv-gated.** An enforcement scale exists *for* heavy vehicles whether or not the mapper tagged
  access; gating on `hgv` would have silently dropped most of them.
- `Makefile` osmium filter extended — **without this the tag never reaches the extract**, so the rules
  would have been correct and inert.

### Surfacing (F11 / M1)

- **A pin's status signal now follows what the facility IS.** `status_signal_for(type)` — a truck
  stop's status is how full it is, a scale's is whether it is open. Reading parking fullness off a
  scale would have rendered a status that means nothing about it.
- `m01_weigh_stations` gates **what a driver sees**, separately from the `f02_ingest_osm` flag that
  governs the pull. While it is off the **server returns nothing** — the client is never handed a
  layer to filter, so there is no client-side gate to keep in sync.
- `scales_ahead()` + `GET /map/scales-ahead` — the corridor line, **capped at two**. Scales are sparse;
  this is for the next few decisions, not a listing.

### UI

- The report vocabulary is **derived from the facility type in one function** (`statusReportFor`), so
  the question shown, the two buttons, and the F10 signal posted cannot drift apart. A scale's answer
  can never be filed as a parking reading — there is an API test for exactly that.
- `ReportSheet` options are now a prop instead of a constant; `StatusPill` labels are translated.
- Corridor: scales **lead** the stack (they are the only line with a deadline attached) and are
  read-only while moving, like every other corridor line.

### §23 decisions logged

Two entries: the **inverted colour semantics** (owner-approved) and the **layer/flag placement**.

## 3. The colour inversion — the one thing to re-read before touching this

`closed` → `--ledger-500` (the good-news token). `open` → `--marker-500` (attention).

This is **backwards from every other status in the product**, deliberately. Everywhere else,
more-of-the-thing is worse. Here the thing itself is the obstacle, and a **closed scale is what a
driver hopes for**. Colour follows the meaning to the driver, not the word. Rendering "open" green
because open is usually good would tell a tired driver the opposite of the truth at highway speed.

No new token was introduced. C-1 is load-bearing here rather than incidental: the pill always carries
its translated label, so a driver who cannot separate the two hues still reads "Closed".

Anyone who finds this inversion and "fixes" it will make the layer actively dangerous. Hence the
§23 entry, the comment at the definition, and `ui/test/weigh-station-ui.test.js`.

## 4. What was NOT done, and why

- **No live OSM pull was run.** The extract filter changed, so a real pull needs an osmium run against
  a fresh extract — that is a decision about bandwidth and timing, not a code change. **Ingest counts
  are therefore unknown**; nothing in this handoff claims otherwise.
- **`m01_weigh_stations` is OFF.** Turning it on before a real pull would show drivers an empty layer.
  The intended order is: pull → inspect the count in the admin console's Data & Ingest section → enable.
- **F10's 2h half-life was not retuned** (the brief said it stands). A test now asserts the half-life
  and the point value so they cannot drift silently.
- **No migration.** E3.1 needed no schema change; it composes existing tables.

## 5. Exact next task — recommendation

**Run the OSM pull and decide on the flag.** It is the only thing standing between this layer and
drivers, and it is a ten-minute operation now that everything downstream is tested. Concretely: fresh
extract → `make` osmium filter → ingest → read the count in Data & Ingest → enable
`m01_weigh_stations` if the count is sane.

**Then: founding-vendor onboarding.** It has been the standing recommendation since HANDOFF-072 and
every tool it needs exists. It is still the first real data this platform will hold.

**Alternatives:** TPIMS second-state activation; §17 Q9 truck routing, the largest open product decision.

## 6. Blockers / questions

- **Still no git remote** — four sessions running. Six commits sit locally on `main`. Add one and I'll push.
- **Coverage of the OSM weigh-station layer is unknown until a pull runs.** 12,178 `weighbridge` uses
  is worldwide, not US. If the US count comes back thin, the honest options are to ship it thin
  (a sparse layer that is *correct* still beats a dense one that is wrong) or to revisit whether a
  state-by-state authoritative source is worth the per-state effort — **not** to relax the tag rules,
  which is how `vehicle_inspection` would end up on the map.
- §17 Q15 (deactivation conduct policy) and Q16 (hard delete) remain open from HANDOFF-075.

## 7. Working rules (unchanged — non-negotiable)

Docker-only (dev = CI parity) · **local commits only, NEVER push** (no remote configured) · plan-first ·
**tests with every change** · live pulls never in CI (fixtures drive tests) · **AI-CONTEXT comments only** ·
import-linter authoritative · **design-prd governs ALL UI** (LAW 0, tokens only, six locales) ·
session ends by writing the next HANDOFF.
Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

`test_phase_a_law.py` untouched and green.

## 8. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-076 + design-prd §23 (inverted scale colours, layer flag)
6b27cd6 E3.1: weigh stations — OSM ingestion, driver open/closed reporting, map + corridor
```

## 9. Key files touched

```
F02      api/app/foundation/f02_facility/domain/ingest/adapters.py (SERVICE_SCALE,
         weighbridge type + service rules, the vehicle_inspection negative) · public.py
F11      api/app/foundation/f11_map/domain/service.py (status_signal_for) · public.py
M01      api/app/modules/m01_map/domain/service.py (WEIGH_STATION_FLAG,
         MAX_CORRIDOR_SCALES, _preset_types, scales_ahead) · public.py
API      api/app/api/m01_map.py (GET /map/scales-ahead)
BUILD    Makefile (osmium filter += amenity=weighbridge,weigh_station)
TESTS    api/tests/foundation/f02_facility/test_ingest_weigh.py (NEW)
         api/tests/modules/m01_map/test_weigh_stations.py (NEW)
         api/tests/api/test_weigh_station_api.py (NEW, end-to-end)
         api/tests/fixtures/ingest/osm_weigh.geojson (NEW)
UI       ui/src/core/presentation.js (WEIGH_STATUS, SCALE_TYPES, statusReportFor)
         ui/src/core/components/{ReportSheet,StatusPill,FacilityCard,CorridorStack}.vue
         ui/src/surfaces/MapSurface.vue · ui/src/core/api.js
         ui/src/core/i18n/*.json (5 keys ×6) · ui/test/weigh-station-ui.test.js (NEW)
DOCS     design-prd.md §23 ×2 · HANDOFF-076.md · HANDOFF.md
```

## 10. Ports / env

**No port or env changes. No migration.** One new F13 flag, `m01_weigh_stations`, default OFF.

Operational note carried forward: `make ci` leaves Postgres running, so `make up` straight afterwards
fails preflight. `make down && make up` is the sequence.
