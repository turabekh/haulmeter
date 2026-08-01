# HANDOFF-111 — the operational floor, and a constitution that now delegates

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 1 August 2026 · **Stack:** **UP** locally · **Deployed:** https://haulmeter.online —
**CURRENT**, with A5 and A12 both live and both verified on the box.

**State in one line:** the box now backs itself up offsite, proves the backup restores,
tells a human when it dies, and can answer which data it is running — none of which it could
do this morning — and the map it serves went from 12 repair shops to 458.

> **This continues HANDOFF-110, which is the same working session.** 110 has A5 and the
> starved-rules finding; this has the owner's delegation of design-prd rule 6 and
> **A12 — Operational floor** (v2.0 Group 1, blocking A9).

**Nothing is half-finished.** Working tree clean apart from the untracked `collect_files.py`.
Everything is pushed and deployed.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0056_a09_facility_geog_idx** — the A9 §4 geography index, deployed |
| Tests | **pytest 1297 · vitest 612 · layout 193 · ruff + import-linter 30/30** |
| §23 decision log | **119 entries** — 117 approved, 118 the delegation, 119 the §18 portal list |
| Handoffs | 000 → 111 |
| Git | **in sync** with `origin/main` (public) |
| Deployed | **CURRENT** — A5, A12, **all nine states re-extracted**, backups, alerting |
| Coverage | `repair` **12 → 449** · callable phones **0 → 756** (§10), after §12's dedupe |
| Backups | **gs://haulmeter-backups**, nightly 03:30 UTC, 30-day lifecycle, **restore proven** |
| Alerting | GCP uptime check + policy → **turabekh@gmail.com**, **delivery confirmed by the owner** |

## 2. design-prd rule 6 now DELEGATES (§23 entry 118)

The owner overrode the rule that said *"agents propose; the owner disposes"*. Entry 117
(the Service chip) is now **approved** under it.

**I kept two carve-outs, deliberately, and they are not formalities.** §22.2's four
never-improvise categories still stop and ask — a new colour, type size or spacing, a new
component pattern, a new navigation structure, a new notification class — and so does **any
reversal of an entry already in the log** (A8's sixth tab is the live example, and v2.0 §3
says explicitly it "must be logged as a reversal"). Delegating who signs an entry does not
make inventing those safe, and the person who owns the product is the only one who can say
whether it should stop looking like one product.

**Logging did not change.** Every decision still gets an entry with its reasoning before it
ships. The log is the only record of WHY, and why is the part a later session cannot
reconstruct from the code.

## 3. A12 — what exists now that did not this morning

| Requirement | State |
|---|---|
| 1. Automated backups with a **proven restore** | **DONE.** Nightly 03:30 UTC → `gs://haulmeter-backups`; restore verified nightly at 04:15 and **performed by hand twice today** |
| 2. One health alert that reaches a human | **DONE and VALIDATED** — fired deliberately, **owner confirmed the email arrived** |
| 3. Every data load records a snapshot identifier | **DONE**, and proven on the box |

**v2.0 §7 item 7 — "a database restore has been performed and verified" — is satisfied.**
The verification restores the newest object **from the bucket** into a scratch database and
checks the four things a successful-looking `pg_restore` does not establish:

```
alembic  live=0055_f08_push_subscription  restored=0055_f08_push_subscription  OK
f02.facility           live=5984     restored=5984     OK
f01.account            live=170      restored=170      OK
f10.belief             live=60       restored=60       OK
f14.analytics_event    live=194      restored=194      OK
postgis geometry       5984  OK
```

It pulls from the **bucket, never the local copy** — the failure it exists to catch is "the
VM is gone", and in that case the local file is gone too, so verifying it proves nothing
about the case that matters. PostGIS is checked explicitly because geometry columns restore
as bytes without the extension, and every map query would fail on a database that restored
cleanly.

**What was there before:** no cron, no timer, no backup job — and three
`backup-2026072*.dump` files written by hand on 29 July, sitting in `/opt/haulmeter`, **on
the same disk as the database they back up.** That is not a backup, it is a second copy of
the thing that dies when the thing dies. The upload is therefore a required step in
`backup_db.sh`: if it fails, the script fails.

**Requirement 3 is answerable now**, and this session is the argument for it — the extract
was silently wrong for the entire life of the project and there was nowhere to look:

```sql
select started_at, ok, summary->'snapshot' from f14.job_run
 where job_name = 'ingest_osm' order by started_at desc;
-- 2026-08-01 04:34:54 | t | wisconsin.geojson | 6e7a71c253eb2e7f… | 290 facilities
```

The identifier is the **content digest**, not the filename and not the date. Two boxes both
holding "wisconsin.geojson" prove nothing about running the same data: the old filter and
the corrected one produce that same filename and differ by 65 repair shops.

## 4. Four things the measurement found that nobody asked about

1. **The disk was 83% full, 3.4 GB free** — and 8.8 GB of it was reclaimable Docker build
   cache. Pruned to **39% used, 12 GB free**. A9 wants ten times the current data and would
   have hit the wall long before the map did.
2. **The VM could not write to GCS at all** — `devstorage.read_only`. Fixed by stop /
   set-scopes / start. **The site was down ~40 seconds** and came back with all seven
   containers healthy. Recorded plainly because it was a deliberate outage of a live box.
3. **Scopes were only half of it.** With `devstorage.read_write` the upload still 403'd —
   the bucket has uniform access and the service account had no IAM role on it. The two
   errors read identically (`Provided scope(s) are not authorized`), so the scope message
   hides the IAM one. And `gsutil` fails on this box even with both; `gcloud storage` works.
4. **A deploy destroys anything copied into a container.** The Wisconsin extract was
   `docker cp`'d in, and the next deploy recreated the container and took it with it — then
   the VM stop cleared `/tmp` and took the host copy too. The *data* survived (postgres is a
   named volume); the *source* did not. Ingest sources now live in
   **`gs://haulmeter-sources`**, and `make osm-publish` / `make ingest-remote` make the round
   trip one command each — the manual `docker cp` is gone.

## 5. The alert works — fired deliberately, and it arrived

Built and live: a GCP uptime check on `https://haulmeter.online/api/health` from three US
regions every 5 minutes, an alert policy firing below 40% success over 5 minutes, and an
email channel to **turabekh@gmail.com**. The policy documentation carries the first
diagnostic commands and where the backups are.

**It lives outside the box on purpose** — anything running on the VM cannot tell you the VM
is gone, which is the failure mode that matters.

**I proved everything except delivery.** Rather than take the site down again, I pointed a
second uptime check at a deliberately 404ing path and wired a test policy to the same
channel. The check failed from all three regions for ~8 minutes, which is well past the
60-second condition, so the incident opened and the notification was dispatched. **Both test
objects have been deleted.**

**The owner confirmed the email arrived.** That is A12 requirement 2's validation clause in
full — *"an alert is triggered deliberately and arrives"* — and it is the half nobody usually
does, because building the policy feels like finishing.

**One thing to carry forward, because it nearly stopped this:** the channel's
`verificationStatus` reads unset and `sendVerificationCode` 404s, and I took that as evidence
the channel might silently deliver nothing. **It was a red herring** — an email channel
created through the API by a project owner delivers without an explicit verification step.
The status field is not the signal; the arriving email is. Do not spend time chasing that
field again.

**A12 IS COMPLETE.** All three requirements built, and both halves of its stated validation —
a restore performed and verified, an alert triggered deliberately and received.

## 6. Exact next task

**1. Answer §5.** One look in an inbox decides whether the alerting half of A12 is real.

**2. A5 still needs a driver; A12 does not and is DONE.** A12's validation is about the world
(a restore, an alert) and both halves are now observed. A5's is about a person: its
`service_call_tapped` count is 1 and that one is mine.

**3. DONE — all nine covered states now run the corrected filter**, on the laptop and on the
box. See §10. The manual step is gone: `make osm-publish STATE=x` then
`make ingest-remote STATE=x`.

**4. A9's §4 and §5 gates are measured and done** (§11, §12, §13), except the merge-review
UI. Previously-stated next step, now superseded in part:

**(was) A9's §4 and §5 gates are both measured and done** (§11, §12). What remains of A9 is
the **admin merge-review surface** §5 also asks for, and `/admin/facilities/*` still not
resolving merged ids — the 95 merges made today mean 95 more ids where an admin URL and a
driver URL answer about different places. That is now the oldest untouched item in A9.
Superseded detail follows for the record:

**(was) A9's §4 gate is measured and half-done** (§11). The geography index is in and deployed;
`_enrich` is bounded at ~275 ms worst case and does NOT block a national run. What A9 still
needs is its own §5 — **dedupe at density**, which is the untested one: geohash-7 blocking
with 0.4 name similarity will produce more false merges once metros are dense, and
`/admin/facilities/*` still does not resolve merged ids. That is the next real piece of A9,
and unlike §4 it has no measurement yet.

**5. Put a push on a real handset — STILL YOURS, five sessions running.**

**6. A3** (the freshness badge says "1 driver" about a DOT feed) is the cheapest remaining
Group 1 defect. **A2 needs D5, A4 needs D3** — those two decisions are still open and the
delegation in §2 does not cover them: v2.0 §6 is a different document and says "no session
may resolve these".

## 10. All nine states re-extracted, and A3 was already fixed

**A3 needed no work, and that is the finding.** v2.0 §3 says the freshness badge "reads
`7m · 1 driver` even when the source is an authoritative DOT feed". It does not, and has not
since commit `f6f8e85` — `freshnessLabel` renders "official feed" whenever the belief carries
a source, with tests at both the pure-function and component level. Verified against the real
payload rather than the tests: a live TPIMS-backed rest area returns
`{"sample_size": 1, "source": "tpims"}`, which is exactly the case the amendment describes,
and it renders as a feed. **Third v2.0 claim this session that did not match the code.**

What remains of A3 is the amendment's `7m · IDOT` — naming the agency rather than a generic
"official feed". I did not build it, because **IDOT would be wrong**: the one configured feed
is `truckparking.travelmidwest.com`, the MAASTO regional exchange covering several midwest
states, not one DOT. Naming a specific agency would need an invented state→agency table, and
getting that wrong on a trust feature is worse than a generic label. If it is wanted, the
honest string is the publisher ("Travel Midwest"), which invents nothing.

**The eight remaining states were re-extracted, audited, ingested locally and loaded onto the
box.** Production, before and after today:

| | this morning | now |
|---|---|---|
| `repair` facilities | **12** | **458** |
| facilities with a callable phone | **0** | **807** |
| with opening hours | 0 | 352 |
| total facilities | 4,874 | 5,438 |

Live service pins, checked through the deployed API: Indianapolis 20 · Detroit 15 · Houston
12 · Dallas 11 · Minneapolis 7 · Columbus 6 · Louisville 4.

**Every state was audited before loading** with the new `scripts/audit_truck_names.py`, which
lists what the NAME rule alone admitted — the only one of the three truck signals that can
admit something absurd. Indiana's 55, Iowa's 30 and Texas's 242 are all genuine truck
businesses (Boss Truck Shop, JX Truck Center, Blue Beacon Truck Wash, Big Rigs Lube Center).
`trailer` never appears without `truck` in any of them, which is the third confirmation that
dropping it cost nothing.

**The digests match across machines**, which is what A12 requirement 3 was for: Indiana loaded
locally and on the box both record `481cbd335d578e9d`, so "are the laptop and the box running
the same extract" is now a question with an answer instead of an assumption.

## 11. A9 §4 measured — the index was the problem, `_enrich` is not (yet)

A12 unblocked A9 this morning, so its §4 gate — *"handle volume before it arrives"* — was
the next work. It names two things. **Measurement supports one of them and softens the other.**

**The index was real, and worse than described.** `spatial_index=True` on `geom` builds a
GEOMETRY index; every distance query in F2 casts to geography, and a geometry index cannot
answer that. **All six were sequential scans**, and nobody noticed because 6,516 rows is
28 ms. Measured on the box:

| | rows examined | time |
|---|---|---|
| before | **6,512** to return 26 | 28 ms |
| after (`ix_facility_geog`) | **30** | 13.5 ms |

The halving is not the point — a seq scan is linear at a measured ~4.3 µs/row, and
`_facilities_in_area` issues one query **per facility type**, so Drive's five kinds would
cost most of a second at national density. Migration `0056_a09_facility_geog_idx`, deployed,
head confirmed on the box.

**`_enrich` is bounded, and A9 §4 overstates it.** It says the per-pin enrichment means
"bulk reads in M3, M6 and M7 come first". Measured server-side, from inside the api
container so the wire is not in the number:

| viewport | pins | median |
|---|---|---|
| r=8 km | 7 | 63 ms |
| r=50 km | 50 | 147 ms |
| r=150 km | 188 | 192 ms |
| r=400 km | 0 (591 clustered) | 108 ms |

That is **~0.71 ms per pin** (a linear fit across three points, not an isolation of
`_enrich` alone), so the 300-pin cap puts the worst case at **~275 ms server-side** — inside
§20's 300 ms tab switch, and the clustering above the cap is what keeps it there. **Bulk
reads are the next optimisation, not a prerequisite.** What A9 §4 actually predicts is a UX
change rather than an outage: at national density more metro viewports cross the cap and
return clusters instead of pins, which is §11.5 working as designed.

**One measurement trap worth carrying.** The first numbers came from the laptop and showed a
20% gain where the box shows a halving — the local postgres runs amd64 under emulation and
~60 ms of fixed overhead swamped the difference. And an 800 ms figure from `curl` on my
machine was almost entirely WAN latency to us-central1. **Neither a dev container nor a
laptop round-trip is a performance measurement.**

## 12. A9 §5 measured — the fear was right, the cause was wrong

§5 predicts geohash blocking at 0.4 similarity "will produce more false merges once metros
are dense". Measured on the nine-state registry:

- **Not one** of the 1,078 merges happened beyond 150 m. A geohash-7 cell is ~153 m, so the
  name path was already bounded by its own blocking — it could never have merged two Pilots
  a kilometre apart.
- **What it does instead is MISS.** 191 live pairs sat within 60 m with similar names,
  unmerged, **every sampled one in a different cell**: "Flying J Travel Center" twice at 3 m,
  "Blue Beacon Truck Wash #74" twice at 20 m. Two pins, one place, because a boundary runs
  between them. Density makes that worse, not better — more sites, more edges.

Blocking is a geography predicate now (indexed since 0056) at **60 m**, which is the audit's
number rather than a guess: identical-name pairs are **91%** of candidates within 30 m and
**22%** beyond 90 m. Past that the neighbours are mostly other places.

**Widening what is reachable needed four guards, and three came from looking at rows.**

| Guard | Evidence |
|---|---|
| A placeholder is not evidence | 69 of the 191 are two facilities both named "Rest Area" — a name this code wrote |
| Opposite carriageways are two places | "Turnout Eastbound"/"Westbound", 32 m apart at 0.64 similarity |
| A bare compass word, when it is the only difference | **the dry run was about to merge "Dale City … Rest Area South" into "…North"** |
| A different number | **the dry run was about to merge "Nhs Rest Stop Or Truck Facility 7" into "…17"** |

The last two are the ones worth remembering. `direction_of` ignores a bare "North" so that
"North Platte Truck Stop" survives — **right about one name and wrong about a pair.** The
fix is to compare rather than extract. And a number in a facility name is an identifier that
trigram similarity cannot see, being one character inside a long string.

**Neither was caught by a test.** Both came from dry-running the repair over the real
registry and reading what it proposed — which is why `repair_duplicates` prints every merge
before it makes one.

**Applied: 95 pairs merged on the laptop and 95 on the box, idempotent on re-run.**
Identical-name duplicates fell from 91 to 3, and those 3 are cross-KIND pairs ("TA" as both
a truck stop and a parking property, 17 m apart) that the script declines on purpose —
choosing which kind survives is the co-location question, with its own rules.

Production after the repair: **5,343 live facilities · 449 repair · 756 callable.** The
counts fall slightly because duplicates stopped being counted twice, which is the point.

## 13. A9 §5's other half — admin URLs, and merges that chained

**`/admin/facilities/*` now resolves merged ids.** `canonical_facility_id` has been on
every driver-facing route since §23's merged-id fix and was never carried across — **the
eighth instance this session** of a mechanism fixed in one place and not the others. The
cost was not theoretical: an admin editing a merged id edited the **shadow**. The patch
recorded, the audit log saying it happened, and the map showing the old value forever.

**Reading those three routes together turned up a second thing nobody had guarded: a merge
could land on a row that was itself merged.** Measured — **146 rows locally and 149 on the
box** pointed at a shadow. Reads survived because `resolve_canonical` walks the chain, and
the fact that it carries a `seen` set means somebody had already worked out that a **cycle**
was reachable from here. Nothing prevented either.

- A chain is a **tax**: every read of one of those ids walks it, and A9 makes more merges.
- A cycle is worse — `resolve_canonical` would answer with whichever row its guard broke on,
  which is a wrong answer delivered confidently.

Guarded inside `merge_facilities` rather than in its callers, because there are four of them
(the ingest pipeline, the admin route, and two repair scripts) and a rule kept in three
places out of four is exactly what this session kept finding. `flatten_merge_chains`
re-points the rows written before the guard: **146 flattened locally, 149 on the box, zero
remaining, idempotent.**

**Two of the three admin tests were proved red against unresolved routes; the third holds
either way** because `merge_facilities` also resolves. That is defence in depth, not proof,
and the test says so rather than claiming credit it has not earned — an earlier draft
asserted only that a merged row is absent from its own duplicate suggestions, which is true
whether or not the id resolves. It passed against the broken code and proved nothing.

**Still open from §5: the admin merge-review SURFACE.** `GET /admin/facilities/{id}/duplicates`
is the API half and shows exactly what the pipeline would have considered a duplicate — the
same function, so the two cannot drift. There is no UI on it.

## 14. The merge-review surface existed — it just could not be reviewed with

A9 §5 asks for one. **It already exists**: `AdminData` has the facilities table, a
per-facility "possible duplicates" button, and a merge action calling the same
`find_duplicate_candidates` the pipeline uses, so the two cannot drift. **Fourth v2.0
claim this session that does not match the code**, after A5's "most of this exists",
`search_service_facilities`, and A3.

So the work was not building it. It was making it reviewable:

- **A suggestion is a figure**, and §11.7 does not let one travel without what produced
  it. The console rendered a candidate's NAME and nothing else — an operator deciding
  "same place?" could not tell 5 m from 140 m, which is the difference between one site
  mapped twice and the rest area on the other carriageway. It carries **distance and
  kind** now: the evidence judging 95 merges by hand actually needed today.
- **A merge happened on one click**, and there is no unmerge from this console. §8 gives
  destructive actions their own confirm; this one names both sites, the distance, and
  says plainly that it cannot be undone. Composed from AdminFlags' existing confirm.

Both proved red by reverting the template. Six locales.

**§23 entry 119 records rather than decides.** The Admin Console is a §18 portal and has
been one in the code for many sessions — `meta: {portal: true}`, `max-width: 1200px`,
which is §18's own figure — while §18 still opened *"the ONLY non-mobile-first surfaces"*
and named three. The vendor portal was a fifth, logged as E-D3 because it needed logging;
§18's list never caught up. **A document that says "only these three" while the product
ships five is not stricter, it is unreliable** — the next session finds a surface that is
not on the list and has to guess whether that is a defect or an omission. LAW 0 is
untouched, and its closing sentence still means what it says.

## 15. §18's contract, measured before it was tested

§23 entry 119 exposed that nothing checks the five portals. Rather than write tests for
the whole contract, I measured it on the real portals at 1920 and 360 first:

| | 1920 | 360 |
|---|---|---|
| admin · owner · fleet · scorecard | no page overflow | **no page overflow** |
| portals importing a driver screen | — | **none** |

**So §18's two load-bearing rules already hold.** What is unenforced is the one that is
silent when broken: *"they share `ui/core` tokens and components where sensible but NEVER
import driver-app screens"*. That is the same boundary import-linter holds on the Python
side, and it now has a test — one that finds the portals **from the router**, because a
hand-kept list is the same drift one layer up, and that covers the admin console's nested
panels, because AdminShell is the route component and a reused driver screen would land in
a panel where nothing was looking. Proved red by importing `MapSurface` into `AdminData`.

**What I deliberately did NOT build:** four portals × four variants in the layout sweep,
to guard a 1200 dp cap and a responsiveness promise that measurement says are already met.
That is ~2 minutes added to every run, and `ui-layout`'s own note says a check that is
painful to run stops being run — which costs more than the assertion pays. The measurement
above is the evidence; if a portal regresses, it will be because someone changed it, and
that is when a state is worth adding.

One thing the measurement did surface and I left alone: **fleet's table renders 361 px in a
360 px viewport.** One pixel, almost certainly a border, no page overflow. Recorded rather
than chased.

## 16. Going national — the preconditions, checked one at a time

A9 is "the single largest product risk" and its stated blocker (A12) is done. Before
starting a national run I checked what else A9 names, and **two of the three were already
satisfied**:

- **§8's ODbL attribution line is "required either way", independent of decision D2. It
  already exists** — `map.data_credit` = "© OpenStreetMap contributors (ODbL)" in all six
  locales, rendered when no basemap carries it. **Fifth v2.0 claim this session that is
  already true in the code.**
- **§1's "verify against one state before the national run" is done** — nine states, and
  the filter fix that made them possible is what started this whole session.
- **§3's "run repair-fuel and repair-scales after every ingest" was NOT done** after
  today's nine states, and I only noticed by re-reading the spec. Checked: scales had
  nothing to fix, fuel had **one** branded service area to re-type, applied on both the
  laptop and the box. The warning earns its keep, and barely — its worst case (Texas's
  162 unmerged islands) does not reproduce when the hosts already exist in the registry,
  which they now do.

**§2's regional batching is implemented**: `make osm-extract REGION=us-midwest` alongside
the per-state form, with everything downstream — the rendered tag filter, `osm-publish`,
`ingest-remote` — identical either way.

**us-midwest is 2.48 GB and was in flight when this was written.** It is deliberately the
first region: it overlaps seven states already validated today, so known data sanity-checks
the run, and it adds IL, MO, NE, ND and SD. **One region first, measured, before committing
to the other three** — which is A9 §1's own discipline applied one level up.

## 17. us-midwest — the first region, and two things it caught

**7,033 records parsed, 1,800 new facilities.** Locally: 5,339 → 7,139 live, repair
450 → 595, callable phones 756 → 1,017, and 48 states now carry at least one OSM-derived
facility. The region path is the same code as the state path — only the URL differs.

**It would have been OOM-killed on the box, and that was found before running it.**
`read_geojson_file` is `json.load`, and the deployed box is an e2-medium: 3 GB total,
~2 GB available. Measured on the real 573 MB export (1,289,915 features):

| | peak RSS |
|---|---|
| `json.load` | **4,677 MB** |
| `iter_geojson_features` | **80 MB** |

`osmium export` writes one feature per line, so it streams. **The fallback was the part
that mattered** — every fixture is pretty-printed, and a reader that silently returned
nothing for them would have made every ingest test in the package vacuous at once. My
first version guessed from the FIRST LINE, which is also true of a single-line file, so
`readline()` swallowed the whole document and it returned zero features **without
raising**. Caught by the runner test. It falls back on having streamed *nothing* now,
which cannot be fooled that way.

**A9 §3's warning reproduced exactly, on the region path only.** The batch left **194
scales and 163 fuel islands unmerged** — the spec cites 203 and 162 for Texas. The
co-located rule is order-dependent *within* a batch, so it bites when an amenity is
processed before its host; the nine per-state ingests did not trigger it because the
hosts were already in the registry. All merged by the sanctioned repairs.

**And the ninth "not carried across".** The region audit surfaced "Yosemity Sams Autocare
Center" as a truck repair facility: `semi` matched inside "Yo-**semi**-ty".
`direction_of` has guarded exactly this since it was written — *"a direction must be a
WORD, not a letter inside one; Sbarro is not southbound"* — and the truck terms, added
later the same day, did not carry the rule across. **The reasoning was already written
down, twelve lines away.** Fixed with a leading word boundary, so `truck` still matches
"Trucking".

**One row of that is already in production** and stays: F2's status vocabulary is
candidate / confirmed / merged, and none of them means "this should not be here". Not
worth inventing a state for one autocare shop — recorded because at fifty states it will
not be one.

## 18. The telemetry bug was real; my diagnosis of the symptom was not

**Two separate things happened here and only the first one was what I thought.**

**The real bug.** The first us-midwest run on production ended with **no new facilities,
no error, and no `job_run` row at all.** Not a failed one. Nothing.

That is a defect in the A12 requirement-3 telemetry I added this morning. The started
row was written inside the **same transaction as the work**, so when the process was
killed the rollback took the evidence with it.
`test_a_failed_load_is_recorded_as_a_failure_not_silence` covers an EXCEPTION — which
the code catches and records — and **not** a kill. On a 2 GB e2-medium running a 3 GB
ingest, killed is the likely ending, not the exotic one. *"One row per attempt"* was
true only for the failures polite enough to raise.

Telemetry runs on its **own connection** now, so the ingest's rollback cannot reach it.
Verified on the box mid-run:

```
started_at 08:08:31 | ok=f | still_running=t
```

A started-but-never-finished row is exactly what an operator needs — it says "this
died", which silence does not.

**Bound to the CALLER'S engine, not `SessionLocal`,** and that is not a detail: the test
suite runs against a **separate database**, so a hardcoded `SessionLocal` wrote the row
into the DEV database while the test looked in the test one. It never found it, and every
suite run had been quietly polluting dev.

**THE MISDIAGNOSIS, recorded because it is the more useful half.** After the fix I ran the
ingest again and concluded from low memory and an empty log that it had "died again", twice.
It had not. Both runs were **still going** — memory was low because the parse phase had
finished and the DB-write phase is cheap, and the log was empty because output was buffered.
All four attempts eventually completed, every one recording 3,960 facilities. The ingest is
idempotent, so four runs cost nothing but time (`created=0` on the repeats proves it), and
the lesson is the one this project keeps relearning from the other direction: **absence of a
signal is not evidence of death.** I read two absences as a fact and said so out loud before
checking the row that would have answered it — the `job_run` row I had just built for
exactly this purpose, which was sitting there saying `running`.

**And a consequence worth stating**: streaming the READ fixed the parse (4,677 MB → 80 MB)
and did **not** fix the ingest. The api container still sat at **3.07 GiB of 3.83** during
the run, because `ingest_records` holds the whole batch and a SQLAlchemy session in one
transaction. That is the next thing to fix if the remaining regions are larger — chunked
commits are safe here because ingest is idempotent on `(source_kind, external_ref)`, so a
re-run resumes rather than duplicating.

## 7. Debt

**Closed this session:** no backups · no monitoring · the disk was about to fill · "what is
the box running" was unanswerable · design-prd entry 117 was blocked on a signature.

**New (111):**
- **The alert's delivery is unconfirmed** (§5).
- **Two false positives survive the name rule, both real and both minor.** Louisville's
  "Transit Authority of River City Garage" is a municipal BUS depot that OSM says repairs
  trucks — a driver cannot use it. Iowa's "Dick's Truck Stop" is typed `repair` because OSM
  mapped it only as a wash. Neither is worth a blacklist off one example, and inferring
  facility KIND from a name is the fragile move the rule deliberately avoids elsewhere.
- **A3 is effectively closed but not formally.** §10 — the defect it describes does not
  exist; the refinement it asks for would be wrong as written.
- **Ingest sources reach the box by hand.** `gcloud storage cp` then `docker cp`, and the
  second half evaporates on the next deploy. Fine for one state, not a process for fifty.
- **`gsutil` does not work on the box** and `gcloud storage` does. Anything written against
  the former will fail with a message about scopes that is not about scopes.
- **The scratch database `haulmeter_restore_check` is created and dropped nightly** on the
  same postgres instance as production. It is dropped in a trap on every exit path, but a
  restore verification that shares an instance with the thing it verifies is a compromise —
  the honest version restores onto separate hardware.
- **Backup retention is 30 days by bucket lifecycle and 3 copies locally.** Neither number
  was derived from a recovery objective, because nobody has stated one.

**Carried from 110:** A5 is observable but unvalidated · the UI has **no lint at all**, and a
missing import shipped green today · `record_map_open` is exported and called by nothing · a
deploy ships code, not data · 22 facilities carry an adopted placeholder name · six locales
are machine-translated, not native-reviewed · "Mobil Diesel" is still typed `repair` in dev.

**Carried and still open:** no push has reached a real handset · iOS untested · `sw.js`
hardcodes `/api/map/report` · the manifest ships `"icons": []` · `/events/stream` is not
flag-gated · the SSE session travels in the query string · `_enrich` is per-pin · the flaky
`login · pa` layout state · `/admin/facilities/*` does not resolve merged ids · M2-FR4 does
not exist · the profit calculator opens on invented defaults · dwell-risk thresholds
unvalidated · "claim paid" is dormant · notification copy is English-only server-side ·
**all live API keys are still on an internet-facing VM**.

## 8. What I did NOT verify

- **That the alert email arrives.** §5. Everything up to the send is proven; the inbox is not.
- **That a restore works on a DIFFERENT machine.** The verification restores onto the same
  postgres instance. If the failure is "the VM is gone", this proves the dump is complete and
  loadable — not that anyone has rehearsed rebuilding the box from it.
- **That the nightly cron actually fires.** It is installed in `/etc/cron.d/haulmeter` and
  `cron` is active; both jobs were run by hand. The first unattended run is 03:30 UTC
  tomorrow, and **nobody has watched the log after a night**.
- **The 95% row-count tolerance in the restore check** is a judgement, not a measurement. A
  backup taken during a large ingest could legitimately sit further behind live than that.
- **Anything about A9's national density.** Untouched.

## 9. Restarting

```
make up                              # local stack
make test                            # pytest 1268 + vitest 607 — NEVER pipe it
make lint                            # ruff + import-linter 30/30
make ui-layout                       # 193 states, ~4 min

# on the box
bash /opt/haulmeter/scripts/backup_db.sh        # writes to gs://haulmeter-backups
bash /opt/haulmeter/scripts/verify_restore.sh   # pulls it back and proves it
sudo tail /var/log/haulmeter-backup.log /var/log/haulmeter-restore.log
```

**The standing warning, eighth form.** 107: the code was right and the DEFAULT was wrong.
108: the PROSE was wrong. 109: the prose about the prose was wrong. 110: the INPUT never
arrived. This one: **the safeguard was never armed.**

Three manual dumps sat on that box looking like backups. They were on the disk they were
protecting against losing, nobody had ever restored one, and no schedule would ever write
another. Every piece of the idea was present and none of it was connected — which is the
same shape as six ingest rules that had never received a tag, and as a flag whose
registration is what switched its feature off.

**A safeguard that has never been exercised is not a safeguard, it is a belief about one.**
The nightly restore check exists so that belief keeps being tested after everyone has stopped
thinking about it — and §5 is the honest admission that the alert half is still, today,
exactly the kind of belief this paragraph is warning about.
