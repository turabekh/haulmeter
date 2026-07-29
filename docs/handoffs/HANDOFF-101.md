# HANDOFF-101 — the session the product finally told a driver something

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 29 July 2026 · **Stack:** UP locally (`make down` to stop) · **Deployed:**
https://haulmeter.online (GCE, `uzimiz-prod`) — **current with `3e7fba2`**, migration at
head, zero errors, and the first `detention_clock` tick alerted nobody (§7.1).

**State in one line:** HANDOFF-100 §8's exact next task, done — the P0 §13.2 has named
since the design constitution was written now fires, and the two defects that stood
between it and a driver were both invisible to a green suite.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0054_m03_driver_clock_alerts** |
| Tests | **pytest 1137 · vitest 547 · ruff + import-linter 30/30** |
| Layout harness | **NOT run this session** (169 as of 100; no UI changed here) |
| §23 decision log | **107 entries** (106–107 this session) |
| Handoffs | 000 → 101 |
| Git | **3 commits ahead of `origin/main`, unpushed** — `8fc0557`, `2c4f066`, `3e7fba2` |
| Deployed | **current with this session's work**; `0054` at head on the box |
| Working tree | clean except untracked `collect_files.py` (not mine) |

## 2. What shipped

| Commit | What |
|---|---|
| `8fc0557` | §23 106 — the proposal: which instant IS "detention started" |
| `2c4f066` | The first P0 this product has ever sent (§23 107) |

## 3. The decision, and why it was worth asking

**100 §8 said this needed an owner decision before any code, and it did.** Geofence
ENTER, free-time expiry and the first billable minute are three different instants.
**Owner decision: free-time expiry, and NO notification class** — both recommendations
taken as written (§23 106, now approved).

Three things found in the code sharpened the case beyond how 100 put it:

- **At geofence ENTER, §12.6's own copy is false in both halves.** "Detention started ·
  $75/h — Notice ready to send" — the amount is $0.00 for the next two hours and
  `send_detention_start_notice` refuses to send while the phase is `within_free_time`.
  A P0 whose figure is zero and whose single action does nothing spends the most
  protected tier in the product on nothing.
- **"First billable minute" is not a distinct instant in this codebase.** `compute_detention`
  accrues from second zero, so one second past free time the claim is worth 2 cents;
  **M3 has no minimum billing increment anywhere.** Choosing it would mean inventing
  one — a change to what every invoice says, not to when a phone buzzes.
- **The P1 beside it is measured from the same boundary.** `PRE_DETENTION_THRESHOLD`
  and `send_pre_detention_notice` already existed with no driver dispatch. Decided
  together, so the two can never be computed from different starts.

**No class, and the reason is the point.** A class is an OPT-IN bundle; an opt-in
switch on the one money-critical fact this product exists to tell a driver would let
them be silently un-told.

## 4. What was actually missing was not the copy

**`clock()` is computed on READ.** The instant free time expired passed unobserved
unless a driver happened to have the screen open. So the feature is a watcher:
`detention_clock`, a 60-second worker job behind M3's own flag. **The interval IS the
alert's accuracy**, which is why it differs in kind from the four feed-refresh jobs
beside it — those tolerate a stale minute, this one defines one.

Two columns, not one: `start_notice_sent_at` records the BROKER's notice,
`driver_start_alert_at` / `driver_warning_alert_at` the DRIVER's. One column would have
made "the driver knows" mean "the broker was told". Each is set when the alert is
DISPATCHED, following M5's rule — F8 may suppress for quiet hours or budget, and
re-offering it every minute until one got through is the nagging §13 exists to prevent.

## 5. The suite was green and the real run was not — TWICE

**This is the section to read before touching anything here.** Every test passed before
either of these was known.

**(1) The first live tick dispatched ELEVEN P0s at once.** Claims whose free time
expired **52–70 hours earlier**, whose drivers F3 still places on the dock. On the
deployed box that is a burst of stale P0s to real accounts, each announcing a moment
long past. §13.2 defines P0 as time-sensitive, so lateness is not a delivery detail:
past `ALERT_FRESHNESS` (**30 min** — forgiving half an hour of worker downtime against
a 60-second job) **there is no alert to send rather than a late one.** Nothing is marked
on that path: a stale claim did not have its alert suppressed, it never had one to send.
It is also what makes deploying this safe — every claim predating the feature is far
outside the window.

**(2) With that fixed the same run still fired FIVE, and the zero gave it away.** All
five reported `detention_seconds == 0`. `clock()` falls back to
`trigger_time = arrival or now`, so a claim F3 cannot place has a trigger that **slides
forward on every call**. Harmless while free time remains — the phase never reaches
accruing. **Not harmless at free time of 0 or None**, where the claim reports
"accruing, 0 seconds, $0.00" FOREVER and reads to an alerting job as a boundary crossed
one second ago. Five live claims were in exactly that state and would each have pushed
"Detention started" for a stop the driver never reached, for no money — **the precise
failure §23 106 rejected geofence ENTER to avoid, arriving through a different door.**

An alert now requires a **real anchor**: a resolved F3 arrival, or the appointment the
claim was triggered on. A sliding `now` is the absence of one.

**Note what caught each.** Not the 1137 tests — the job summary line in the worker log,
read against the real database. `{'scanned': 43, 'started': 11}` is what a defect looks
like when every assertion agrees with you.

## 6. Method notes

- **Every guard was proved RED first** by restoring the behaviour it forbids — the phase
  gate, the idempotency, the 30-minute threshold, the freshness window and the anchor,
  each temporarily removed and the naming tests watched to fail. Four probes, five
  guards.
- **The paired assertion matters.** "P0 survives a spent budget" proves nothing unless a
  P1 at the same instant is shown to be suppressed; both halves are in the same test.
  Same for quiet hours.
- **Verified end to end on the real database, not only in the suite**: from a reset
  state the job reports 0 started across 43 open claims, and a claim whose boundary was
  crossed one minute ago produces exactly one P0 — correct copy, `/claim/<stop>` deep
  link, status `sent`, silent on the second run. The probe account and its rows were
  deleted afterwards.
- **The dev database was left clean.** The 14 notification rows and 71 claim timestamps
  written by the two buggy runs were removed; `detention_start` / `free_time_warning`
  rows are back to zero.
- **`make ui-layout` was not run** — no UI changed. Run it before anything visual ships.

## 7. Exact next task

**~~1. Deploy.~~ DONE, and the claim §5(1) rests on was verified rather than assumed.**
The first `detention_clock` tick on the box read
`{'scanned': 43, 'started': 0, 'warned': 0, 'delivered': 0}` — **43 real open claims,
not one stale P0 sent.** Zero `detention_start` / `free_time_warning` rows exist on
prod and no claim carries an alert timestamp, so the backlog that would have produced
eleven pushes on the laptop produced none here. Migration at `0054`, `/api/health` 200,
no API errors.

**2. The other two P0s §13.2 names still have zero dispatch sites** — "booking failed"
(M6) and "claim paid" (F7/M9). Deliberately not widened into this session. Neither
needs a §22 stop the way detention did: both instants are unambiguous, unlike the three
candidates that made "detention started" a product question. The class question is
already settled by precedent (§23 106) — money-critical P0s carry no opt-in class.

**3. Then Web Push (VAPID).** Unchanged from 100 §8.2 and still not blocked on
credentials. Everything dispatched today reaches the inbox and nothing else; a P0 to a
phone in a pocket is still push and can be nothing else. **What this session changed is
that there is now something real to push.**

**4. Coverage.** 9 states (WI IN IA MN KS KY MI OH TX). Unchanged from 100 §8.3.

## 8. Debt

**New this session:**
- **`trigger_time = arrival or now` is still the money core's behaviour** (§5(2)). The
  alert path now refuses to act on it, but nothing else does: **`/detention/{id}/clock`
  answers "accruing · $0.00" today for a claim F3 cannot place**, and five such claims
  exist in the dev data. Narrowing it touches four callers and is a change on its own
  evidence — do not fold it into a notification feature.
- **The 30-minute `ALERT_FRESHNESS` window is a judgment, not an owner decision.**
  Composed from "P0 is time-sensitive"; logged in §23 107 so it can be overruled.
- **`dispatch_clock_alerts` costs one `clock()` per open claim** — a stop read and an F3
  visit window each. Deliberate and bounded: it runs on the worker, not in a request,
  and `scanned` in the job summary is the instrument for noticing if it stops being
  small. It was 43 all session.
- **M5's expiry reminders deep-link to `/docs`, a tab root, which §13.5 forbids
  outright.** Pre-existing, one line, found while reading the dispatch precedent. Not
  fixed because it was not this session's task.
- **Notification copy is English-only, server-side.** Every dispatch site writes literal
  strings — the pre-existing pattern, followed here rather than inventing an i18n
  mechanism for notifications that does not exist. §12.5's six-locale law has no purchase
  on it today, and the inbox renders exactly what the server wrote.

**Carried and still open:** everything in 100 §9 except the two items this session
closed (nothing dispatches a P0; the P1 warning had no driver dispatch). Still standing:
`/events/stream` is not flag-gated · the SSE session travels in the query string · the
SSE generator is synchronous · `_enrich` is per-pin · beliefs written against merged ids
before §23 95 · the flaky `login · pa` layout state · `/admin/facilities/*` does not
resolve merged ids · M2-FR4 does not exist · per-stop detention terms not expressible in
the UI · the profit calculator opens on invented defaults · dwell-risk thresholds
unvalidated · `pin.shape` read by nothing · all live API keys on an internet-facing VM ·
**no backups** · **no monitoring**.

**Closed this session:** CLAUDE.md rule 3 no longer says "NEVER push" — it now
describes the actual working agreement (commit locally without asking; push and deploy
on the owner's say-so, checking the diff for secrets because the repo is public). It had
been carried as debt since 099 §11.

## 9. Restarting

```
make up                              # local stack
make test                            # pytest + vitest
make ui-layout                       # 169, ~2.5 min — run it alone
make lint                            # ruff + import-linter
./scripts/deploy.sh                  # push the working tree to haulmeter.online
docker compose -f infra/docker-compose.yml logs worker | grep detention_clock
```

**The standing warning, in the form this session found it.** 1137 tests agreed the
alerting was correct while it was preparing to tell eleven drivers about detention that
started three days ago, and five more about detention at a dock they never reached. Both
were visible in one line of worker log against the real database, and in nothing else.
**A test proves the code does what it was written to do. Only real data tells you what
the code is about to do to somebody.**
