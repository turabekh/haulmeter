# HANDOFF-106 — the session the prompt became reachable

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 30 July 2026 · **Stack:** UP locally (`make down` to stop) · **Deployed:**
https://haulmeter.online (GCE, `uzimiz-prod`) — **BEHIND this handoff's work.** The box
has 105's token fix but no opt-in switch, so the prompt is still unreachable there.

**State in one line:** a driver can finally turn the lot-status prompt on — and silence
it at one lot without turning the whole class off.

> **This continues HANDOFF-105.** It set out to build 105 §8's mute and found that the
> class it would mute could not be switched on by anyone.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0055_f08_push_subscription** (no new migration; `muted_subjects` already existed) |
| Tests | **pytest 1211 · vitest 587 · layout 181 · ruff + import-linter 30/30** |
| §23 decision log | **114 entries** (114 this session) |
| Handoffs | 000 → 106 |
| Git | committed locally, **NOT pushed** — owner's call |
| Deployed | **STALE.** Needs a deploy before §7.1 is possible |
| Working tree | clean except untracked `collect_files.py` (not mine) |

## 2. What shipped

| Commit | What |
|---|---|
| `5526cc5` | The opt-in endpoints, the per-lot mute, `unmute_subject`, and the reachability test |
| _(this commit)_ | The two switches, six locales, the harness states, and these docs |

## 3. What was wrong — the third time, same shape

**`dispatch` applies opt-in class laws before any tier logic, `lot_status_prompt` is
`opt_in_default=False`, and nothing in the product could set that preference.**
`set_class_opt_in` had exactly one caller in the whole tree: the vendor-alerts route,
hardcoded to `VENDOR_ALERT`. No notifications endpoint, no client function, no control in
the sheet. So the prompt suppressed `not_opted_in` for **every driver, always.**

**Three defects, one feature, one shape — the tests reached past the door:**

| | The rule was right | Nothing could reach it | The tests |
|---|---|---|---|
| §23 112 | the prompt's refusal rules | `DWELL_TICK` never fires for an unarmed lot | called `prompt_for_lot_status` directly |
| §23 113 | `sw.js` reads the token correctly | `_adopt` never wrote it | called a test-only `setToken` |
| §23 114 | the class laws | no route could opt anyone in | called `set_class_opt_in` directly |

**Each time a green suite said it was fine.** Unit tests answer "do these rules work".
Only a test that comes in the front door answers "can anyone get here".

## 4. Two documents were wrong, and are corrected in place

- **104 §8** said "the only control is the class opt-in in the notifications sheet."
  There was no such control. **Believing there was one is why nobody looked for it** —
  which is why the line is corrected rather than deleted.
- **104 §7.1 and 105 §7.1** told the owner to enable alerts and park. That enables
  **push**, not the **class**, so the handset test they name would have failed as
  `not_opted_in` and pointed at the wrong layer. I relayed those steps to the owner
  verbatim last session; they would not have worked.

**A false claim about a control is worse than a missing one, because it closes the
question.**

## 5. What was built

- **`GET /notifications/classes`** — key, `opted_in`, default, cap, tier. A screen renders
  the driver's real answer instead of guessing; "no row" is an answer (the default), not
  missing data.
- **`PUT /notifications/classes/{key}/opt-in`** — one route both ways, because §21.8 makes
  off exactly as easy as on. Validated against the code-defined registry: an unknown key
  is a **404**, not a preference row that governs nothing. Generic, so a new class needs
  no new endpoint. **Only `lot_status_prompt` is surfaced** — `vendor_alert` has its
  control in More already, and `protection_gap` is on by default for a stated reason, so
  a switch for it is a separate decision.
- **`unmute_subject` in F8, which did not exist.** The only way out of a mute was
  `follow_subject` — vendor-shaped, and it switches the whole class on. So the mute was a
  one-way door. It leaves `opted_in` alone (un-silencing one lot is not a class-level
  choice) and returns None on no row, so `is_opted_in` keeps reading the default:
  "never asked" and "answered no" must not collapse into each other.
- **`GET`/`POST` `…/prompt-pref`, `mute-prompts`, `unmute-prompts` on M1**, all through
  `Depends(canonical_facility_id)`. Two POSTs rather than one PUT so both directions go
  through `queuedPost` and survive a dead zone; the class switch is not queued because it
  is not a roadside action.
- **The two controls.** The class switch in the notifications sheet (the placement §23 112
  already approved); the mute toggle on `/facility/<id>`, **owner-chosen**, reversible in
  place — mute and un-mute are the same control in the same place, because a mute a driver
  cannot see is a mute they cannot undo.

## 6. Method notes — two guards proved, one harness caught lying

- **The reachability test is the point of the session**
  (`tests/api/test_prompt_reachability_api.py`). Register → opt in → ping, all over HTTP,
  never through a service function. It was RED before the endpoint existed. Its sibling
  `test_without_opting_in_the_driver_is_not_asked` **passed on the old code**, which is
  the cleanest possible evidence of the bug: every driver was in that state.
- **The merged-id guard proved RED** by removing `Depends(canonical_facility_id)` and
  watching the returned id diverge from the canonical one. Without it a driver taps "don't
  ask about this lot", gets a 200, and is asked again the next night.
- **THE LAYOUT HARNESS PASSED BOTH NEW CONTROLS WHILE MEASURING NEITHER** — exactly what
  105 §9 warned about, one session later. Unmocked routes 404 in that harness and both
  controls render only once the server answers, so `sheet-notifications` went green having
  measured a sheet with no switch in it. Fixed by mocking the class route, adding a
  `facility-prompt-mute` state, and pointing `ready` at the **new** control rather than at
  a row that renders anyway. **Proved by disabling the mock and watching all four checks
  fail.** 177 → 181.
- **Driven on the running stack, four drivers over HTTP:** opted in → **asked**; muted
  that lot → **suppressed `muted`**; muted then unmuted → **asked again**; never opted in
  → **suppressed `not_opted_in`**. Every ping returned `events=[]` — 112's shape (c) still
  holding, the prompt firing with no geofence event at all.
- **Then the same loop in a real browser**, registering through the login screen: both
  switches tapped, both verified against the server in both directions.
- The dev DB now holds five `drive-…@example.com` and one `ui-drive-…@example.com`
  account, plus the `idb-verify-…` pair from 105.

## 7. Exact next task

**1. Deploy, then put a push on a real handset.** The box cannot do this yet — it has no
opt-in switch. After `./scripts/deploy.sh`: Android Chrome on https://haulmeter.online,
sign in, More → notifications → **turn on BOTH** "Turn on alerts" (push) and "Ask me
about lots" (the class), then park inside a truck-stop geofence for 15 minutes. **Confirm
the tray actions appear and that tapping one posts the report WITHOUT opening the app.**
That last hop — browser → service worker action — is the only link in this feature no test
here can exercise.

**2. Watch whether prompted beliefs disagree with volunteered ones.** §23 entry 112 flags
it and it is finally *possible* to measure, because prompts can now reach drivers.
**Check before the 1/day cap is ever raised.**

**3. Quiet hours and the driver's timezone have no surface either.** §13.3 says "default
22:00–06:00 local (driver-adjustable)" and `NotificationPrefs.quiet_start/quiet_end` are
written by **no route** — so every driver is on the default window in the default
timezone. Same class of gap as this session's, and a bigger blast radius: it affects every
P1, not one class. **This is the one I would do next.**

**4. Give "claim paid" a second actor**, or accept it stays dormant (102 §4).

**5. Coverage.** 9 states (WI IN IA MN KS KY MI OH TX). Unchanged.

## 8. Debt

**New this session (106):**
- **No place lists every lot a driver has muted.** The accepted cost of the in-place
  toggle; revisit only if muting turns out to be common.
- **The generic opt-in endpoint will accept `protection_gap`**, which is on by default
  because a driver cannot opt in to a warning they have never seen. Nothing surfaces it,
  deliberately, but the route would let a client switch it off.
- **`GET /notifications/classes` returns every class including ones with no surface**, so
  a future client could render a switch for something the design has not decided on.

**Carried from 105:** no push has reached a real handset · `sw.js` hardcodes
`/api/map/report` (right deployed, wrong in dev) · no test asserts that `setToken` is
unused by production code · the manifest ships with `"icons": []` · no push telemetry ·
iOS untested.

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
make test                            # pytest 1211 + vitest 587
make ui-layout                        # 181, ~2.5 min — run it alone
make lint                            # ruff + import-linter 30/30
make vapid-keys                      # prints a pair; paste into infra/.env by hand
./scripts/deploy.sh                  # ship to haulmeter.online — NEEDED for §7.1
```

**The standing warning, third form.** 104 said a suite answers "does this do what it was
written to do" and never "is this reachable". 105 said the agreement between two
components can be owned by neither. This session found the same feature broken a third
time and adds the sharpest version: **the tests kept reaching past the front door.** Every
one of the three defects was invisible because the suite entered where a driver cannot —
calling the service function, calling the test-only setter, calling the prompt directly.
And the layout harness did it again in miniature, passing two controls it had not
rendered. **Come in the front door. If no test does, the feature is not built yet.**
