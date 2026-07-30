# HANDOFF-105 — the session the tray answer turned out to be decoration

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 30 July 2026 · **Stack:** UP locally (`make down` to stop) · **Deployed:**
https://haulmeter.online (GCE, `uzimiz-prod`) — **BEHIND by this handoff's fix.** The
box still has the version where a tray tap cannot post.

**State in one line:** the lot-status prompt's tray buttons worked; answering with one
could never send anything, and now can.

> **This continues HANDOFF-104.** 104 §7.1 named "put a push on a real handset" as the
> next task, and reading the path it was meant to test is what found this.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0055_f08_push_subscription** (no new migration; no API change at all) |
| Tests | **pytest 1193 · vitest 578 · layout 177 · ruff + import-linter 30/30** |
| §23 decision log | **113 entries** (113 this session) |
| Handoffs | 000 → 105 |
| Git | committed locally, **NOT pushed** — owner's call |
| Deployed | **STALE.** The fix is local only |
| Working tree | clean except untracked `collect_files.py` (not mine) |

## 2. What shipped

| Commit | What |
|---|---|
| `ea87d18` | The token mirror moves to the ref; the seam gets its first test (§23 113) |

## 3. What was wrong

**Entry 112 shipped tray buttons so a driver could answer from a locked phone. The
answer could never be sent.** The path crosses two files that met in no test:

- `ui/src/core/api.js` **writes** the session token to IndexedDB.
- `ui/public/sw.js` **reads** it, because a service worker cannot reach localStorage.

`mirrorTokenToIdb` had two callers — `logout`, and **`setToken`, which is test-only.**
Nine files under `ui/test/` call it; no production code does. The real sign-in is
`login`/`register` → `_adopt`, which set the ref, called `persist()`, and mirrored
nothing. The boot restore assigns the ref directly and mirrored nothing either.

So `readToken` resolved `null` for every driver, `reportLotStatus` returned `false`, and
every tray tap fell through to `openWindow`. **That is a deliberate fallback, which is
why nothing looked broken:** the buttons appeared, tapping one opened the app at the
facility, and the one-tap-from-a-locked-phone design was decoration.

## 4. Why the suite was no help — read this one

**happy-dom implements no IndexedDB.** So `mirrorTokenToIdb`'s own
`typeof indexedDB === "undefined"` guard — written so a browser with IDB blocked still
signs in — made the mirror a silent no-op in **every test that has ever run in this
project.** It was never exercised, not once.

And the tests that did touch it called `setToken`, **exercising a path production does
not take.** That is HANDOFF-104 §4 again, one layer up: there, thirteen tests called
`prompt_for_lot_status` directly and proved rules nothing invoked.

**`api.js` is the most-tested module in the UI. `sw.js` had no test at all.** The
assertion that would have caught this — *the token the app writes is the token the worker
reads* — belonged to neither file, so nobody was missing it. **A writer and a reader in
two files with no test across the seam is an untested integration however green both ends
are.**

## 5. The fix, and why it is shaped this way

`watch(token, mirrorTokenToIdb, { immediate: true, flush: "sync" })` replaces both
hand-placed calls.

- **The write belongs to the ref, not to a caller.** One mechanism instead of two, and
  the next code path that sets a token cannot forget. Structural rather than guarded —
  the same reasoning as the prompt's DRIVING ban being enforced by its trigger.
- **`flush: "sync"` keeps the timing of the calls it replaces**, so this changes where
  the write is decided, not when it happens.
- **`immediate` is the operational half.** A driver already signed in on the box has a
  localStorage session and an empty IndexedDB; it mirrors on their next app open. **No
  sign-out, no re-enrolment** once this deploys.
- `persist()` was left alone. All three of its call sites are correct, and folding it in
  is a wider refactor than this bug needed.

## 6. Method notes

- **The test drives the real `ui/public/sw.js`**, read off disk and evaluated with an
  injected `self`, rather than a copy of its rules. sw.js's own argument for deciding
  nothing is that a vocabulary living elsewhere goes stale — and a test is elsewhere. A
  duplicated `LOT_STATUS` map would have passed against the same broken file.
- **`fake-indexeddb` is a new devDependency** for the same reason: a hand-rolled double
  can be wrong in exactly the shape the code is wrong and prove nothing. **It changes the
  ui image** — `make up` or `docker compose build ui` after pulling, or the new test file
  cannot resolve it.
- **Verified in a real browser against the real API, in both directions.** Registering
  through the actual login screen: `haulmeter`/`kv`/`token` matches localStorage; delete
  the key, reload, it comes back. **With the fix reverted the same script reports `null`,
  and still `null` after reload** — so the verification detects the defect rather than
  agreeing with the code. Five of the eleven new unit tests were RED before the change.
  - Two proxies were needed to do it: the dev app calls `http://localhost:8008` and the
    API's dev CORS allowlist is exactly `http://localhost:9008`, so the browser has to
    see both on its own localhost or the run measures a CORS failure instead of the
    mirror. §23 entry 92's trap, from the other side.
- The dev DB now holds two `idb-verify-…@example.com` accounts from those runs.

## 7. Exact next task

**1. Put a push on a real handset — now worth doing, because the thing it tests can
work.** Unchanged from 104 §7.1 except that it was guaranteed to fail before. Requires a
**deploy first**, which is the owner's call. Then: Android Chrome on
https://haulmeter.online, sign in, More → notifications → "Turn on alerts", park inside
a truck-stop geofence for 15 minutes. **Confirm the tray actions appear and that tapping
one posts the report WITHOUT opening the app.** If the app opens, the token did not reach
IndexedDB on that handset and §8's first item is back.

**2. Watch whether prompted beliefs disagree with volunteered ones.** §23 entry 112
flags it; nothing has measured it. **Check before the 1/day cap is ever raised.**

**3. Give "claim paid" a second actor**, or accept it stays dormant (102 §4).

**4. Coverage.** 9 states (WI IN IA MN KS KY MI OH TX). Unchanged.

## 8. Debt

**New this session (105):**
- **`sw.js` hardcodes `/api/map/report`.** Right deployed (`VITE_API_BASE=/api`, same
  origin), wrong in local dev where the API is on 8008 with no prefix — so a dev tray tap
  still falls back to opening the app and local testing of it is not possible. Fixing it
  means the server sending its own base in the push payload.
- **No test asserts that `setToken` is unused by production code**, which is the thing
  that made this bug invisible. A dead-export check across `ui/src/` would have found it,
  and would probably find others.

**Resolved from 104:** the tray answer now has unit coverage across the seam and is
verified in a real browser — but **still never answered from an actual phone's tray**,
which is §7.1.

**Carried from 104:** `stationary_since` runs on every ping · nobody can turn the prompt
off from inside a prompt (`mute_subject` exists in F8 and `m13_vendor.py:347` already
uses it for vendor alerts, so there is a pattern to copy).

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
make up                              # local stack — REBUILDS ui for fake-indexeddb
make test                            # pytest 1193 + vitest 578
make ui-layout                        # 177, ~3 min — run it alone
make lint                            # ruff + import-linter 30/30
make vapid-keys                      # prints a pair; paste into infra/.env by hand
./scripts/deploy.sh                  # ship to haulmeter.online — NEEDED for §7.1
```

**The standing warning, in the form this session found it.** 104 ended by saying a suite
answers "does this do what it was written to do" and never "is this reachable, is it
measured, is it still true today". This session found the same defect one layer up, and
the new part is *why nobody could have noticed*: **the two ends of the path were each
well covered, and the agreement between them was owned by neither.** The guard that let a
browser without IndexedDB sign in also stopped the test suite from ever seeing the
feature — a defensive line doubling as a blindfold. **Ask what two components agree
about, not whether each one does what it says. And drive the real thing.**
