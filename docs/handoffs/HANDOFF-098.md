# HANDOFF-098 — the session the map stopped inventing, and the product left the laptop

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 28 July 2026 · **Stack:** UP locally (`make down` to stop) · **Deployed:**
https://haulmeter.online (GCE, project `uzimiz-prod`).

**State in one line:** the Map tab was rebuilt from a screen showing **three invented
facilities from a fixture** in the one state a driver cannot check anything, into one
served entirely by its own API — and then the whole product was deployed to a real
domain, where the first thing it did was reveal a bug only a deployment can find, and
the second was to fall over under one phone.

> Read 097 first for the Load-tab QA run that preceded this. This session is the Map
> tab in four owner-approved slices, then everything the owner found by *looking at it*,
> then the deployment.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0052_m03_claim_clock_since** (no schema change this session) |
| Tests | **pytest 1066 · vitest 502 · ruff clean · import-linter 30/30** |
| Layout harness | **~200 tests, ~3 min** (was 681 / 11 min) — **NOT run since the refactor** |
| §23 decision log | **93 entries** (81–93 added this session) |
| Handoffs | 000 → 098 |
| Git | `main`, local only, never pushed. **13 commits** this session |
| Deployed | `haulmeter.online` — valid TLS, 4,573 facilities, 160 accounts |
| Working tree | clean except untracked `collect_files.py` (not mine, left alone) |

## 2. What shipped

| Commit | What |
|---|---|
| `3ca1f3d` | Corridor served, not invented; heading captured (§23 81) |
| `d20bced` | `rate_cents` + `accessorial_terms` finally stored (§23 84) |
| `1796469` | Profit calculator reads the load it was opened from (§23 85) |
| `ed33989` | Facility card measured at 360 dp; CTA ladder made provable |
| `d56e377` | Basemap pairs with the theme; saved lot gets coordinates (§23 86) |
| `15c5830` | **M2-FR3 implemented** — §11.2's clock badge has a signal (§23 87) |
| `3ae7966` | Harness: 5 page-loads → 1 per state; the "squished" fix (§23 88) |
| `d6df821` | Denser map top: icon chips, strip gone, corners cleared (§23 89) |
| `e60718c` | Voice reports *why* it failed; one owner per corner (§23 90) |
| `bfbc959` | A mic that cannot work stops calling itself available (§23 91) |
| `fcd713e` | **Deployment** to GCE at haulmeter.online (§23 92) |
| `c2db1b7` | DB copy procedure + two testing accounts |
| `0c26859` | **Outage fix** — geolocate storm exhausted the DB pool (§23 93) |

## 3. The Map tab, in the order it mattered

**Corridor mode was a fixture.** `MapSurface` passed a hardcoded `SAMPLE_CORRIDOR` —
"Pilot #77 · full · 3.4 mi" and two more — into the DRIVING screen, while
`GET /map/corridor` had sat unreached since M1 shipped. Not a capability with nothing
reaching it; a **lie** where an absence should have been. A driver at 65 mph was being
told a specific truck stop 3.4 miles ahead was full.

**And "ahead" meant due north for everyone.** `location.js` recorded lat, lon, accuracy
and speed and dropped `coords.heading`, so the only heading in the product was the
literal `0` two API calls defaulted to. Verified live after the fix — four headings,
four different answers; before it, all four returned the 0° result.

**M2-FR3 was specified into a module that cannot compute it.** `m02.detention_risk`
returned `basis: "m3_pending"` and had since M2 shipped. It read as a scheduling matter
waiting on M3. It was not: the FR says the indicator is "derived from M3 claim events"
and import-linter orders M2 **before** M3, so M2 can never read a claim. **Two tests
were holding the stub in place** — a placeholder plus a test *of* the placeholder is
indistinguishable from a finished feature at the level of a green suite.

Also closed: `rate_cents` and `accessorial_terms`, the sixth and seventh parsed values
found reaching no field. **Every neighbour in `parsed` was checked and the list is now
empty** — that family, seven instances over six sessions, is done. On the way it turned
out `m04.check_accessorial_terms` had been judging every load in production against an
empty dict.

## 4. What the owner found by looking at it

Every one of these came from a screenshot or a sentence, not from a test.

| Report | What it actually was |
|---|---|
| "the top is a little too squished" | three stacked controls all had `margin: … 0` on the **bottom**; the last one ended at exactly the y the canvas began (both 232) |
| "still overlapped and confusing" | four controls from two owners in one corner. Took **three attempts** — each move traded one collision for another until I measured after every one |
| "listening but it is not working" | `start()` swallowed a synchronous throw, so `onerror` never fired and `listening` stayed true forever over a mic that never opened |
| "listening **still** not working" | `recognitionSupported()` tested whether the constructor EXISTS. Chrome exposes it over plain http and then refuses to start one |
| "server is down" | one phone's GPS stream exhausted the DB connection pool |

**The lesson that recurs:** in four of five, the correct discipline already existed ten
lines away and had not been carried across. `location.js` throttles its own pings and
explains why; Mapbox's geolocate control is a *second* position stream that inherited
none of it. The Docs capture chip was once caught by the shortest-locale width rule —
and the new `$` badge and the saved-sheet Remove were caught by that same rule again,
twice, in this session.

## 5. Method notes — read before trusting anything above

- **The layout harness caught two violations in code minutes old**, both mine: a badge
  at a hardcoded `10px` under §6.2's floor, and a 44×48 dp control in Punjabi under
  §6.5. Neither was visible to 502 unit tests.
- **A new test passed for the wrong reason.** The corridor/pin price-agreement test
  compared two `None`s in a database with no fuel rows and went green — §23 entry 42's
  shape. It now seeds a station and asserts the badge *exists* before comparing.
- **Slice D falsified one of Slice A's own tests.** `"nothing in the stack is a
  control"` was true when written and wrong four hours later. Restated to the invariant
  it was protecting, not deleted.
- **I raised the harness workers 2→4 without raising the timeouts**, then spent a cycle
  investigating three "failures" in which nothing was wrong. A test now covers five
  evaluations; the budgets were tuned for the old shape.
- **Measuring beat guessing every time.** Every layout complaint was resolved by reading
  boxes at 360×800, not by looking at the screenshot — and the corner fix needed three
  measured rounds because two of my answers were wrong.
- **The full layout sweep has NOT been run since the harness refactor**, and global
  chrome changed after that. **This is the largest unverified claim in this document.**

## 6. Deployment

Full runbook in `docs/deploy-testing-env.md`. Essentials:

| | |
|---|---|
| Instance | `haulmeter-test`, e2-medium, `uzimiz-prod` / **`us-central1-a`** (zone b was out of capacity) |
| IP | `136.65.58.211` (static, regional) |
| Firewall | `haulmeter-test-web` — **tcp:80/443 only**; everything else is compose-internal |
| Deploy | `./scripts/deploy.sh` — bundles the working tree, copies, rebuilds |
| Cost | ~$28–30/month |

**Accounts.** Passwords were handed over in chat and are deliberately written nowhere —
F1 offers no `set_password` by design, so a lost password means a new account.

- `driver@haulmeter.online` — `driver`
- `admin@haulmeter.online` — `driver` + `platform_admin`

Verified that the driver is **refused** `/admin/flags` with 403, not merely that the
admin is allowed. A role that grants nothing looks identical to one that grants
everything until someone tries the door.

**Two deployment traps, now encoded in `scripts/deploy.sh`:** macOS `tar` writes binary
AppleDouble sidecars (`._name`) and alembic globs `versions/*.py`, so
`._0001_f01_identity.py` was imported as Python and the API restart-looped on *"source
code string cannot contain null bytes"* — pointing at a migration that was fine. **678
rode along.** And `api/data` is ingest source, read only by `make ingest-*`; including
it made the first bundle 889 MB instead of 1.8 MB.

## 7. Exact next task — Session 19

1. **Run the full layout sweep** (`make ui-layout`, ~3 min now) and fix what it finds.
   It has not run since the refactor, and global chrome changed after that.
2. **Ask the owner where to seed demo data, then seed it.** Their GPS reported **Perth,
   Australia** (`-31.814, 115.964`) in the deployed request logs, while the only
   non-US facility in the database is "Namangan" in Uzbekistan — where I seeded a
   cluster on the assumption that was them. **One of those is wrong and I do not know
   which.** The US data (3,726 facilities, densest around Indiana/Ohio/Illinois) is
   intact and visible by panning there.
3. **Run the Map tab the way 097's owner ran the Load tab.** Every defect in §3 came
   from reading code against the constitution; every defect in §4 came from *using it* —
   and §4 is the longer list.

## 8. Debt

**Carried from 097, still open:**
- Per-stop detention terms exist in the schema, not expressible in the UI
- **M2-FR4 does not exist** — needs an owner decision
- Evidence logs before `f3e6a86` stay polluted; the chain is append-only
- The free-time caption reported missing in one screenshot — **unreproduced, do not
  "fix" it without seeing it**

**New this session:**
- **§11.4's "map locks to heading-up follow" is not implemented.** Corridor mode replaces
  the map rather than following it. Heading exists now, so this is buildable.
- **§11.6's custom day/night styles from §6.1 tokens are not built.** The basemap pairs
  with the theme (§23 86); it is still Mapbox Standard's own `lightPreset`.
- **The profit calculator opens on invented defaults** (`revenue 2000 / miles 500 /
  tolls 30`, fixed `mpg 6.0`) with no active load — money on a screen nobody entered,
  the shape §23 entry 52 removed from the Load tab. What an *empty* calculator should
  show is a product decision, not a passing one.
- **The dwell-risk badge thresholds are a guess** — 0.5 over a minimum of 3 finished
  stops. Both defensible, neither validated against a real map.
- **`pin.shape`** is serialized by the overlay and read by nothing.
- **All live API keys sit on an internet-facing test VM** (owner's decision, recorded in
  the deploy doc). A restricted Anthropic key would be cheap insurance.
- **The deployed box has no backups.** `pgdata` is a Docker volume on one VM. For a
  testing environment that is a choice — but it is a choice, not an oversight.
- **No monitoring.** The outage was found by the owner opening the app. Nothing would
  have told us first.

## 9. Key files touched

```
API  m01_map/service.py       corridor_ahead (status per facility kind, capped at 3)
     m03_detention/service.py facility_detention_stats — M2-FR3's real source
     m02_facility_intel       detention_risk stub REMOVED (unimplementable there)
     api/m01_map.py           /corridor rewritten; _fuel_badge, _dwell_risk_badge
     api/load.py              /load/active names the dock; meter carries rate_cents
     api/m02_facility_intel   composes M3's stats into the profile response
     core/db.py               pool 10+20, pool_recycle (§23 93)
     core/config.py           cors_origins
UI   core/location.js         heading: coords.heading, else derived bearing
     core/presentation.js     placeLabels (§11.5), ageLabel, basemapPreset (§11.6)
     core/map-presets.js      NEW — preset persistence per driver state
     core/saved.js            NEW — §11.4 save-for-stop queue
     core/speech.js           secure-context guard, failure taxonomy
     core/api.js              API_BASE from env (§23 92); fetchCorridor
     MapCanvas.vue            §11.2 badge slots; theme pairing; attribution moved
     CorridorStack.vue        server data, price, deferred-safe tap
     FacilityCard.vue         "your stop" rung; dwell rate; CTA ladder modifiers
     MapSurface.vue           corridor, heading, saved chip, presets, throttled locate
     PresetChips.vue          icons + aria-labels + filled selection
     StatusStrip.vue          state label and dead mic REMOVED
     LoadCalcSurface.vue      prefills from the load it was opened from
INFRA docker-compose.deploy.yml · Caddyfile · ui/Dockerfile · scripts/deploy.sh   NEW
DOCS design-prd §23 entries 81–93 · deploy-testing-env.md · user-guide-load-and-docs.md
```

## 10. Restarting

```
make up                              # local stack
make test                            # 1066 pytest + 502 vitest   (~2 min)
make ui-layout-only STATE=<screen>   # ~45 s — the one you want while building
make ui-layout                       # full sweep — RUN IT ALONE, and rarely
./scripts/deploy.sh                  # push the working tree to haulmeter.online
```

**The standing warning, earned three separate ways this session.** The corridor was a
fixture for months behind a green suite. M2-FR3 was a stub held in place by two tests
that asserted the stub. And the API fell over under a single phone, because a rule
written carefully in one file was never carried to the second place it applied.
**1,066 tests and a layout harness caught none of the three.** The owner found the last
by opening the app; the first two were found by reading the code against the
constitution and asking what each line actually did. Neither method is optional, and
neither is sufficient alone.
