# HANDOFF-107 — the session quiet hours turned out to be inverted

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 31 July 2026 · **Stack:** UP locally (`make down` to stop) · **Deployed:**
https://haulmeter.online (GCE, `uzimiz-prod`) — **current**, and verified there from a
browser that genuinely believed it was in Denver: signing in recorded the zone, the sheet
named it, and moving the window stuck without clobbering it.

**State in one line:** §13.3's "22:00–06:00 local" now means what it says, in the driver's
own zone, without the driver doing anything.

> **This continues HANDOFF-106**, whose §7.3 flagged quiet hours as having no surface.
> Measuring it turned up something worse than missing.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0055_f08_push_subscription** (no new migration; the columns already existed) |
| Tests | **pytest 1235 · vitest 592 · layout 181 · ruff + import-linter 30/30** |
| §23 decision log | **115 entries** (115 this session) |
| Handoffs | 000 → 107 |
| Git | pushed; in sync with `origin/main` (public) |
| Deployed | **current**, verified end to end on the box |
| Working tree | clean except untracked `collect_files.py` (not mine) |

## 2. What shipped

| Commit | What |
|---|---|
| `49e6814` | `set_prefs`, the prefs routes, and the measured quiet-hours suite |
| `4386b34` | The timezone sync, the window control, six locales, the harness, these docs |

## 3. What was wrong

**106 §7.3 said quiet hours were "not driver-adjustable". They were also pointed at the
wrong half of the day.**

`in_quiet_hours` honours §13.3 exactly — it converts server time into `prefs.timezone`.
And **`prefs.timezone` defaulted to `"UTC"` and was written by nothing in the tree.** No
route, no client call, no screen. Measured with the product's own function before a line
was changed:

| Driver's zone | P1 notifications actually SILENCED |
|---|---|
| America/Los_Angeles | 15:00–23:00 |
| America/Denver | 16:00–24:00 |
| America/Chicago | 17:00–24:00 (+ 00:00–01:00) |
| America/New_York | 18:00–24:00 (+ 00:00–02:00) |

Every driver muted through the working afternoon and evening, and **reachable at 03:00**.
This platform serves US drivers exclusively, so it was wrong for **100% of them**.

**Scope, precisely: every P1, and no P0.** `dispatch` sends P0 before it reaches the
quiet-hours branch, so no detention alert was ever swallowed. The free-time warning, doc
expiry, `protection_gap` and the lot-status prompt made reachable the day before were all
landing on the wrong half of the day. A test now pins that ordering, because the blast
radius of the next bug here depends on it.

## 4. The decision worth arguing with

**Auto-detect the zone; no picker.** The browser already answers it
(`Intl.DateTimeFormat().resolvedOptions().timeZone`). A 400-entry IANA list on a 360 dp
screen is the wrong control, and **a driver should not have to configure their way out of
a bug**. It also follows the truck, which is what "local" means to someone crossing three
zones in a day.

The honest half of not offering a picker: **the sheet states the zone in use** rather than
hiding it, so a phone reporting the wrong one is a fact the driver can see.

Wired on the **token watcher**, beside §23 entry 113's IndexedDB mirror — boot and sign-in
are two call sites and two call sites is the trap that entry documents. **Every existing
driver heals on their next app open**, no action asked.

## 5. Rules to know before touching this

- **The PUT is partial, and that is load-bearing.** The client sends the zone on every
  sign-in; a whole-object write would silently undo a window the driver set. Held by tests
  at the service layer, the route layer, and in the UI (the window editor must send no
  `timezone` key).
- **`_sentTimezone` resets on logout.** Without it the next driver on a shared cab tablet
  inherits the last one's dedupe and never gets their own zone recorded.
- **The zone is validated by `ZoneInfo`'s own lookup**, never a hand-kept list — the only
  check that stays true as tzdata changes, and the same object `in_quiet_hours` will use,
  so a value that stores cannot fail at read time.
- **`start == end` means no quiet hours at all** (`start <= t < end` contains no hour).
  The tests have relied on that for months as folklore; the sheet now says it out loud.

## 6. Method notes

- **Four existing tests broke, and they were right to.** They read
  `fetch.mock.calls[0]` or a total call count while calling `setToken` — and establishing
  a session now also tells the server the timezone, so "the first request" is no longer
  the one under test. **Same brittleness HANDOFF-104 §6 corrected in an M5 assertion
  reading `delivered[0]`:** indexing a call list asserts a position, not a fact. They now
  find their own call by URL, and the throttle test counts *pings* rather than requests —
  which is what it always meant.
- **The harness was made to prove itself again.** `sheet-notifications` now renders three
  controls that each appear only after the server answers, and unmocked routes 404 there.
  `ready` is `.notif:has(.prompt-class):has(.quiet)` — it cannot go green with either
  missing. Verified by disabling the prefs mock and watching all four checks fail.
- **A test caught me conflating two rules.** The empty-window test sent three P1s to one
  driver and read the third's `budget` suppression as a quiet-hours failure. §13.1's 2/day
  cap was doing its job. It uses a fresh driver per hour now.
- **Driven in a real browser that genuinely believed it was in Denver** — Playwright's
  `timezoneId`, so `resolvedOptions()` really returns it rather than a value the test
  handed the app. Signing in recorded `America/Denver` server-side; the sheet named the
  zone; moving the window stuck; editing the window left the zone alone.
- **Re-measured after the fix:** every US zone reads **22:00–06:00 local**, and a Denver
  P1 is sent at 09:00 and 19:00, held at 23:00 and 03:00.
- The dev DB gained a `tz-drive-…@example.com` account from that run; the box gained a
  `tz-deploy-…` and a `tz-drive-…` from the post-deploy verification, the second carrying
  a 23:30 window.
- **The deployed check was run twice over**: the prefs routes by hand over HTTPS (default
  UTC, PUT a zone, partial PUT keeps it, unknown zone 422 and changes nothing), then the
  same browser drive against https://haulmeter.online. `/api/health` answered 200 on the
  first try this time — the 502 recorded in 106 §6 was a startup race, not a pattern.

## 7. Exact next task

**1. Put a push on a real handset.** Unchanged from 106 §7.1 and now worth more: quiet hours no longer silence a US driver's afternoon, so a P1 sent during a test
drive will actually arrive. Android Chrome on https://haulmeter.online, sign in, More →
notifications → turn on **both** "Turn on alerts" and "Ask me about lots", park inside a
truck-stop geofence for 15 minutes. **Confirm the tray actions appear and that tapping one
posts the report WITHOUT opening the app.** Browser → service-worker action is still the
only link no test here can exercise.

**2. Watch whether prompted beliefs disagree with volunteered ones** (§23 entry 112).
Check before the 1/day cap is ever raised.

**3. Give "claim paid" a second actor**, or accept it stays dormant (102 §4).

**4. Coverage.** 9 states (WI IN IA MN KS KY MI OH TX). Unchanged.

## 8. Debt

**New this session (107):**
- **A driver cannot see or change their zone if the browser reports it wrong.** The sheet
  states it; there is no override. Deliberate — see §4 — but it is the failure mode to
  watch for, and the fix if it bites is a picker after all.
- ~~**The timezone syncs once per session.**~~ **CLOSED later the same session:** a
  `visibilitychange` listener re-checks the zone whenever the app returns to the
  foreground, so a driver who crosses into Kansas gets their window moved with them. The
  dedupe makes it free — nothing is sent unless the zone actually changed — and a test
  drives Denver → Chicago and asserts both PUTs, proved RED by disabling the listener.
- ~~**QUIET HOURS DO NOT DEFER — THEY DISCARD.**~~ **DECIDED — §23 entry 116: quiet hours
  FILE silently.** A P1 suppressed for quiet hours is written `status=suppressed` and
  nothing ever sends it; the worker runs five jobs and none re-dispatches, while three
  files reasoned in prose about "deferring". The owner chose honest naming over a
  redelivery job, and the rejected branch argues for it: a "30 minutes of free time left"
  held at 23:00 is actively wrong at 06:00, and re-sending a stale P1 is worse than
  silence. §13.3 now states it and adds that **no surface may promise later delivery**.
  The copy was corrected too, because the decision made it false: `notifications.held`
  said "Held until morning" on EVERY suppressed row — already wrong for `budget`,
  `muted`, `resting` and `not_opted_in`, none of which have a morning — and now reads
  "Held · not sent". **The count was deliberately not built**; the honest version is a
  count of what is UNREAD, which is a fact rather than a promise (and §10.5 keeps it away
  from a badge).

**Carried from 106:** no place lists every muted lot · the generic opt-in endpoint would
accept `protection_gap` · `GET /notifications/classes` returns classes with no surface.

**Carried from 105:** no push has reached a real handset · `sw.js` hardcodes
`/api/map/report` · no test asserts `setToken` is unused by production code · the manifest
ships with `"icons": []` · no push telemetry · iOS untested.

**Carried from 104:** `stationary_since` runs on every ping.

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
make test                            # pytest 1235 + vitest 592
make ui-layout                        # 181, ~2.6 min — run it alone
make lint                            # ruff + import-linter 30/30
./scripts/deploy.sh                  # ship to haulmeter.online — NEEDED for §7.1
```

**The standing warning, fourth form.** 104: a suite answers "does this do what it was
written to do", never "is this reachable". 105: the agreement between two components can
be owned by neither. 106: the tests kept entering where a driver cannot. This one is
different in kind and worth adding: **the code was correct and the DEFAULT was wrong.**
`in_quiet_hours` implements §13.3 faithfully; every test of it passed; the bug was a
three-letter string that nobody had ever compared against the world the product describes.
**"UTC" is not a neutral placeholder in a platform with a country in its problem
statement — it is an assertion that every driver is in Britain.** Read the defaults with
the same suspicion as the logic, and measure them against a real user before believing
them.
