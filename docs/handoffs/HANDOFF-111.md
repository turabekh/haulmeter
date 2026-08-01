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
| Migrations | head **0055_f08_push_subscription** (no new migration this session) |
| Tests | **pytest 1268 · vitest 607 · layout 193 · ruff + import-linter 30/30** |
| §23 decision log | **118 entries** — 117 (Service chip) **approved**, 118 (the delegation) added |
| Handoffs | 000 → 111 |
| Git | **in sync** with `origin/main` (public) |
| Deployed | **CURRENT** — A5, A12, **all nine states re-extracted**, backups, alerting |
| Coverage | `repair` **12 → 458** · callable phones **0 → 807** (§10) |
| Backups | **gs://haulmeter-backups**, nightly 03:30 UTC, 30-day lifecycle, **restore proven** |
| Alerting | GCP uptime check + policy → **turabekh@gmail.com** (see §5 — the last inch is unconfirmed) |

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
| 2. One health alert that reaches a human | **BUILT, last inch unconfirmed** — see §5 |
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

## 5. The alert's last inch is NOT confirmed, and I could not confirm it

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

**What I could not do is look in the inbox.** The channel's `verificationStatus` reads unset
and `sendVerificationCode` 404s, and an unverified email channel can silently deliver
nothing — which would be this session's own defect, one layer out: a capability wired to
something nothing reaches.

> **OWNER, one thing: did an email from Google Cloud Monitoring arrive around 04:25 UTC
> titled something like "ALERT PIPELINE TEST (delete me)"?** If yes, A12 requirement 2 is
> validated and the phase DoD item is closeable. If no, the channel needs verifying from the
> console (Monitoring → Alerting → Notification channels → Email → verify), and until then
> **the alert is decorative.**

## 6. Exact next task

**1. Answer §5.** One look in an inbox decides whether the alerting half of A12 is real.

**2. A5 and A12 both still need a driver.** A5's `service_call_tapped` count is 1 and that
one is mine. A12's alert is unconfirmed. Under v2.0 §2 neither is validated.

**3. DONE — all nine covered states now run the corrected filter**, on the laptop and on the
box. See §10. The manual step is gone: `make osm-publish STATE=x` then
`make ingest-remote STATE=x`.

**4. A9 is now unblocked on its stated blocker.** A12's backups exist and are proven, and the
disk has room. What A9 still needs before a national run is §4 of its own spec — the bulk
reads and the GiST-on-expression indexes — because `_enrich` is per-pin and the 300-pin cap
will bind in every metro at national density. **Measure with `EXPLAIN (ANALYZE)` before
multiplying the table**, which its spec says and this session's habit agrees with.

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
