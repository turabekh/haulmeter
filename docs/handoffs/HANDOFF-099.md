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
| Tests | **pytest 1087 · vitest 502 · ruff clean · import-linter 30/30** |
| Layout harness | **161 tests, 2.4 min — RUN, CLEAN.** 098's estimate of "~200" was wrong |
| §23 decision log | **96 entries** (94, 95, 96 added this session) |
| Handoffs | 000 → 099 |
| Git | **PUSHED to `github.com/turabekh/haulmeter` — see §11.** 6 commits this session |
| Deployed | `haulmeter.online` — redeployed + repaired; pre-migration dump on the VM |
| Working tree | clean except untracked `collect_files.py` (not mine, left alone) |

## 2. What shipped

| Commit | What |
|---|---|
| `707d54d` | One truck stop is one pin, and the price rides it (§23 94) |
| `b1a5eeb` | docs: HANDOFF-099 |
| `a8d28e6` | A merged `facility_id` resolves to the site it belongs to (§23 95) |
| `9f37b4c` | docs: HANDOFF-099 second half |
| `d68a111` | An unnamed host adopts the pump's name instead of losing it (§23 96) |
| (this one) | docs: HANDOFF-099 third half — the push |

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

## 4b. The defect the fix created work for — a merged id read as its own shadow

**Continuing to drive the Map tab found a defect in what §4 had just shipped**, which
is the whole argument for doing it. The repair scripts promise "nothing is deleted, so
every `facility_id` anyone already holds still resolves" — and **I repeated that
sentence in the commit message and in this document before testing it.**

It is half true. The row survives, so a lookup answers **200 rather than 404 — with
the wrong place.**

```
GET  /public/facility/<merged id>  ->  200  "Pilot" / fuel_station
                                              (not "Flying J Travel Center" / truck_stop)

POST /map/report {facility_id: <merged id>, status: "full"}
     ->  200 {"submission_id": "…"}      the driver is told it landed
     ->  canonical pin still status=None  nobody will ever see it
```

`resolve_canonical` has existed since F2 and was called by **the ingest pipeline and
nothing else.** The write paths matter more than the reads: the M7 crowd price confirm,
M10's leaving-broadcast and questions, and M2's reviews were all silently addressed to
a pin that is gone. §11.7 exists to stop an absence being rendered as a result; this
rendered a *discarded write* as a successful one.

**678 rows are merged — 239 from the 076 scales repair, 439 from §4.** So the exposure
predates this session by many sessions and **this session tripled it.** It is bounded:
live queries already exclude merged rows, so only a client holding a PRE-merge id can
hit it — a saved lot (§11.4), a deep link, a notification, a cached pin. That is
exactly the set §13.5 requires to keep working.

Fixed by one `canonical_facility_id` dependency at the API composition layer (the ID is
what needs correcting, not the object — most callers pass the UUID to tables of their
own). Ten driver-facing path routes plus four body-carried writes. **The three
`/admin/facilities/*` routes are excluded on purpose:** an operator must be able to
address a shadow row directly, or a bad merge cannot be undone.

## 4c. The 35 held-back pins — merged, with their names

**Owner decision (§23 entry 96), reversing the conservative half of §4.** Entry 94 held
35 pumps back from merging because their hosts were unnamed OSM features, and merging
would have taken "Flying J #695", "TA", "Kwik Trip" and "Speedway" off the map.

**Entry 94 framed it as a binary — lose the name or keep two pins — and it was not
one.** The merge can carry the name across: the host adopts it, the site ends as ONE
pin holding the only real name anyone wrote for it. The third answer needed no new
mechanism, only the willingness to rename a placeholder. What entry 94 was actually
protecting is narrower than it claimed, and is untouched: **a host with a REAL name is
never renamed after its tenant.** A test holds each half separately.

**Applied locally and deployed: 35 merged, 34 adopted.** The counts differ by one
because two pumps shared a single unnamed host — the first renamed it, and the second
correctly declined to rename a host that by then had a name. That is the rule working.

Adopted sites **keep their original kind**: a lot named "Kwik Trip" stays
`parking_property`. A pump does not prove the site around it is a truck stop, and the
fuel SERVICE already gets these onto the Fuel preset without a second unmeasured
decision.

`fuel_station` is now **72** — the genuinely standalone ones — down from 546.

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
- **The §4b tests were proved RED before being trusted.** The resolver was temporarily
  stubbed to return its input; both failed; it was restored and both passed. A test
  written against a bug you have just fixed passes for free otherwise — §23 entry 42's
  shape, and 098 §5 recorded the same species.
- **I mis-verified my own fix and nearly recorded it as broken.** Checking §4b live, the
  reported pin still read `status=None` — because I had picked an arbitrary merged row
  with `limit 1` and then queried the overlay at the *Lebanon* coordinates. It was a
  different Flying J, 200 km away. Querying at the facility's own coordinates showed
  `status='full'`. **The verification was wrong, not the code**, and the only reason I
  found that out was reading the id in the response instead of the name.

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

1. **Keep running the Map tab by hand — it is two for two.** §4 came from driving one
   bbox through the API; §4b came from driving the surfaces around it and found a
   defect in §4's own shipped work. **Still untouched: the corridor stack, the report
   sheet, the saved-for-stop queue, and the facility card in the UI** (the API behind
   it has now been exercised; the screen has not).
2. **Ask whether CLAUDE.md rule 3 should be amended** now that the repo is public and
   44 commits are pushed (§11). It is stale either way and must not be guessed at.
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
- **Adopted sites keep their original KIND** — a lot named "Kwik Trip" is still
  `parking_property`. Deliberate (§23 96): a pump does not prove the site around it is
  a truck stop. If the map should reclassify them, that is a measured decision nobody
  has made.
- **Three ambiguous brands** — QuikTrip, Speedway, Casey's, 1 row each — are taken by
  the branded-service-area rule. `hgv=yes` on `highway=services` is a fair reading of a
  truck stop; special-casing three rows would be taste rather than evidence.
- **`Pin.services` is populated and deliberately NOT serialized.** It gates the badge
  server-side. If a future session wants it on the client, that is an API change with a
  §22 question attached, not a free one.
- **The deployed backup is a file on the box it backs up.** One `pgdata` volume, one VM.
- **A truck stop with no fuel evidence shows no price**, which is honest and means a
  Love's we have no pump data for looks the same as a dry lot. The fix is data, not code.
- **Beliefs written against merged ids before §4b are still attached to shadows.** The
  resolver fixes new writes; it does not walk the F10 rows already misfiled. The count
  is small (only pre-merge clients could produce them) but it is not zero, and no
  repair pass exists for it.
- **`/admin/facilities/*` deliberately does NOT resolve.** That is correct — an
  operator must be able to reach a shadow row — but it means an admin URL and a driver
  URL for the same id now answer about different facilities. Anyone adding an admin
  facility route should decide which behaviour they want rather than inherit one.
- **Unnamed OSM features render as "Parking Property" / "Rest Area" on the map.** Seen
  live while verifying §4b on the deployed box: a merged id resolved to a host actually
  named `Parking Property`. Pre-existing and not introduced here — the §4 name guard
  prevents NEW ones from absorbing a brand — but those placeholder names are on the map
  today and a driver cannot search for them.

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
     api/deps.py              NEW canonical_facility_id — the resolver dependency (§4b)
     api/{public,m02,m07,m08,m10,m12,m13}.py  10 path routes + 4 body writes resolve
TEST f02/test_ingest_fuel.py  NEW — 14 tests incl. the 135-rest-area negative
     api/test_map_api.py      the badge follows the merge; the preset finds it; no
                              coverage badge; a merged id reads and REPORTS as its site
DOCS design-prd §23 entries 94, 95 · Makefile repair-fuel
```

## 11. The repo is now PUBLIC — and CLAUDE.md still says never push

**Owner instruction, 29 July 2026: 44 commits were pushed to
`https://github.com/turabekh/haulmeter`, which is a PUBLIC repository.** It was a clean
fast-forward (`0 44`, no divergence, no force). The whole codebase, the PRD, the design
constitution and every handoff 000–099 are now readable by anyone.

**This directly contradicts CLAUDE.md working rule 3 — "Local commits only. NEVER
push."** I raised the conflict and the repo's public visibility before doing it and the
owner confirmed; that is why it happened. **I have NOT edited CLAUDE.md**, because one
authorised push is not the same instruction as "pushing is now always allowed", and
rewriting a governing rule on that inference is exactly the kind of silent
reinterpretation the constitution forbids. **Rule 3 is therefore stale and known to be
stale.** The next session must not treat it as settled either way — ask the owner
whether it should be amended, and log the answer.

Two things that follow from the repo being public and are worth a decision:

- `docs/deploy-testing-env.md` is now public and names the **instance, zone, static IP
  and firewall rules** of a live internet-facing box. No credential — but it is a map
  of the machine. I flagged this before pushing.
- Pre-push scan found **no secrets**: only `infra/.env.example` is tracked, and no key
  patterns or literal credentials appear in the 44-commit diff. Rule 9 held.

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

**And the sharper version, from §4b.** The sentence "nothing is deleted, so every
`facility_id` anyone already holds still resolves" was inherited from a script that
had been true for two years, repeated into a commit message, and written into this
handoff — **before anyone asked the API whether it was so.** It was half true, and the
half that was false told drivers their reports had landed when they had been thrown
away. A claim carried forward is not a claim tested. The next session should assume
the same of anything written here.
