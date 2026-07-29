# HANDOFF-099 — the session the map stopped drawing one place twice

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 29 July 2026 · **Stack:** UP locally (`make down` to stop) · **Deployed:**
https://haulmeter.online (GCE, project `uzimiz-prod`) — **updated and repaired this session.**

**State in one line:** 098's largest unverified claim was verified (the layout sweep is
clean), and then running the Map tab the way 098 asked found that the map drew one
truck stop as **two pins 73 m apart**, disagreeing about which chain it is, with the
fuel price on the pin that is not named after the brand — a §11.1 violation whose
mechanism had been built two years of sessions ago and applied to one facility kind.

> Read 098 first. This session is its §7 task list, in order: the sweep, the seeding
> decision, and the Map tab run — plus the deployment of what the run found.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0052_m03_claim_clock_since** (no schema change this session) |
| Tests | **pytest 1083 · vitest 502 · ruff clean · import-linter 30/30** |
| Layout harness | **161 tests, 2.4 min — RUN, CLEAN.** 098's estimate of "~200" was wrong |
| §23 decision log | **94 entries** (94 added this session) |
| Handoffs | 000 → 099 |
| Git | `main`, local only, never pushed. **2 commits** this session |
| Deployed | `haulmeter.online` — redeployed + repaired; pre-migration dump on the VM |
| Working tree | clean except untracked `collect_files.py` (not mine, left alone) |

## 2. What shipped

| Commit | What |
|---|---|
| `707d54d` | One truck stop is one pin, and the price rides it (§23 94) |
| (this one) | docs: HANDOFF-099 |

## 3. 098's task list, in order

**The layout sweep is clean — 161/161, 2.4 min.** It had not run since the harness
refactor and global chrome changed after it; 098 called this "the largest unverified
claim in this document." Nothing regressed. **Correct 098's number: the suite is 161
tests, not ~200.** The estimate predates the refactor finishing.

**Seeding: none, by owner decision.** The Perth-vs-Namangan question in 098 §7.2 is
answered — seed nothing, pan to the US. **The lone "Namangan" row is NOT evidence of
where the owner is.** It is test-fixture residue: the delivery stop of a draft load on
`record-scope@example.com`, with an armed geofence and an evidence log, six rows
created in one transaction on 26 Jul. It was left in place deliberately. Do not read it
as a location, and do not delete it without following its `f05.stop` FK first.

**The Map tab run is §4.** It is the whole rest of this document.

## 4. One truck stop, two pins, and the price on the wrong one

At the Lebanon, Indiana Flying J the API said three contradictory things:

| Preset | Before | After |
|---|---|---|
| Drive | `Flying J Travel Center` (no price) **+** `Pilot` ($5.20), 73 m apart | one pin, `truck_stop`, `~$5.20` |
| Fuel | only `Pilot` — the Flying J absent | `Flying J Travel Center` with its price |
| Tonight | the Flying J, no fuel information | same pin, with its price |

**Two independent causes, and neither was the one I first proposed.**

1. `highway=services` sat ABOVE the truck-stop rule and is how every US chain is
   tagged, so **309 branded stops filed as `rest_area` and not one facility in the
   pull was ever typed `truck_stop` from that tag**. `Preset.fuel` was
   `[fuel_station]`, so a Flying J carrying `fuel:diesel=yes` in its own tags was
   absent from the one preset built to find it.
2. **474 of 546 fuel stations** stood within 150 m of a destination that already had a
   pin — the site feature and its fuel island, ingested as two places.

**HANDOFF-076 had already diagnosed this, for scales.** It measured 239 of 253 within
150 m, called them "second pins stacked on Pilots, Love's and rest areas — precisely
what design-prd §11.1 forbids", built the co-located-amenity mechanism, and applied it
to `FacilityType.scale` alone. The fuel case is twice the size and the mechanism was
never carried across. **098 §4's recurring lesson, sixth instance.**

Nothing new was invented: `SERVICE_FUEL` joins `SERVICE_SCALE`, and `_contribution`
already narrows a co-located amenity to `UNION_KEYS`, so the island gives its host the
fuel fact **without** giving it the pump's name.

## 5. Method notes — read before trusting anything above

- **Measuring killed three of my own proposals before they were written.** Reordering
  the type rules fixes nothing (`amenity=truck_stop` appears on **zero** misfiled
  rows). `hgv` alone would have converted **135 public rest areas** into truck stops.
  And the badge, gated on the KIND, would have **deleted the price rather than moved
  it** — strictly worse than the duplicate pin it replaced.
- **I introduced a regression and caught it only by re-running the original repro.**
  Re-typing the Flying J emptied the Fuel preset entirely. `sells_fuel` is now ONE
  definition shared by the preset that shows a pin and the badge that prices it, so
  they cannot disagree. There is a test.
- **The repair was not idempotent on the first attempt.** It reported 109 sites twice,
  because `_recompute_canonical` opens with `db.refresh()` and read straight past an
  unflushed write. A second run is now a verified no-op, locally and deployed.
- **A dry run over real data found what reasoning missed.** 35 of 474 merges were
  "Flying J #695" and "TA" disappearing into "Parking Property" — the placeholder this
  code writes for an unnamed OSM feature. Those 35 are held back and **counted in the
  output** rather than hidden.
- **An `information_schema` query lied about the schema.** Asked which tables
  reference `f02.facility`, `constraint_column_usage` returned **2**. `pg_constraint`
  returns **13**. The check that passed was the wrong check; an FK error was the only
  thing that stopped a cascade through data I had not looked at.
- **A test asserted the old behaviour and was restated, not deleted** — 098's rule.
  `test_facilities_without_services_carry_no_services_key` was pinned to a fixture's
  contents; it now asserts the invariant it was protecting (absent, not empty).

## 6. Deployment

Runbook unchanged (`docs/deploy-testing-env.md`). This session:

- **A pre-migration dump was taken first** — `/opt/haulmeter/backup-20260729-024237.dump`
  (2.2 MB, `pg_dump -Fc`), because 098 §8 records that this box has no backups. It is
  on the same VM, which is better than nothing and is **not** a backup strategy.
- Deployed `707d54d`, then dry-ran the repair (identical numbers to local), then applied.
- **Applied: 368 re-typed · 553 gained the fuel service · 439 merged · 72 standalone ·
  35 held back.** `truck_stop` 1457 → **1825**, `rest_area` 1584 → **1216**,
  `fuel_station` 546 → **107**. Zero errors in the API log since.
- Repro verified live at `https://haulmeter.online/api/map/overlay`.

**Note for the next session: the API is mounted under `/api/*`** (Caddy `handle_path`
strips the prefix). `https://haulmeter.online/health` returns 200 from the SPA
fallback, not the API — it is `/api/health` that answers for the API. I wasted a cycle
on that.

`make repair-fuel` uses the LOCAL compose file; on the VM run the module directly:
`sudo docker compose -f docker-compose.deploy.yml --env-file .env exec -T -e DRY_RUN=0 api python -m scripts.repair_colocated_fuel`

## 7. Exact next task — Session 20

1. **Keep running the Map tab by hand.** §4 came from driving ONE bbox through the API.
   The corridor, the facility card, the report sheet and the saved-for-stop queue have
   not had the same treatment, and 098's §4 was the longer list for a reason.
2. **The 35 held-back pins are a data question waiting for an answer.** A branded pump
   beside an unnamed "Parking Property" is one site or two, and only a human looking at
   it can say. They render as two pins until someone does.
3. **Decide what an empty profit calculator shows** (carried from 098, unresolved).

## 8. Debt

**Closed this session:** the fuel/rest-area duplicate-pin family; the Fuel preset
missing every major chain; 098's unrun layout sweep.

**Carried from 098, still open:**
- Per-stop detention terms exist in the schema, not expressible in the UI
- **M2-FR4 does not exist** — needs an owner decision
- Evidence logs before `f3e6a86` stay polluted; the chain is append-only
- The free-time caption reported missing in one screenshot — **unreproduced**
- §11.4's heading-up follow is not implemented; §11.6's custom day/night styles are not built
- **The profit calculator opens on invented defaults** with no active load
- The dwell-risk badge thresholds (0.5, min 3) are defensible and unvalidated
- **`pin.shape`** is serialized by the overlay and read by nothing
- All live API keys sit on an internet-facing test VM
- **No monitoring.** The outage in 098 was found by the owner opening the app

**New this session:**
- **35 branded pumps still draw a second pin** beside an unnamed host, by design and
  by count. The alternative was taking the only real name off the map.
- **Three ambiguous brands** — QuikTrip, Speedway, Casey's, 1 row each — are taken by
  the branded-service-area rule. `hgv=yes` on `highway=services` is a fair reading of a
  truck stop; special-casing three rows would be taste rather than evidence.
- **`Pin.services` is populated and deliberately NOT serialized.** It gates the badge
  server-side. If a future session wants it on the client, that is an API change with a
  §22 question attached, not a free one.
- **The deployed backup is a file on the box it backs up.** One `pgdata` volume, one VM.
- **A truck stop with no fuel evidence shows no price**, which is honest and means a
  Love's we have no pump data for looks the same as a dry lot. The fix is data, not code.

## 9. Key files touched

```
API  f02/ingest/adapters.py   SERVICE_FUEL; _osm_sells_diesel; _osm_is_branded_service_area
                              (brand+hgv, measured); placeholder_name; colocated fuel
     f02/domain/service.py    fuel_station OUT of COLOCATED_HOST_TYPES (no amenity chaining);
                              merge_would_lose_the_only_name
     f02/ingest/pipeline.py   the name guard on the 2b co-location branch
     f11_map/domain/service.py Pin.services + CorridorEntry.services (server-side only)
     m01_map/domain/service.py sells_fuel — ONE definition; Preset.fuel filters on it
     api/m01_map.py           badge gate keyed on the SERVICE, not the kind
     scripts/repair_colocated_fuel.py  NEW — 3 passes, idempotent, dry-run default
TEST f02/test_ingest_fuel.py  NEW — 14 tests incl. the 135-rest-area negative
     api/test_map_api.py      the badge follows the merge; the preset finds it; no coverage badge
DOCS design-prd §23 entry 94 · Makefile repair-fuel
```

## 10. Restarting

```
make up                              # local stack
make test                            # 1083 pytest + 502 vitest
make ui-layout-only STATE=<screen>   # ~45 s
make ui-layout                       # full sweep — 161 tests, 2.4 min
make repair-fuel                     # DRY_RUN=0 to apply. Idempotent
./scripts/deploy.sh                  # push the working tree to haulmeter.online
```

**The standing warning, earned a different way this session.** 1,066 tests, a clean
layout harness and a green CI all agreed the map was fine while it drew one truck stop
as two places and hid the price behind the wrong name. The defect was found by asking
the API what a driver would see at one specific interchange — and every subsequent
correction, including a regression I introduced myself, came from **measuring the real
4,568 rows rather than reasoning about them.** Three of my own proposals died that way
before a line was written. Reading the code against the constitution finds what is
wrong in principle; running it against real data finds what is wrong in fact.
