# HANDOFF-108 — the session that stopped believing the prose

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 31 July 2026 · **Stack:** **DOWN** (`make up` to start) · **Deployed:**
https://haulmeter.online (GCE, `uzimiz-prod`) — **BEHIND by three commits.** The box has
the timezone fix from 107 but **not** the zone-follows-the-truck re-check and **not** the
copy correction, so it is still telling drivers "Held until morning" about notifications
that are never sent.

**State in one line:** quiet hours now follow the truck across zone boundaries, and the
product has stopped claiming it defers notifications it actually files.

> **This continues HANDOFF-107, which is the same working session.** 107 has the
> inversion, the per-zone table and the timezone sync; this closes two of its debt items
> and records an owner decision that came out of the second.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0055_f08_push_subscription** (no new migration) |
| Tests | **pytest 1235 · vitest 594 · ruff + import-linter 30/30** |
| Layout | **181 states; 179 passed under four workers — see §5, it is a known flake and both stragglers pass alone** |
| §23 decision log | **116 entries** (115 and 116 this session) |
| Handoffs | 000 → 108 |
| Git | **NOT pushed** — three commits ahead of `origin/main` |
| Deployed | **STALE**, and currently showing false copy |
| Working tree | clean except untracked `collect_files.py` (not mine) |

## 2. What shipped after 107

| Commit | What |
|---|---|
| `71e1855` | The quiet-hours window follows the truck (`visibilitychange` re-check) |
| `38ec9e8` | §13.3 + §23 116: quiet hours FILE, they do not defer — and the copy that said otherwise |
| _(this commit)_ | This handoff |

## 3. The window follows the truck (107 §8, closed)

The zone synced once per sign-in, so a driver crossing into Kansas kept Denver's window
until the app was reloaded — **the same "local means local" defect 107 exists to fix, in
miniature.** A `visibilitychange` listener re-checks when the app returns to the
foreground; the existing dedupe makes it free, since nothing is sent unless the zone
actually changed. A test drives Denver → Chicago and asserts both PUTs, **proved RED by
disabling the listener** and watching it report only `['America/Denver']`.

## 4. Quiet hours FILE — the owner decision, and how it was found

**Going to add "3 alerts are waiting until 06:00" to the new control, I checked whether
they are. They are not.** A P1 suppressed for quiet hours is written `status=suppressed`
and **nothing ever sends it**: the worker runs five jobs — `tpims_dynamic`,
`tpims_static`, `eia_regional`, `document_expiry`, `detention_clock` — and none
re-dispatches. It is filed, and the driver sees it only if they open the inbox.

**The product asserted the opposite in three places:**
- `api/app/api/notifications.py` — *"Deferring a notification is considerate; destroying
  it is lossy."*
- `f08.inbox` — rendering held rows was justified because hiding them would mean the rule
  *"silently destroyed information rather than deferring it."*
- §23 entry 102 — *"quiet hours DEFER, they do not destroy."*

All three describe a mechanism **that was never built.** The reasoning for *rendering*
held rows is sound and is unchanged; what was wrong was the implied redelivery.

**OWNER DECISION (§23 entry 116): quiet hours file silently.** §13.3 now states it, and
adds the operative clause: **no surface may promise that a held notification will arrive
later.** The rejected branch argues for the chosen one — a *"30 minutes of free time
left"* held at 23:00 is **actively wrong** at 06:00, so a redelivery job would have needed
a per-class staleness rule nobody has specified.

**The copy was corrected too, because the decision made it false.**
`notifications.held` read **"Held until morning"** and renders on *every* suppressed row —
so it was **already wrong** for `budget`, `muted`, `resting` and `not_opted_in`, none of
which have a morning. It now reads "Held · not sent", true of all five reasons, in six
locales. The quiet-hours caption written the previous day was corrected in the same pass.

**The count was deliberately NOT built.** A surface that says how many are waiting is a
surface that says they are waiting. The honest version is a count of what is **unread**,
which is a fact rather than a promise — and §10.5 keeps it away from a badge.

## 5. The layout sweep is 179/181 under load, and that is worth reading

The full sweep failed with **`sheet-map-report` and `sheet-map-place` timing out on their
`ready` selector at 15 s**. Both **pass in isolation** — `sheet-map-report` at 21 s,
`sheet-map-place` at 11 s — and **all eight checks for this session's own new states
passed in the full run** (`sheet-notifications`, `facility-prompt-mute`).

The harness already documents this exact mode at `layout.spec.js:757`: *"Under four
workers the mocked overlay can land later than a lightly-loaded machine suggests, and a
`ready` that times out looks exactly like a broken surface — which is how three states
'failed' a run in which nothing about them was wrong."* The timeout was already raised
once, 5 s → 15 s.

**It is now marginal rather than comfortable**: `sheet-map-report` needs ~21 s even alone
on this machine, so the 15 s `ready` budget is inside the noise. **Do not read this as
green, and do not read it as a regression either.** The next person here should either
raise that budget again or give the map states their own worker count — a check that
fails when nothing is wrong is a check people learn to ignore, which is worse than not
having it.

## 6. Method notes

- **The `visibilitychange` guard was proved RED**, by disabling the listener.
- **The deferral finding came from trying to write copy, not from reading code.** Nothing
  flagged it; the assertion only surfaced because a sentence had to be true before it
  could be shipped. **Prose in a codebase is a claim about behaviour and it rots** — that
  is the rule §23 entry 116 ends on, and it is a sibling of 115's "a default is a claim
  about the world".
- **The false label predates this session by a long way.** "Held until morning" was wrong
  for four of the five suppression reasons from the day it was written, and no test
  caught it because every test asserts through the i18n key rather than the string.

## 7. Exact next task

**1. Push and deploy — this one matters more than usual.** The box is showing drivers
"Held until morning" about notifications that will never arrive, which is precisely what
§13.3 now forbids. `git push` then `./scripts/deploy.sh`.

**2. Then put a push on a real handset** — unchanged from 107 §7.1 and still the only
link in the notification stack no test here can exercise. Android Chrome on
https://haulmeter.online, sign in, More → notifications → turn on **both** "Turn on
alerts" and "Ask me about lots", park inside a truck-stop geofence for 15 minutes.
**Confirm the tray actions appear and that tapping one posts the report WITHOUT opening
the app.**

**3. Decide what to do about the map states' `ready` budget** (§5). Small, and it stops a
green suite from becoming a suite nobody trusts.

**4. Watch whether prompted beliefs disagree with volunteered ones** (§23 entry 112).
Check before the 1/day cap is ever raised.

**5. Give "claim paid" a second actor**, or accept it stays dormant (102 §4).

**6. Coverage.** 9 states (WI IN IA MN KS KY MI OH TX). Unchanged.

## 8. Debt

**New this session (108):**
- **The map states' `ready` budget is marginal** (§5).
- **An honest "what is waiting" surface does not exist.** The decision forbids promising
  delivery; it does not forbid telling a driver they have unread held notifications. That
  is a real gap — a driver who was not interrupted has no reason to open the inbox — and
  the shape of it is a §22.2 question, not a copy tweak.
- **No test asserts the SHAPE of a suppression label.** Every test compares against the
  i18n key, so "Held until morning" was wrong for four reasons for two sessions and the
  suite was green throughout. A test that renders each `suppressed_reason` and asserts the
  label does not claim a time would have caught it.

**Closed from 107:** the timezone now follows the truck · the defer/file question is
decided.

**Carried from 107:** a driver cannot override the zone if the browser reports it wrong
(deliberate — §23 116's "no picker" reasoning).

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
make up                              # local stack — it is DOWN
make test                            # pytest 1235 + vitest 594
make ui-layout                        # 181 states, ~6 min — see §5 before believing a red
make lint                            # ruff + import-linter 30/30
git push && ./scripts/deploy.sh      # the box is three commits behind (§7.1)
```

**The standing warning, fifth form.** 104: a suite answers "does this do what it was
written to do", never "is this reachable". 105: the agreement between two components can
be owned by neither. 106: the tests kept entering where a driver cannot. 107: the code was
right and the **default** was wrong. This one: **the code was right and the PROSE was
wrong.** Three files reasoned confidently about "deferring" and none of them checked that
anything defers; a label said "until morning" for four reasons that have no morning. None
of it was caught by a test, because tests assert against keys and comments assert against
nobody. **Read the sentences in this repo as claims, and check them like claims.**
