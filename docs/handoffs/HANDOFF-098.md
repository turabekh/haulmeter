# HANDOFF-098 — the session the map stopped making things up

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 28 July 2026 · **Stack:** UP (`make down` to stop).

**State in one line:** Corridor mode — the DRIVING screen, the one state where a driver
cannot look anything up — was rendering **three invented facilities from a fixture**,
including a specific truck stop reported as `full` 3.4 miles ahead; and the word "ahead"
meant **due north** for every driver in the product, because the location sensor had
never captured a heading.

> Read 097 for the Load-tab QA run that preceded this. This session was the Map tab:
> four slices, planned and approved before any code (HANDOFF §4.1).

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0052_m03_claim_clock_since** (untouched — this session added no schema) |
| Tests | **pytest 1055 · vitest 477 · layout 579 · ruff clean · import-linter 30/30** |
| §23 decision log | **83 entries** (81, 82, 83 added) |
| Handoffs | 000 → 098 |
| Git | `main` local only, never pushed · **nothing committed this session** — see §7 |
| Services | **running** |

## 2. What was wrong, in the order it mattered

All seven were found by reading the surface against §10.1 and §11 before touching
anything. None was caught by 1,048 tests or 545 layout checks.

| # | Defect | Shape |
|---|---|---|
| 1 | `MapSurface` passed hardcoded `SAMPLE_CORRIDOR` into `CorridorStack`; **`GET /map/corridor` had existed since M1 and no client function had ever called it** | capability with nothing reaching it — and the replacement was a **lie**, not an absence |
| 2 | `location.js` dropped `coords.heading`; `fetchScalesAhead` and `fetchCorridorVendors` both defaulted `headingDeg = 0` | **due north for everyone**, since both layers shipped |
| 3 | `/map/corridor` returned no status and no price; the fixture carried a `status` | fixture whose shape hides its endpoint (entry 52, again) |
| 4 | `fuel_net` and `bookable` badges serialized for years; `MapCanvas` rendered only food | §11.2 named three badge slots and drew one |
| 5 | No "Arm stop" anywhere; `/load/active` returned an opaque stop id | a field (`facility_id`) present and never asked for (entries 74, 80) |
| 6 | `const preset = ref("drive")` — reset on every mount | §11.3's "persists per state (RESTING→Tonight)" unimplemented |
| 7 | Corridor cards were `<li>`, so §11.4's "deferred-safe taps" was **vacuously true** | a clause satisfied by the feature not existing |

## 3. What shipped — four approved slices

**A · Corridor mode is served, not invented.** Heading captured (`coords.heading`, else
derived from displacement with a 15 m floor so a parked truck does not spin the corridor
through four quadrants); `corridor_ahead` added to M1 carrying crowd status + freshness;
`_fuel_badge` factored so the corridor and the pin **cannot quote different prices for
the same pump**; `SAMPLE_CORRIDOR` deleted; scales and food now get the real heading.
`corridor_view` left untouched — M7, M8 and M13 consume its entries.

**B · §11.2's badge slots drawn.** Fuel price as a decluttered label, bookable as a `$`
glyph on the opposite shoulder from food. §11.5's rule (`zoom threshold` +
`no overlapping labels`) implemented as `placeLabels` in `core/presentation.js`, because
inside the component it would have shipped unexercised — a mounted canvas has no
viewport in vitest. **The clock/dwell slot is deliberately still empty**: no such signal
exists in the payload, and a slot with nothing behind it is the fake confidence §11.7
forbids.

**C · The map and the load know each other.** `/load/active` now names the dock;
the armed facility's card leads with §10.1's third rung as a NAV-5 cross-link to the
Meter (**not** a new "create a load from a pin" flow — that would be navigation
structure, §22 never-improvise). Preset persisted per driver state via
`core/map-presets.js`.

**D · §11.4's deferred-safe tap.** Owner-approved destination: a chip on the Map tab
appearing once **stopped**, opening a sheet (NAV-3, no new route). The tap opens nothing,
is idempotent (a gloved double-tap is one intention, never a toggle), and the saved row
**states no status and no distance** — both were true thirty miles ago, and a lot that
read `empty` at 60 mph is exactly the lot that fills while you drive to it.

## 4. Verified live, not just in tests

```
GET /map/corridor?lat=32.7767&lon=-96.7970&heading_deg=…
  0° → Love's #212 (status "some", 1 sample) · QuikFuel ($3.94 net, 25¢ saved, feed)
 90° → Pilot Flying J #88
180° → I-35 Rest Area
270° → Indie Fuel Stop · RoadFuel Express · TA Dallas South
```

Four headings, four answers. **Before this session every one of those calls returned the
0° result**, because 0 was the only heading the client could send.

## 5. Method notes — read before trusting a green run

- **The layout harness caught TWO violations in code minutes old, and both were mine.**
  (1) My first `$` badge was **text at a hardcoded `10px`** — below §6.2's 13 dp floor
  *and* a hardcoded value where §22.3 box 8 says tokens only; it failed in three locales.
  The food badge never tripped it because it was always an icon, and a 14 dp disc cannot
  hold any legal type size, so that slot can only ever hold a glyph. (2) The saved sheet's
  **Remove measured 44×48 dp in Punjabi** — §6.5 is 48 dp in BOTH axes and I set only the
  height. That is the identical defect already recorded on `.cap__chip`: **a control sized
  by its content is sized by the shortest locale.** Two runs, two real findings, neither
  visible in 477 unit tests. **The harness is worth its 12 minutes.**
- **One full-suite run failed and the next three did not.** `food-decide.test.js` failed
  once under `make test` (5.9 s on a test that takes 0.6 s alone), immediately after I
  added a corridor fetch on mount — a plausible cause, since that test asserts on map
  fetches. It did not reproduce in three subsequent full runs (one standalone, two under
  `make test`). **Recorded as unexplained rather than as flake**, per 097 §5: it may be
  contention, and it may be an ordering dependency that will resurface.
- **A new test passed for the wrong reason.** The corridor/pin price-agreement test
  compared two `None`s in a database with no fuel rows and went green — entry 42's shape
  exactly. It now seeds a station and asserts the badge **exists** before comparing.
  Asserting agreement between two absences is not a test.
- **Slice D falsified one of Slice A's own tests.** `"nothing in the stack is a control"`
  was true when written and wrong four hours later. It was **restated** to the invariant
  it was protecting (nothing opens a flow; only the deferrable row is a control), not
  deleted. A test that must be deleted to ship a feature was usually measuring the
  implementation rather than the rule.
- **Three component assertions were re-run against the pre-change render** and all three
  failed, per 097 §5. The heading tests were written against a sensor that had no heading
  field at all.
- `make test` and `make ui-layout` were never run concurrently (097 §5).

## 6. Exact next task — Session 19

1. **`rate_cents` and `accessorial_terms` still reach no load field.** Carried unchanged
   from 097 §6 — this session was the Map tab instead. Sixth and seventh dropped parsed
   values; fix together and check every neighbour in `parsed`.
2. **Run the Map tab the way 097's owner ran the Load tab.** Every defect above was found
   by reading code against the constitution. That method found seven; *using* the Load tab
   found ten in one session, three of them invisible to a passing test by construction.
   The Map tab has never had that treatment.
3. **Republish the QA checklist artifact** (still outstanding from 097 §6). Note
   `docs/user-guide-load-and-docs.md` was written this session and contains a 22-step
   checklist for those two tabs; the Map tab now needs the same.

## 7. Uncommitted tree — read this before committing

**Nothing was committed this session.** The working tree already carried uncommitted work
from the previous session when this one started (`f04_evidence`, `m05_protection`,
`test_load_import`, `test_protection_api`, `ui-components.test.js`, the six locale files),
and commit `8bb4a2c` named in HANDOFF-097 §8 **is not in the log** — so 097's last change
appears to be staged-but-uncommitted. `api/app/api/load.py` carries *both* that prior work
and this session's `/load/active` change, so the two cannot be separated by staging paths
alone. Left for the owner rather than swept into one commit.

## 8. Debt

- **`rate_cents`, `accessorial_terms`** — parsed, stored on no load field (from 097)
- **§11.2's clock / dwell-risk badge slot** has no signal behind it. M2 computes dwell
  statistics; nothing puts them on the overlay payload. The slot stays empty on purpose.
- **§11.6 is only half-honoured.** `MapCanvas` uses Mapbox Standard's `lightPreset` keyed
  to the wall clock, not custom day/night styles built from §6.1 tokens, and it does not
  follow the app's own theme toggle. A driver in dark theme at noon gets a light basemap.
- **§11.4's "map locks to heading-up follow" is not implemented** — corridor mode replaces
  the map entirely rather than following it. Heading now exists, so this is buildable.
- **Corridor entries carry no coordinates**, so a saved row's Navigate routes via the
  facility page rather than handing coordinates to the nav app. Honest, but one field on
  the corridor response would fix it.
- **`pin.shape`** is serialized by the overlay and unused by the canvas (icon encodes type
  per an owner-directed §11.2 refine). Harmless, but it is a payload field nothing reads.
- Per-stop detention terms exist in the schema and are not expressible in the UI (097)
- **M2-FR4 does not exist** — needs an owner decision (097)
- Evidence logs before `f3e6a86` stay polluted; the chain is append-only (097)
- The meter caption reported missing in one screenshot right after arrival —
  **unreproduced, do not "fix" without seeing it** (097)

## 9. Key files touched

```
API  m01_map/service.py     corridor_ahead (status per facility kind, capped at 3)
     m01_map/public.py      corridor_ahead, MAX_CORRIDOR_ENTRIES exported
     api/m01_map.py         /corridor rewritten; _fuel_badge factored out of _enrich
     api/load.py            /load/active names the dock (facility_id + facility_name)
UI   core/location.js       heading: coords.heading, else bearing from displacement
     core/presentation.js   placeLabels (§11.5 declutter), ageLabel
     core/map-presets.js    NEW — §11.3 preset persistence per driver state
     core/saved.js          NEW — §11.4 save-for-stop queue
     core/api.js            fetchCorridor; activeStopFacilityId
     MapCanvas.vue          §11.2 price + $ badge slots
     CorridorStack.vue      server data, no_report honesty, price, deferred-safe tap
     FacilityCard.vue       §10.1's third CTA (isActiveStop → open-stop)
     MapSurface.vue         corridor wiring, heading, saved chip + sheet, presets
     fixtures.js            SAMPLE_CORRIDOR deleted
     layout.spec.js         `storage` seam + sheet-map-saved state
DOCS design-prd.md §23 entries 81–83
     user-guide-load-and-docs.md  NEW (earlier this session, Load + Docs tabs)
```

## 10. Restarting

```
make up          # preflight, then the full stack
make test        # 1055 pytest + 477 vitest
make ui-layout   # 579 mobile-first checks at 360 dp (~12 min) — RUN IT ALONE
```

**The standing warning, still earned.** Seven Map-tab defects were found this session by
reading the code against §10.1 and §11 — a method that works and is strictly weaker than
using the app. 097's owner found ten defects in one sitting by running one load. The Map
tab has not been run that way. Corridor mode in particular can now only be judged from a
moving vehicle, and everything above about it is verified by curl and by tests, **not by
a driver.**
