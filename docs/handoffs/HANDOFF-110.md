# HANDOFF-110 — the first session under PRD v2.0, and the rules that had never fired

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 1 August 2026 · **Stack:** **UP** locally (`make down` to stop) · **Deployed:**
https://haulmeter.online — **CURRENT, and verified against the artifact rather than the
script's "done".** A5 is live: 9 service pins near Madison, 5 of them callable, and a call
tap recorded in the production database.

**State in one line:** the map can find a repair shop and call it — and the reason it never
could was not a missing feature but six ingest rules that had never once received the tags
they read.

> First session under `docs/trucker-platform-prd-v2-amendment.md`. Requirement **A5 —
> Service & repair discovery** (Group 1), owner-approved plan, built end to end.

**Nothing is half-finished.** Working tree clean apart from the untracked `collect_files.py`
(still not mine). Everything is pushed and on the box.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0055_f08_push_subscription** — **no new migration**, `services`/`phone` ride in the existing `attributes` JSON |
| Tests | **pytest 1265 · vitest 607 · layout 193 · ruff + import-linter 30/30** — all green, all run unpiped |
| §23 decision log | **117 entries** — 117 added this session, **status `proposed`**, needs your yes/no (§7.2) |
| Handoffs | 000 → 110 |
| Git | **in sync** with `origin/main` (public) |
| Deployed | **CURRENT.** A5 code, the corrected Wisconsin data, and the contact backfill are all on the box |
| Local stack | **UP** |

## 2. What shipped

| Commit | What | Pushed? |
|---|---|---|
| `e2aee9e` | The service rules had never fired — the extract starved them | ✅ deployed |
| `b678bcc` | A placeholder is not a name, whichever kind wrote it | ✅ deployed |
| `8599afa` | The Service preset, and a phone a driver can actually tap | ✅ deployed |
| `21044e2` | The Service chip, the call, and the shop rows — driven on the real map | ✅ deployed |
| `9b72db9` | This handoff + §23 entry 117 (proposed) | ✅ pushed |
| `3fd4208` | Make the call OBSERVABLE, or A5 cannot be validated at all | ✅ pushed + deployed |

## 3. A5's premise was false, and measuring it is the whole session

v2.0 §3 says of A5: *"Most of this exists."* The rules do. **The data never reached them.**

| A5 / v2.0 claim | Measured before writing a line |
|---|---|
| repair shops on the map | **12** `repair` facilities across nine states |
| tire shops · parts · towing | **0 · 0 · 0** |
| "facility card exposes tap-to-call" | **0 of 4,869 facilities had a phone number.** Not one |
| `f02.search_service_facilities` "already searches them" | a **name** search (`q`, min 2 chars) called only by the vendor portal — not a map layer, no geospatial path |

**Cause, proven rather than assumed.** The `osm-extract` recipe passed five tag patterns and
none of `shop=tyres`, `shop=truck_repair`, `shop=car_repair`, `shop=truck_parts`,
`amenity=car_wash`, `service:vehicle:*`. Counted in the two largest filtered extracts on
disk: those tags appear **zero** times in Wisconsin and Texas, `amenity=car_wash` four times
in all of Texas. **Six of the eight `_OSM_SERVICE_RULES` had never fired once**, and could
not have. This is A9 §1's trap, which HANDOFF-099 already hit, sitting underneath the
requirement that reads "most of this exists."

**The tag list now lives with the rules and the Makefile renders it** (`scripts/
osm_filter_args.py`), so there is one list. A probe-based test discovers which tags each rule
actually reads — by running the rule against tag objects that record every lookup and
comparison — and fails when a rule has no way in. **It found two more starved paths beyond
the six**: `_osm_hgv` reads `truck=yes`, which never arrived, and E3.3's `fuel:diesel` — the
tag added so a Flying J carries its own diesel fact — only ever arrived on features admitted
for some other reason.

> The first draft of that test compared KEYS and reported five starved rules. `amenity=
> car_wash` read as covered because the filter passed `amenity=truck_stop`. A selector is a
> key AND a value, and the probe records comparisons now. **The check that measures nothing
> looks exactly like the check that passes.**

## 4. The filter alone would have shipped NOTHING

The obvious fix — extend the filter — produces zero facilities, and one measurement says so.

**Of 2,638 Wisconsin features carrying a service tag, ZERO carry `hgv`, `access=hgv` or
`truck=yes`.** Not one. Nobody tags access on a repair shop; the only access tags present at
all are `customers` (19) and `private` (9). The type rule gated `repair` on `_osm_hgv`, so
every one of them would still have been dropped.

**What actually separates them, hand-audited over all 76 matches:**
- an explicitly truck-specific **tag** — 30 features
- trucks **named in the business name** — 57 features, and **two thirds of the genuine finds
  carry no truck tag at all**. "Diesel Doctors", "Portage Diesel Repair", "Truck Country",
  "Ottery Brothers Truck Wash" are plain `shop=car_repair`. So is "TA Truck Service". So is
  Love's. Drop the name signal and you drop most of the real answers.

The other 2,562 are the car trade — 1,347 `shop=car_repair`, 1,060 `amenity=car_wash` — and
they stay out. **Terms earn their place on the data**, which is why two obvious ones are
missing: `fleet` (13 of its 14 matches are "Fleet Farm", a retail chain whose CAR WASH would
have become a truck repair facility) and `trailer` (its one match is "…Trailer Sales").

**Result, Wisconsin alone: 0 → 65 repair records parsed, 45 facilities after merge.** The
whole nine-state registry held 12.

## 5. Four defects found by driving the real thing, none by a test

Each of these passed every test in the suite at the moment it was found.

1. **The preset shipped DEAD.** `register_flag` creates a row with `enabled=False`, and
   `is_switched_off` reads that as switched off — **so registering the kill switch is what
   turned the feature off.** The real endpoint returned zero service pins in Madison while 45
   repair facilities sat in the table. The unit test passed throughout: it called `kill()`
   explicitly and asserted the *un-registered* state as if it were the default (with no row,
   the predicate fails open). A capability that is off the moment it is registered is this
   project's favourite defect wearing a new hat.
2. **Two Pin constructors.** `phone` was added to one; every unit test passed; the map, which
   uses the other, still had no phone number. §23 entry 113's trap exactly. There is one
   `_build_pin` now.
3. **`None` and `[]` meant the same thing** to the facility-type filter, so switching the
   preset off returned **every facility in the viewport** instead of none. "No filter" and
   "filtered to nothing" are opposite instructions.
4. **"Mobil Diesel" came back as a repair shop** in the real Madison overlay. `fuel` and
   `scale` are `SERVICE_KINDS`, so "has any service" was true of a pump; `diesel` is a
   truck-name term, so "serves trucks" was true of its name. `REPAIR_SERVICE_KINDS` is now
   one definition in F2, read by the rule that TYPES a facility and the preset that FILTERS
   for one — m01 had its own copy for about an hour, which is how the two definitions §23
   entry 94 warns about get started.

**And one that predates A5 entirely.** `host_should_adopt_name` refused exactly one invented
name, `placeholder_name(fuel_station)`, because fuel was the only co-located kind when it was
written. Every other kind's placeholder was adopted: **18 truck stops and a rest area in the
live registry are named "Weigh Station"**, and a weigh station is named "Scale". Found because
adding `repair` to the co-located kinds produced a parking lot called "Repair".

## 6. Method notes

- **The plan changed twice under measurement, both times before code.** Extend the filter →
  measured → the hgv gate is the real blocker. Add the name terms → audited all 76 → `fleet`
  and `trailer` removed.
- **RED first, and proved against the real code.** The starved-rules test was run against the
  Makefile's own list transcribed verbatim, and named the six. The truck-relevance tests were
  proved red by reverting the gate to `_osm_hgv`. The co-location tests failed on the real
  merge path. The born-dead flag test failed against the real registry.
- **One test was rewritten because it proved the wrong thing.** The bay-merge test set
  `colocated_amenity=True` by hand — testing the pipeline while leaving the adapter rule that
  sets it unexercised — and used names similar enough to merge by fuzzy match instead.
- **DRIVING behaviour is tested through the real state machine, not a prop.** A `driving`
  prop would prove only that the parent passes it.
- **Driving the real screen took four attempts and each failure was informative**: the browser
  runs inside the compose network, so `localhost:8008` is its own localhost, and the origin
  `http://ui:9008` fails CORS. Proxying through Node (`route.fetch`) reaches the real API with
  the real database behind it. **Until that worked the map was quietly rendering `SAMPLE_PINS`
  demo fixtures** — Loves #212, Pilot #77 — which is worth knowing: a failed overlay fetch
  looks like a working map.

## 7. Exact next task

**0. DONE — pushed and deployed, and verified against the artifact.** Both diffs were secret-
scanned before leaving (rule 3, public repo). What was done to production, in order:

| Step | Result |
|---|---|
| `git push` + `./scripts/deploy.sh` | served bundle carries `map.preset.service`, `facility.call`, `map.service_none`; `/api/health` 200 |
| `pg_dump` before touching data | `/tmp/haulmeter-pre-a05.sql.gz` on the box — **there are still no automated backups (A12)**, so this was a manual precaution and it is not one |
| `repair-contact DRY_RUN=0` | 839 facilities updated · **625 callable phones, 246 with hours** |
| shipped the corrected Wisconsin extract and re-ingested | **12 → 44 repair facilities** |
| second deploy (the call observation) | POST `/map/facility/{id}/called` → 204, and the row is in `f14.analytics_event` |

**The deploy ships CODE, not DATA**, and that is worth carrying forward: `api/data` is
excluded from the bundle, so the extract had to be `docker cp`'d into the api container by
hand. **The other eight states still run the old filter on the box.** Each needs
`make osm-extract STATE=<x>` locally, then the same manual copy — or a better path than the
one I used.

A first-response `/api/health` came back empty and 200 on the retry: the startup race 106 §6
recorded, not a pattern.

**1. §23 entry 117 is PROPOSED and needs your decision.** The sixth preset chip. It invents
nothing — existing chip, existing Lucide set, NAV-1 untouched, exactly E-D2's Food-chip
precedent — but E-D2 was logged, so this is logged. If you say no, the chip comes out and the
preset stays reachable from the server.

**2. A5 IS OBSERVABLE NOW, AND STILL NOT VALIDATED.** The gap I flagged here is closed: the
tap posts to `/map/facility/{id}/called` and emits `service_call_tapped`, queued through F12
because a breakdown is exactly where there is no signal. The question v2.0 §7 item 6 asks is
now answerable:

```
select count(*) from f14.analytics_event where event_name = 'service_call_tapped';
```

**It reads 1, and that one is mine** — a verification call from this session's own account.
**Validation needs a driver who is not the owner.** Until that number moves for someone else,
A5 is built, deployed, observable and unvalidated, which under v2.0 §2 is not done.

**3. Coverage is still nine states, and A5 makes that worse, not better.** A driver in the
other 41 taps a wrench and gets an honest "none mapped here yet". A9 is blocked by A12, and
A12 is Group 1 and unstarted — **and the extract fix landing now is exactly what A9 §1 says
must be verified against one state before a national run. That verification is done.**

**4. Put a push on a real handset — THIS NEEDS YOUR HANDS.** Unchanged and now four sessions
old (109 §7.1, 108 §7.2, 107 §7.1). Nothing in this repo can exercise it.

**5. The other Group 1 requirements**, in the order I would take them: **A12** (blocking A9,
and the box still has no backups), **A3** (the freshness badge says "1 driver" about a DOT
feed — a trust defect on the daily-open surface), **A1** (Stop Packet, the largest).
**A2 needs D5** and **A4 needs D3** before either can start.

## 8. Debt

**New this session (110):**
- **A5 is observable but unvalidated.** §7.2. The only `service_call_tapped` row is mine.
- **The UI has NO LINT AT ALL.** `make lint` is ruff + import-linter, both Python. A missing
  import in a `.vue` file is a runtime `ReferenceError` nothing catches — and one shipped
  green today: `recordServiceCall` was used in MapSurface and never imported, with every
  unit test passing. A surface test now covers that path (proved red by deleting the import
  again), but the CLASS is uncovered. ESLint with `no-undef` is the fix and it is a
  toolchain decision with a wide blast radius, so it wants its own scoped work rather than
  the end of a session. I hand-rolled a probe to size the gap and it returned 477 hits with
  a false-positive rate that made it useless — which is itself the argument for the real tool.
- **`record_map_open` is exported and called by NOTHING** — not a route, not a test — in the
  same file as the event helper A5 just added. Wiring DAU/MAU is its own decision; the dead
  export is recorded here so the next session does not rediscover it.
- **A deploy ships code, not data.** `api/data` is excluded from the bundle, so putting the
  corrected Wisconsin extract on the box meant a `docker cp` into the running container by
  hand. Doing that for 50 states is not a process.
- **Nothing re-types an existing facility.** "Mobil Diesel" is still a `repair` facility in
  the dev DB — measured, it is the **only** such row, and it was created by this session's own
  ingest run, so production has none. A `repair-*` pass would fix it if it ever spreads.
- **22 facilities carry an adopted placeholder name** (18 truck stops named "Weigh Station",
  and the rest). The guard is fixed forward; the existing rows are a data repair over prod
  and were deliberately not attempted here.
- **Six locales were machine-translated by me**, not native-speaker reviewed — F15's pipeline
  says AI-assisted translation with native-speaker driver review before release. Three new
  strings plus an empty state.
- **A co-located repair bay's phone is narrowed away** by `_contribution`, so TA Truck Service
  merging into a truck stop loses its own number. That is the established rule (the pump's
  phone describes the island, not the Flying J), and it is correct for fuel — it may be wrong
  for a service bay a driver specifically wants to ring.
- **`facility_types=[]` now means "nothing"**, which is right, but any caller that was
  relying on the old falsy-means-everything behaviour would have changed meaning. Grepped:
  m01 is the only caller.

**Closed from 109:** nothing — 109's items were the push (still open, §7.0) and the handset
(still open, §7.4).

**Carried from 109:** the label test guards ONE string · the forbidden vocabulary is
hand-maintained per locale and a seventh locale would pass vacuously.

**Carried from 108–101:** an honest "what is waiting" surface does not exist · a driver cannot
override a wrong browser timezone · no place lists every muted lot · the generic opt-in
endpoint would accept `protection_gap` · `GET /notifications/classes` returns classes with no
surface · no push has reached a real handset · `sw.js` hardcodes `/api/map/report` · the
manifest ships `"icons": []` · no push telemetry · iOS untested · `stationary_since` runs on
every ping · "claim paid" is dormant · `recovered` is terminal · `check_in`/`check_out` have
no endpoint · `trigger_time = arrival or now` · `ALERT_FRESHNESS` is a judgement ·
`dispatch_clock_alerts` costs one `clock()` per open claim · M5 expiry reminders deep-link to
a tab root · notification copy is English-only server-side.

**Carried and still open:** `/events/stream` is not flag-gated · the SSE session travels in
the query string · the SSE generator is synchronous · `_enrich` is per-pin · beliefs written
against merged ids before §23 95 · the flaky `login · pa` layout state · `/admin/facilities/*`
does not resolve merged ids · M2-FR4 does not exist · per-stop detention terms not expressible
· the profit calculator opens on invented defaults · dwell-risk thresholds unvalidated ·
`pin.shape` read by nothing · all live API keys on an internet-facing VM · **no backups** ·
**no monitoring**.

## 9. What I did NOT verify

Stated plainly, because an unverified claim in a handoff becomes law by the third session that
reads it.

- **No driver has used any of this.** The one recorded call tap is mine, from a verification
  account on the box (`a05-obs-…@example.com`, alongside `a05-verify-…` from the overlay
  check — the same kind of residue 107 left behind).
- **Only Wisconsin was re-extracted.** The other eight states still run the old filter, so
  their service rules are still starved. `make osm-extract STATE=<x>` then `make ingest-osm`
  fixes each, and each costs a ~280 MB download.
- **The name-term list was audited on ONE state.** `fleet` and `trailer` were dropped on
  Wisconsin evidence alone; both may earn their place elsewhere, and a term that is wrong in
  another state will show up as a car garage on a truck map.
- **The deployed UI was never opened in a browser.** Production was verified over HTTP —
  bundle strings, overlay payload, the call endpoint, the analytics row — and the SCREEN was
  driven only against the local stack. The two are the same build, but that is an inference,
  not an observation.
- **The six locales are not native-reviewed.**
- **The production restore was never tested.** I took a `pg_dump` before mutating the box and
  never restored it, so it is an untested backup — precisely what A12 exists to fix, and
  precisely the false comfort a backup nobody has restored provides.
- **I did not measure map render cost at the new pin density.** Wisconsin gained 33
  facilities, which is nothing; A9's national density is where `_enrich` and the 300-pin cap
  bind, and that measurement belongs to A9.
- **iOS, background location, and the F3 question in Phase DoD #8** were not touched.

## 10. Restarting

```
make up                              # the stack is UP; this is here for the next cold start
make test                            # pytest 1262 + vitest 605 — NEVER pipe it
make lint                            # ruff + import-linter 30/30
make ui-layout                       # 193 states, ~3.5 min
make repair-contact                  # dry run; DRY_RUN=0 applies (already applied in dev)
make osm-extract STATE=<state>       # re-extract with the CORRECTED filter, then ingest-osm
git push && ./scripts/deploy.sh      # six commits, and this one is driver-facing (§7.0)
```

**The standing warning, seventh form.** 104: a suite answers "does this do what it was written
to do", never "is this reachable". 105: the agreement between two components can be owned by
neither. 106: the tests kept entering where a driver cannot. 107: the code was right and the
DEFAULT was wrong. 108: the code was right and the PROSE was wrong. 109: the prose about the
prose was wrong. This one: **the code was right and its INPUT never arrived.**

Six rules, correct, tested, documented, and starved for the entire life of the project. Every
test of them passed — because a fixture hands a rule the tags the extract would never have
delivered. **A test that supplies its own input cannot tell you the input does not exist.**
The suite could not see it, the fixtures actively hid it, and the amendment written above it
said "most of this exists."

And its corollary, which cost the most time here: **the obvious fix was wrong too.** Extending
the filter — the fix the plan was approved with, and the one A9 §1 names — would have produced
exactly zero facilities, because a second gate nobody had measured was rejecting all 2,638 of
them. **Measure the fix, not only the bug.**
