# HANDOFF-093 — the session that checked its own premise and found a missing sense

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 27 July 2026 · **Stack:** UP (`make down` to stop).

**State in one line:** a task that said *"verify this premise before building on it"* found the
premise false in two ways — **geofence EXIT could not fire in production at all** — so F3 grew
the sensor it never had, and M5-FR5's carve-out, deferred across five handoffs, is now closed on
top of it.

> Supersedes HANDOFF-092, which covered the first half of this session (the Load tab and the
> sheet coverage). Both halves are summarised here; 092 keeps the detail on the UI work.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0050_f06_document_archive_reason** (unchanged — no migration this session) |
| Tests | **pytest 1014 · vitest 377 · layout 466 · ruff clean · import-linter 30/30** |
| §23 decision log | **56 entries** (52–56 are this session) |
| Handoffs | 000 → 093 |
| Git | 255 commits · `main` is **6 ahead of `origin/main`** (local only, HANDOFF §4.3) |
| Services | **running** |

## 2. What this session was

Two halves, one habit: **ask whether the thing actually does what the document says**, and check
by running it rather than by reading it.

**First half (detail in HANDOFF-092):** the Load tab was rebuilt where it was lying — an empty
state that ran a fixture load with $37.52 of ticking fake detention, a raw ISO timestamp in
§10.2's stop context row, a "BOL captured" label that could only read as done. Then the LAW 0
harness went **136 → 466 checks** and now opens **eighteen sheet states**, which is how it found
that `EvidenceSurface` styled none of its own action controls.

**Second half (this document):** the FR5 task, and what verifying its premise turned up.

## 3. The premise was false in two ways (§23 entry 55)

Five handoffs had queued: *"FR5's EXIT carve-out — verify M2-FR4's micro-review prompt really
fires on geofence EXIT before relying on it as precedent."*

**(a) M2-FR4 does not exist.** M2 can `submit_review`, `moderate_review`, `list_reviews`. Nothing
prompts — no trigger, no notification, no UI. PRD §215 specifies it; it was never built.

**(b) Geofence EXIT could not fire at all.** `evaluate_ping` is the only emitter of
ENTER/EXIT/DWELL_TICK, and in application code it had **exactly one caller**:

```
api/app/api/load.py   POST /load/{stop}/arrive
  location.evaluate_ping(db, account.id, lat, lon, ...)   # lat/lon = the facility's OWN coords
```

By construction that can only land *inside*. Every other caller in the repo was a test or
`scripts/seed_demo.py`. No route ingested a position, the UI never sent one, `record_ping` was
exported by F3's public and called by nothing, and `POST /load/{stop}/end` emitted no EXIT.

**Measured, not reasoned:**

```
every facility a real driver had touched   ENTER n, EXIT 0
the only EXIT rows in the whole database   "Dallas Distribution Center (demo)"  (seed_demo: # far -> exit)
arrive -> end on a fresh load              ENTER, and nothing else — though the load reached `completed`
```

**The blast radius was never FR5.** F3's dwell pairing walks ENTER→EXIT and skips an unclosed
ENTER — so **M2's `dwell_stats` and `detention_risk` had been computing over an empty sample**,
which is §11.7's whole honesty apparatus running on nothing — and M3's `_arrival_departure`
always returned `departure = None`.

> **A foundation capability with no inbound seam is not a capability.** Seventh instance of that
> shape in this project, and the first where the missing half was a *sensor* rather than a screen.

## 4. What was built

**`POST /location/ping`** — F3's inbound seam. Server time authoritative (PRD §7.3), the client's
clock recorded as skew rather than trusted, events returned so a surface can react to its own
movement without polling.

**`ui/src/core/location.js`** — the sensor. F3's adaptive sampling implemented as the ≤5%/day
battery budget: significant-change while idle, high-accuracy only while a stop is armed, which is
exactly when ±3-minute arrival detection is being judged.

**A position is the one write that must NEVER queue.** Every other capture queues through F12,
because a photo taken in a dead zone is still true an hour later. A position is not: the server
evaluates it at server time, so a replayed ping would be judged as happening *now* and could
fabricate an ENTER at a dock the driver left this morning. **A lost EXIT is a gap; a fabricated
one is a lie in an evidence chain.**

**§15.5's degraded-location card** — shipped because this made it load-bearing. The meter now
depends on a permission. Copy states the *consequence* ("arrivals aren't detected — start the
meter yourself"), not the permission; `unavailable` gets no card, because there is no one-tap fix
for a desktop browser and offering one would be the dead-control pattern.

## 5. FR5's EXIT carve-out (§23 entry 56)

**The notification class was the owner's decision, not a composition** — §22 makes it a
never-improvise category. Approved: **`protection_gap` — P1, exempt from §13.1's 2/day budget,
capped at 1/day, on by default, still silent in quiet hours and while RESTING.**

**"Exempt" is enforced in both directions**, which is the half that is easy to miss: the class
skips the budget check **and** its sends are excluded from `p1_budget_used`. A class that skipped
the check while still consuming a slot would quietly spend one of the driver's two ordinary
nudges to pay for itself.

**Only some gaps are irrecoverable, and that distinction is the design.** A trailer photograph and
a signed BOL can be taken at that dock and nowhere else. **On-time proof is different** — F5 files
it from the arrival record at `/arrive`, so driving away changes nothing about it, and warning
about it would be exactly the nag the budget exists to prevent. `IRRECOVERABLE_ON_EXIT` is
deliberately shorter than `missing`.

**Verified live, and the verification is the design working:**

```
P1 · protection_gap · "Missing: BOL, pickup photos, delivery photos"
  -> /load/{stop}/evidence
  status: suppressed    reason: quiet_hours          (the run was 04:39 UTC)
```

Exempt from the budget, not from the driver's sleep.

## 6. Three defects found in our own work

- **The sampler's throttle was claimed after the `await`**, so every fix arriving while a request
  was in flight also passed it — a burst of fixes became a burst of POSTs, defeating the budget
  the throttle exists to keep. Claimed on attempt now.
- **The first FR5 tests used `datetime.now()`** and every dispatch came back `quiet_hours`,
  because §13.3's default window covers a third of the day. Same shape as HANDOFF-091's m13
  flake — **a clock the test does not control is a clock the test is at the mercy of.**
- **A `flex: none` fix broke its neighbour** (first half): it stopped `.voice__send` collapsing
  and made the row overflow 360 dp, because `.voice__input` carried flex's default
  `min-width: auto`. The harness caught the regression in the same run that confirmed the fix.
- **`make ci` had never been runnable at all** — see §13. Found by running it, not reading it.

## 7. Exact next task — Session 13

1. **The M5 DoD close-out** — the §22.3 sweep. The layout half is now genuinely earned (466
   checks, sheets included); what remains is the non-layout half: six locales, offline,
   DRIVING-state, a11y, stated plainly per surface.
2. **Decide M2-FR4** — build the micro-review prompt or strike it from the PRD. It now has a
   working EXIT hook available to it, so it is cheap; what it does not have is a decision.
3. **Then M6**, chosen for a finish line inside our control rather than by numeric order.

## 8. Debt — logged, not worked around

**New this session**

- **No in-app notification centre.** `protection_gap` dispatches and F8 records it, but nothing
  renders the tray entry §13.4 describes. Building one is a navigation decision (§22
  never-improvise), so it was not filled in quietly.
- **Dead-zone pings are dropped, not queued** — deliberate (see §4), and it means a transition
  that happens with no signal is lost. The honest fix is client-side geofencing that reports the
  crossing *with its own timestamp* and a server that trusts it under narrow conditions; that is
  a design decision, not a patch.
- **`POST /load/{stop}/end` still emits no EXIT.** Now that real pings exist this is mostly
  moot, but a driver who ends a load without moving leaves the presence row open.
- **The map facility card and fuel-price sheet remain unmeasured** — both need a Mapbox pin tap
  and the harness has no token.
- **`make ui-layout` is 9.6 min**, the long pole in CI.
- **`API_BASE` is hardcoded** to `http://localhost:8008` in `ui/src/core/api.js`; fine as a dev
  seam, fatal on a device.
- **Probe accounts and loads** in the dev database from live verification. Harmless; purge freely.

**Carried**

- M4 and M9 still send the model a `content_hash`, not the document.
- F9's required-keys check tests presence, not value; F9 talks raw httpx, not the SDK.
- No ICU plurals; the rate-con import is not offline-capable; no geocoder.
- Hard delete for a mis-capture — the §17 Q16 carve-out the owner deferred.
- F5 has no path to correct a parsed appointment window.
- No global voice affordance (M11); the status-strip mic stays disabled and labelled.
- F2 geohash-boundary duplicate miss; `merge_facilities` staleness.
- `collect_files.py` sits untracked at the repo root and is not ours to commit or delete.

## 9. Commits this session (newest first)

```
b7cdfe6 A deadline is not a nag: FR5 fires when the evidence stops being capturable
b13adee Geofence EXIT could not fire, so F3 grew the sensor it never had
f900be3 docs: HANDOFF-092 — the session the harness stopped agreeing with us
e5dc17f A screen that produces broker evidence had no styles for its buttons
64a3096 The workhorse component had never been measured
933a014 The Load tab's empty state was a load nobody had
```

## 10. Key files touched (second half)

```
API  api/location.py (NEW — POST /location/ping, the EXIT composition point)
     main.py (router)
F8   service.py (NotificationClassSpec.budget_exempt, PROTECTION_GAP_CLASS,
                 BUDGET_EXEMPT_CLASSES, p1_budget_used exclusion) · public.py
M5   service.py (IRRECOVERABLE_ON_EXIT, irrecoverable_gaps,
                 notify_protection_gap) · public.py
UI   core/location.js (NEW — the sensor) · core/api.js (sendLocationPing)
     App.vue (start/stop) · LoadSurface.vue (§15.5 card)
     i18n/*.json ×6 (+load.geo_off, +load.geo_fix)
TEST tests/api/test_location_api.py (NEW, 15) · ui/test/location.test.js (NEW, 10)
     ui-components.test.js (§15.5 card)
DOCS design-prd.md §23 entries 55, 56
```

## 11. Ports / env / flags

**No port, flag, migration or env changes.** One new route (`/location/ping`) and one new
notification class (`protection_gap`).

## 12. Restarting

```
make up          # preflight, then the full stack
make test        # 1014 pytest + 377 vitest
make ui-layout   # 466 mobile-first checks at 360 dp (~9 min)
make ci          # all four gates from a COLD stack — verified end to end this session
```

**`make ci` must be run from a stopped stack** (`make down` first): `preflight` asserts the host
ports are *free*, and with the stack up it correctly reports all 8 as held by Docker. From cold it
now passes end to end — see §13 for why it could not before.

## 13. `make ci` had never been runnable

The documented CI-parity target **could not pass in either state**, and finding out took running
it rather than reading it:

| Gate | Requires |
|---|---|
| `preflight` | host ports **free** → stack **down** |
| `ui-layout` | `http://ui:9008` resolving → ui service **up** |

`compose run` *replaces* a container's command, so `ui-layout`'s one-off runner never started
vite and nothing was listening on 9008. From a cold stack all 466 checks failed with
`net::ERR_NAME_NOT_RESOLVED`; from a warm stack `preflight` failed on 8 ports. Five sessions of
handoffs quoted "`make ci` runs both" as though it were true — everyone ran `make up` and then
`make ui-layout`, so the two halves were only ever exercised separately.

**Fixed:** `ui-layout` now runs `compose up -d ui` before measuring, and `ci` keeps `preflight`
first, while everything is still down. Verified: `make ci` from a cold stack, **exit 0**.

**The same shape as everything else this session** — a capability that reads as working from
whichever side you inspect it and has never been exercised end to end.
