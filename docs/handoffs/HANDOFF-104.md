# HANDOFF-104 — the session the product started asking

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 29 July 2026 · **Stack:** UP locally (`make down` to stop) · **Deployed:**
https://haulmeter.online (GCE, `uzimiz-prod`) — **current**, Web Push enabled, and the
lot-status prompt verified firing on the box through the real push gateway.

**State in one line:** F8 now runs in both directions — it tells a driver things
(three P0 classes) and, for the first time, asks them one.

> **This continues HANDOFF-103, which is the same session.** 103 has the Web Push
> build and the one-shot-prompt reasoning; this feature depends on both.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0055_f08_push_subscription** (no new migration this batch) |
| Tests | **pytest 1193 · vitest 567 · layout 177 · ruff + import-linter 30/30** |
| §23 decision log | **112 entries** (106–112 this session) |
| Handoffs | 000 → 104 |
| Git | pushed; in sync with `origin/main` (public) |
| Deployed | **current**, verified end to end on the VM |
| Working tree | clean except untracked `collect_files.py` (not mine) |

## 2. What shipped after 103

| Commit | What |
|---|---|
| `47a1fcf` | The prompt's rules, class and tray actions — trigger blocked (§23 112) |
| `2dc2d38` | The trigger, wired to the ping trail instead of the geofence |

## 3. What was asked, and what was refused

Owner-raised: crowd status should be **dynamic** — the app noticing a driver is
approaching, passing, entering or leaving a facility and prompting for a quick
confirmation, instead of waiting for someone to open the map and tap the report chip.
**The gap was real: nothing in this product had ever asked a driver anything.**

**Refused — approach and pass**, on three independent grounds, any one sufficient:

- **§13.4** is explicit that while DRIVING there are "no interactive prompts, no
  full-screen intents", and approaching a facility *is* the DRIVING state.
- **§13.1's budget** caps unprompted interruptions at two a day; a driver passes dozens
  of facilities daily. The failure mode is not irritation, it is a revoked notification
  permission — **one-shot**, and shared with the detention P0.
- Approach detection needs finer position sampling than the 250 m / 5 min throttle that
  §23 entry 93 exists to enforce.

**Refused — the "leaving" half, because it already exists.** A driver pulling out is a
spot opening, and that is M10-FR2's relay handoff: built, tested, already streamed over
SSE (§23 entry 103). A second prompt would be a competing weaker source for one fact.

**Built — the arrival half**, with almost every rule being a refusal: wrong kind of
facility, already reported, never opted in, over the daily cap, quiet hours.

## 4. The trigger, and the version that could never fire

**The first build hung the prompt off `DWELL_TICK` and shipped thirteen green tests.
It could not fire at all.** `evaluate_ping` emits events only for facilities with an
active ARMING, and `arm_geofence` has exactly one caller in the tree —
`f05_load.arm_stop`. So geofence events exist only for **stops on a load**: the dock
kinds this feature deliberately excludes, because a driver dwelling at a dock is
working. A driver pulling into a truck stop for the night produced no event at all.

**Every one of those thirteen tests called `prompt_for_lot_status` directly.** They
proved the RULES, which is a different question from whether anything ever calls them.
It was caught by pushing real pings through `evaluate_ping` and getting an empty list.

**The fix is owner-chosen shape (c): read the ping trail, touch nothing else.**
`f03.stationary_since` returns when the current stay began — one query, the anchor kept
as a scalar subquery so PostGIS flags the whole window server-side.

- **The first ping outside 150 m ENDS the stay.** A driver who left and came back gets
  this visit, not the union of both — §23 entry 73's scoping mistake, which billed
  $187.76 against $0.00 owed, refused in advance.
- **It writes nothing to the location tables** — no arming, no presence, no event. That
  isolation is the whole reason this shape beat auto-arming: it cannot perturb the
  machinery M3's money reads even if the detection is completely wrong. **A test
  asserts the emptiness rather than trusting it.**
- **Checks are ordered cheapest-first, because this runs on every ping:** offered-today
  (one indexed read, short-circuiting almost every ping after the first) → stopped at
  all (false for every ping of a moving truck) → and only then a spatial query.

## 5. Rules to know before touching this

- **The attempt guard counts OFFERS, not deliveries.** A driver dwelling eight hours
  pings ~96 times; without it each one loses to the daily cap and writes a SUPPRESSED
  row — and §23 entry 102's inbox deliberately renders suppressed rows, so they would
  open it to ninety identical held prompts. Suppression is a decision about one
  notification, not a licence to keep making the same one.
- **Not budget-exempt, deliberately.** `protection_gap` earned its exemption by being a
  DEADLINE — that trailer cannot be photographed at that dock ever again. A survey is
  the opposite, so it must LOSE to real news rather than crowd it out.
- **Opt-in is OFF by default** and that is the field most worth revisiting: it asks the
  driver for LABOUR and §21.8 forbids helping ourselves to it. The cost is real — most
  drivers will never see it unless they go looking — and the answer to low uptake is a
  better offer, not a default that takes without asking.
- **The three tray actions are `PARKING_STATUS`'s own values** (Empty / Some / Full), so
  no new vocabulary exists anywhere in the system and the answer maps straight onto
  `/map/report`.
- **`sw.js` decides nothing** and renders the actions the server sent. A vocabulary
  hardcoded in a service worker can be stale on a driver's phone for days.

## 6. Method notes

- **Verified on the deployed box, through the real push gateway**: a driver with no
  load, no stop and no arming produces **zero geofence events** and is still asked,
  once, with the right copy and a `/facility/<id>` link. Gateway resolved to
  `WebPushNotificationGateway`.
- **A PostGIS bug was caught by the tests and would have shipped otherwise.** Fetching
  the anchor geometry into Python and passing it back produced `parse error - invalid
  geometry` — a failure that reads like bad data and is actually a round trip that
  should never have happened. It is a scalar subquery now, which also collapsed two
  queries into one.
- **Three guards proved RED**: the dwell requirement, the attempt guard, and the two
  facility/already-reported refusals.
- **An order-dependent M5 assertion was found and fixed.** It read
  `db.query(Notification).all()` with no ORDER BY and asserted `delivered[0]`; it passed
  for months and flipped when the new tests started writing more notification rows and
  changed the heap. Adding `ORDER BY dispatched_at` does not fix it either — both are
  dispatched at the same instant, so their relative order is simply not a fact the data
  records. It now asserts WHICH two survived the budget, which is what it meant.

## 7. Exact next task

**1. Put a push on a real handset** — unchanged from 103 §7.1 and now more valuable,
because there are two things worth receiving: a detention P0 and a lot-status prompt
with tray buttons. Open https://haulmeter.online on Android Chrome, sign in, More →
notifications → "Turn on alerts", then either cross a free-time boundary or park inside
a truck-stop geofence for 15 minutes.
> **CORRECTION 2026-07-30 (§23 entry 114): these steps could not have worked for the
> prompt.** "Turn on alerts" enables PUSH — the browser permission and the subscription.
> The lot-status prompt is also gated on its CLASS opt-in, which nothing could set, so
> the prompt would have been suppressed `not_opted_in` and the test would have failed
> pointing at the wrong layer. The sheet now carries the class switch too; turn on BOTH. **Confirm the tray ACTIONS appear and that
tapping one posts the report without opening the app** — the service-worker action
handler and the IndexedDB token read are the two pieces no test here can exercise.

**2. Watch whether prompted beliefs disagree with volunteered ones.** §23 entry 112
flags it: prompted reports are more numerous and lower-intent. F10's consensus and trust
scoring should absorb it, but nobody has measured it, and §11.7's posture is that a
confident wrong status is worse than none. **This should be checked before the 1/day cap
is ever raised.**

**3. Give "claim paid" a second actor**, or accept it stays dormant (102 §4).

**4. Coverage.** 9 states (WI IN IA MN KS KY MI OH TX). Unchanged.

## 8. Debt

**New this session (104):**
- **The prompt has never been answered from a tray.** The dispatch path is verified on
  the box; the ACTION path — service worker → IndexedDB token → `/map/report` — has
  only unit coverage.
- **`stationary_since` runs on every ping.** One indexed query, ordered behind a cheaper
  guard, and measured at nothing on a small dev set — but it is a new per-ping cost on
  the endpoint §23 entry 93 already took the API down once. Worth watching under load.
- **Nobody can turn the prompt off from inside a prompt.** §13.1's per-subject mute
  exists in F8 (`mute_subject`) and no surface uses it; the only control is the class
  opt-in in the notifications sheet.
  > **CORRECTION 2026-07-30 (HANDOFF-105 successor, §23 entry 114): there was no such
  > control.** No endpoint, client function or screen could set this class's opt-in —
  > `set_class_opt_in` had exactly one caller in the tree, the vendor-alerts route — so
  > `dispatch` suppressed `not_opted_in` for every driver, always, and the feature was
  > unreachable. Both controls exist now. Left in place rather than deleted, because
  > believing a control existed is why nobody looked for it.

**Carried from 103:** no push has reached a real handset · the manifest ships with
`"icons": []` · no push telemetry · iOS untested.

**Carried from 102:** "claim paid" is dormant · `recovered` is terminal with no operator
path back · `check_in`/`check_out` have no endpoint.

**Carried from 101:** `trigger_time = arrival or now` · the 30-minute `ALERT_FRESHNESS`
window is a judgement · `dispatch_clock_alerts` costs one `clock()` per open claim ·
M5's expiry reminders deep-link to `/docs`, a tab root · notification copy is
English-only, server-side.

**Carried and still open:** `/events/stream` is not flag-gated · the SSE session travels
in the query string · the SSE generator is synchronous · `_enrich` is per-pin · beliefs
written against merged ids before §23 95 · the flaky `login · pa` layout state ·
`/admin/facilities/*` does not resolve merged ids · M2-FR4 does not exist · per-stop
detention terms not expressible in the UI · the profit calculator opens on invented
defaults · dwell-risk thresholds unvalidated · `pin.shape` read by nothing · all live
API keys on an internet-facing VM · **no backups** · **no monitoring**.

## 9. Restarting

```
make up                              # local stack
make test                            # pytest + vitest
make ui-layout                       # 177, ~2.4 min — run it alone
make lint                            # ruff + import-linter
make vapid-keys                      # prints a pair; paste into infra/.env by hand
./scripts/deploy.sh                  # ship to haulmeter.online
```

**The standing warning, in the form this session found it — and it found it twice.**
A feature passed thirteen tests while being structurally incapable of running, because
every test called it directly. A harness passed 177 states while knowing nothing about
the screen just built. A test that read as timeless expired at 13:00. An assertion that
looked deterministic was reading rows in whatever order the heap happened to hold them.
**None of these are bugs in the code the tests cover. They are all the same thing: a
suite answers "does this do what it was written to do", and never "is this reachable, is
it measured, is it still true today".** Drive the real thing.
