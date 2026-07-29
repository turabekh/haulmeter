# HANDOFF-076 — E3.1 weigh stations: ingestion, driver reporting, map + corridor

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).
**State in one line:** extension-PRD **§E3.1 is closed** and **trucker request #4** is answered —
weigh stations are ingested from OSM, reported open/closed by drivers through the ordinary F10 crowd
pipeline, and surfaced on the Drive preset and the corridor. **The pull has run for four states and
the layer is LIVE** (`m01_weigh_stations` enabled): 106 enforcement scales + 15 standalone commercial
ones, with 244 existing facilities carrying a scale badge instead of a duplicate pin.

**Read order each session:** `HANDOFF.md` (pointer → this file) → PRD §6/§7 → design-prd §11/§16/§22/§23
→ this file → HANDOFF-075 (Admin Console 2.0c).

---

## 0. Current state

| Thing | Value |
|---|---|
| Migrations | head **0043_f01_impersonation** (E3.1 added none) |
| Tests | **pytest 787 · vitest 256 · ruff clean · import-linter 30/30** |
| `make ci` | **PASSES COLD** |
| New flag | `m01_weigh_stations` — **ENABLED** in dev after the pull (§4) |
| Live ingest | WI · IN · IA · MN — **106 weigh_station + 15 scale pins** (§4) |

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

## 4. The pull — and the gap it exposed

Four states still had their Geofabrik `.pbf` locally, so they were re-filtered with the new osmium
rule without re-downloading ~900 MB. **Kansas, Kentucky, Michigan and Ohio have only the old GeoJSON**
(their pbfs were deleted) and still need a fresh download before their scales exist.

| | staged | created | matched | weighbridges in extract |
|---|---|---|---|---|
| Wisconsin | 515 | 98 | 417 | 100 |
| Indiana | 619 | 108 | 511 | 116 |
| Iowa | 564 | 94 | 470 | 99 |
| Minnesota | 402 | 61 | 341 | 61 |

The old filter had incidentally caught 0–4 weighbridges per state through the `hgv` rules. The layer
is **not** thin — the worry recorded in §6 of the first draft of this handoff is answered.

### What went wrong, and what it cost

**The composite rule did not fire for the case that dominates.** The plan and the first version of
this handoff both claimed a weighbridge inside a truck stop "enriches it rather than plants a second
pin — no new code." That is true only when the two records SAY the same thing: the F2 dedupe matches
on fuzzy NAME, and "Cat Scale" resembles "Pilot Travel Center" not at all. The fixture happened to
name its weighbridge after the host, so the test passed and proved nothing about real data.

Measured: **253 commercial scales, 239 within 150 m of a facility that already had a pin** (169 within
50 m), and 6 merged. The rest were second pins stacked on Pilots, Love's and rest areas — precisely
what design-prd §11.1 forbids.

The fix is a **co-located amenity** flag on `StagedRecord`: a record that describes a thing AT a site
rather than a site merges into the nearest destination by **proximity alone**. Two rules stop it
becoming a general proximity merge that would collapse the Pilot and the Love's across the road:

- only a record the **adapter** marked co-located may take the path, and
- only a **destination** may host one, so amenities never chain into each other.

150 m is the measured figure — it covers 239 of the 253 while a truck-stop lot is itself ~200 m across.
A **public weigh station is deliberately not co-located**: it is a destination a driver navigates to,
and 69 of the 103 stood more than 2 km from anything.

**Two further bugs, both mine, found only by looking at the data after the fix:**

1. **A tenant overwrote its host's identity.** The re-ingest path replaces a source's attributes
   wholesale, so narrowing the contribution only at merge time was undone by the very next pull —
   **203 truck stops briefly advertised catscale.com**. The narrowing now runs on every write, from
   one function (`_contribution`).
2. **A CAT scale filed itself as a REPAIR SHOP.** Making a weighbridge a SERVICE also made it match
   the catch-all `some service + hgv -> repair` rule sitting *above* the weighbridge rules. Specific
   now outranks catch-all, and `colocated_amenity` is derived from the **resolved type** so the flag
   and the kind cannot disagree again.

Neither would have been caught by the fixtures. Both have tests now.

### After repair and re-ingest

`make repair-scales` (`DRY_RUN=0` to apply) fixes rows written before the rule existed — a re-ingest
cannot, because an already-seen `(source, external_ref)` takes the update-in-place branch and never
revisits which facility it belongs to. It merges rather than deletes, so every `facility_id` anyone
already holds still resolves. Idempotent; a second run finds nothing.

| | before | after |
|---|---|---|
| pins for scales | 356 | **121** (106 enforcement + 15 standalone commercial) |
| existing facilities carrying a scale badge | 6 | **244** |
| hosts wearing a tenant's identity | 203 | **0** |

Verified over HTTP: the Drive preset returns weigh stations as `small_square` pins with `status: null`
(nobody has reported yet — the honest state), Tonight and Work return none, and `/map/scales-ahead`
returns the corridor line.

## 5. What was NOT done, and why

- **Four states only.** KS, KY, MI, OH need a fresh Geofabrik download before their scales exist.
- **F10's 2h half-life was not retuned** (the brief said it stands). A test now asserts the half-life
  and the point value so they cannot drift silently.
- **No migration.** E3.1 needed no schema change; it composes existing tables.
- **`merge_facilities` does not recompute the survivor's attributes.** The repair script calls
  `_recompute_canonical` itself. This means the admin console's own merge (decision 7) probably leaves
  the survivor's attributes stale — **worth checking before relying on it**. Not fixed here because it
  touches the console's merge path and deserves its own change.

## 6. Exact next task — recommendation

**Founding-vendor onboarding.** It has been the standing recommendation since HANDOFF-072, every tool
it needs exists, and it is still the first real data this platform will hold.

**Or, if you'd rather finish the map first:** pull the four remaining states (KS, KY, MI, OH). Each
needs a ~200–300 MB Geofabrik download, then `make osm-extract STATE=<x>` and `make ingest-osm`. The
co-located rule now applies from the first write, so no repair pass will be needed for them.

> **FALSIFIED 29 Jul 2026 (HANDOFF-099 §4d) — leaving the sentence above so the mistake
> is legible.** The rule is order-dependent WITHIN a batch: a pump or a scale processed
> before the site it stands in exists finds no host and earns its own pin. The Texas
> pull produced **162 unmerged fuel islands and 203 unmerged scales** on exactly this
> path. **Run `repair-scales` and `repair-fuel` after every ingest**, not only over
> legacy rows. The branded-service-area type rule IS order-independent and needs no
> repair (0 re-types on Texas).

**Alternatives:** TPIMS second-state activation; §17 Q9 truck routing, the largest open product decision.

## 7. Blockers / questions

- **Still no git remote** — four sessions running. Six commits sit locally on `main`. Add one and I'll push.
- **Coverage is answered for four states and unknown for the rest.** WI/IN/IA/MN yielded 61–116
  weighbridges each, so the layer is real. If a later state comes back thin, the honest options are
  to ship it thin (a sparse layer that is *correct* beats a dense one that is wrong) or to revisit a
  state-by-state authoritative source — **not** to relax the tag rules, which is how
  `vehicle_inspection` would end up on the map.
- **One false positive seen in the real data:** a `weighbridge` named "Tractor Pull Weigh Scale". One
  in 103 is tolerable and no tag rule would catch it; noting it so nobody is surprised.
- **`merge_facilities` may leave the survivor's attributes stale** (§5) — check before relying on the
  console's merge.
- §17 Q15 (deactivation conduct policy) and Q16 (hard delete) remain open from HANDOFF-075.

## 8. Working rules (unchanged — non-negotiable)

Docker-only (dev = CI parity) · **local commits only, NEVER push** (no remote configured) · plan-first ·
**tests with every change** · live pulls never in CI (fixtures drive tests) · **AI-CONTEXT comments only** ·
import-linter authoritative · **design-prd governs ALL UI** (LAW 0, tokens only, six locales) ·
session ends by writing the next HANDOFF.
Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

`test_phase_a_law.py` untouched and green.

## 9. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-076 — the pull, the counts, and what it exposed
624cec2 F2: co-located amenities merge into the site they stand in, by proximity
6b27cd6 E3.1: weigh stations — OSM ingestion, driver open/closed reporting, map + corridor
```

## 10. Key files touched

```
F02      api/app/foundation/f02_facility/domain/ingest/adapters.py (SERVICE_SCALE,
         weighbridge type + service rules, the vehicle_inspection negative,
         colocated_amenity, weighbridge outranks the repair catch-all) · public.py
         .../domain/ingest/pipeline.py (_contribution, the co-located merge branch)
         .../domain/service.py (colocated_host, COLOCATED_RADIUS_M/HOST_TYPES)
F11      api/app/foundation/f11_map/domain/service.py (status_signal_for) · public.py
M01      api/app/modules/m01_map/domain/service.py (WEIGH_STATION_FLAG,
         MAX_CORRIDOR_SCALES, _preset_types, scales_ahead) · public.py
API      api/app/api/m01_map.py (GET /map/scales-ahead)
BUILD    Makefile (osmium filter += amenity=weighbridge,weigh_station; repair-scales)
SCRIPT   api/scripts/repair_colocated_scales.py (NEW, one-off, dry-run by default)
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

## 11. Ports / env

**No port or env changes. No migration.** One new F13 flag, `m01_weigh_stations` — default OFF in
code, **enabled in the dev DB** after the pull.

Operational note carried forward: `make ci` leaves Postgres running, so `make up` straight afterwards
fails preflight. `make down && make up` is the sequence.
