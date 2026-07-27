# HANDOFF-094 — the session that stopped believing the documents

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 27 July 2026 · **Stack:** UP (`make down` to stop).

**State in one line:** the Load tab is **complete to §10.2** and §5's state machine finally
*runs* — and the way both happened was by opening screens and running commands instead of
trusting what this repo's own documents said about itself.

> Supersedes HANDOFF-093. That covered the first half of the day (F3's sensor, FR5's carve-out);
> this covers the Load tab passes, the DoD sweep, SM-3, and the state deriver.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0051_f05_stop_appointment_source** |
| Tests | **pytest 1021 · vitest 398 · layout 481 · ruff clean · import-linter 30/30** |
| §23 decision log | **62 entries** (52–62 are today) |
| Handoffs | 000 → 094 |
| Git | 262 commits · `main` is **13 ahead of `origin/main`** (local only, HANDOFF §4.3) |
| Services | **running** |

## 2. The one thing to carry forward

**Six documents in this repo asserted something the code did not do**, and every one was found
by running the thing rather than reading about it:

| Claim | Reality |
|---|---|
| HANDOFF-087: FR1 "complete end to end (window + provenance + **verdict**)" | the verdict reached no screen |
| `LoadSurface.vue`: "the protection is the WINDOW, not the verdict" | an **unlogged** decision contradicting HANDOFF-085's own task |
| `Makefile`: "`make ci` runs both" | `make ci` could not pass **in either state** |
| `state.js`: "state is derived from F3 motion/geofence signals" | nothing derived anything; `setState` was called only from tests |
| §22.3's DoD, ticked | three boxes were false, incl. a camera opening at speed |
| the Meter's `appointment_source` | credited a parse for a value the parse never supplied |

§23 entry 42 already named this failure mode — *"the original sentence recorded an intention as
an accomplishment"* — and called it the most instructive defect the build has produced. It is
still producing it. **Treat every completion claim in these handoffs as unverified until you run
it.** That includes this one.

## 3. What shipped (§23 entries 57–62)

**The Load tab, third pass (57).** A claim could be filed for **$0.00** — and §9 freezes the
Meter at the filed amount while the UI hides every claim control once filed, so the screen read
`$0.00 · clock stopped` while detention went on accruing, **with no route back**. Measured: filed
at zero, three minutes later the meter still said $0.00 while the API had $4.42. Fixed by guarding
the *offer*, not by unfreezing the Meter. The pre-arrival Meter also rendered a **static clock
face** — the same figure the Appointment row states two lines below — so §9's "counting figure"
now counts down to the appointment and up once it passes.

**M5-FR1's verdict (58).** `within_window` is filed on **every** arrival and reached no screen;
the only exposure was the `/arrive` response, which the Load tab discards, so a reload lost it.
It is now the evidence checklist's **fourth row** — which is where it belongs, because FR5's
`protection_summary` has always computed four documented items while the screen rendered three.

**The §22.3 sweep, run rather than ticked (59).** `ConditionSurface` — whose file input carries
`capture="environment"` — had **no DRIVING behaviour at all**, on a route with no guard. And
DocsSurface's capture *chip* was guarded while the *sheet* it opens was not.

**SM-3, declared and enforced (60).** Seven of thirteen driver surfaces had no DRIVING behaviour;
**§10.3 specifies the Money tab's** and it had never been implemented. The obvious fix — a global
redirecting `beforeEach` — is **forbidden by §13.5**, so the guard is a declaration plus
`driving-posture.test.js`.

**§5's deriver (61).** See §4.

**The appointment's whole lifecycle (62).** The parse extracted an appointment and the confirm
sheet **threw it away**, so every load created the PRIMARY way had a null window. Provenance moved
to the stop (0051), and `PATCH /load/{stop}/appointment` gives FR1 the correction it was
incomplete without.

## 4. `DriverState` was permanently IDLE

The largest instance of the pattern: **an entire section of the constitution with nothing reaching
it.** Every DRIVING behaviour in the product — §10.2's glance card, §11.4 Corridor mode, §10.3's
read-only Money, §10.4's inspection confirm, and the seven surfaces' guards shipped an hour
earlier — was correct and **inert**.

It was only buildable because F3 grew an inbound seam this morning: `/location/ping` carries
`speed_mps`. **Verified in a real browser**, not just in tests: `DRIVING reached after ~65s of
motion`, `data-state: driving`, and the T-1 type bump measured at body 16→18, title 20→22,
meter 44→52 — which had never once executed in production.

**RESTING is deliberately not derived.** §5 triggers it on "stationary >20 min at a **parking-type**
facility"; the client has no facility type. Deriving from time alone would put a driver waiting on
a receiver's dock at 7pm into RESTING and **mute their notifications to P0**.

## 5. Exact next task — Session 14

1. **§5's ON_SITE behaviour — an owner decision, not a task.** ON_SITE is now *reachable* and
   still changes nothing. §5 wants "capture actions one tap from anywhere via a persistent action
   chip", which is a new component pattern **and** navigation structure — both §22
   never-improvise. Logged as an open proposal; it needs a decision before any code.
2. **The 200% reflow assertion.** The last mechanically-closeable §22.3 box: the harness already
   drives a real browser at 360 dp, so the same assertions at 200% text scale are a small addition
   and would retire T-5 honestly.
3. **Then M6**, chosen for a finish line inside our control rather than by numeric order.

## 6. The Load tab — what is actually left

§10.2's anatomy is **complete and measured**: Meter (resting / countdown / free time / accruing /
filed), stop context with provenance and correction, four-row evidence checklist, next-stop
preview, single-CTA ladder, empty state, history, DRIVING glance, §15.5 degraded card.

Left: **ON_SITE** (above), and three DoD boxes that are *not claimed*: 200% reflow, Android back
behaviour, §20 performance budgets.

## 7. Debt — logged, not worked around

**New today**

- **`make ci` needs a stopped stack** (`make down` first) — `preflight` asserts the ports are free.
- **Dead-zone pings are dropped, not queued** — a transition with no signal is lost. The honest fix
  is client-side geofencing that reports the crossing with its own timestamp.
- **`POST /load/{stop}/end` emits no EXIT**, so ending without moving leaves the presence row open.
- **No in-app notification centre** — `protection_gap` dispatches and F8 records it, but nothing
  renders §13.4's tray entry.
- **DRIVING thresholds are reasoned, not calibrated** — 2.5 m/s / 60s / 90s come from §5's wording,
  not from real GPS traces. The first road test may move them.
- **The map facility card and fuel-price sheet stay unmeasured** — both need a Mapbox pin tap.
- **`make ui-layout` is ~9 min**, the long pole in CI.
- **`API_BASE` is hardcoded** to `http://localhost:8008`; fine as a dev seam, fatal on a device.
- **M2-FR4 does not exist** — the micro-review prompt five handoffs cited as precedent. It now has
  a working EXIT hook available to it; what it lacks is a decision.

**Carried**

- M4 and M9 still send the model a `content_hash`, not the document.
- F9's required-keys check tests presence, not value; F9 talks raw httpx, not the SDK.
- No ICU plurals; the rate-con import is not offline-capable; no geocoder.
- Hard delete for a mis-capture — the §17 Q16 carve-out the owner deferred.
- No global voice affordance (M11); the status-strip mic stays disabled and labelled.
- F2 geohash-boundary duplicate miss; `merge_facilities` staleness.
- `collect_files.py` sits untracked at the repo root and is not ours to commit or delete.

## 8. Commits since HANDOFF-093 (newest first)

```
e0210cd The parse read the appointment and the confirm sheet threw it away
0f78510 DriverState was permanently IDLE, so every DRIVING behaviour was unreachable
f0953d9 Seven of thirteen driver surfaces had no DRIVING behaviour at all
8f0c5a1 A camera-first capture screen had no DRIVING behaviour at all
3fa9bef The on-time verdict was computed on every arrival and shown nowhere
dc1eb00 A claim filed for $0.00 froze the meter at nothing
```

## 9. Key files touched

```
MIGRATION 0051_f05_stop_appointment_source
F5   models.py (Stop.appointment_source) · service.py (set_stop_appointment,
     add_stop provenance) · public.py
M5   service.py (on_time_proof_for_stop) · public.py
API  load.py (on_time + arrived_at on the meter, PATCH /{stop}/appointment,
     stop-owned provenance)
UI   core/state.js (THE DERIVER: observeMotion, thresholds, ON_SITE)
     core/location.js (feeds it; displacement fallback for a null speed)
     core/api.js (correctAppointment) · core/app-shell.scss (.driving-note)
     router.js (meta.driving on all 13 driver routes)
     LoadSurface · RateConImportSheet (the appointment field)
     ConditionSurface · DocsSurface · MoneySurface · BookingSurface
     FuelSurface · LoadCalcSurface · AuditSurface · FacilityProfileSurface (SM-3)
     VoiceSheet · IncidentSheet · HandoffSheet · MapSurface (§6.5)
     i18n/*.json ×6 (+13 keys)
TEST test/driver-state.test.js (NEW) · test/driving-posture.test.js (NEW)
     location.test.js · ui-components.test.js · test_load_api.py · test_load_import.py
     layout.spec.js (sheet-appointment → 481)
MAKE ui-layout brings up `ui`; ci ordered so preflight runs first
DOCS design-prd.md §23 entries 57–62
```

## 10. Ports / env / flags

**No port, flag or env changes.** One migration (0051), one new route
(`PATCH /load/{stop}/appointment`), one new notification class from earlier today
(`protection_gap`).

## 11. Restarting

```
make up          # preflight, then the full stack
make test        # 1021 pytest + 398 vitest
make ui-layout   # 481 mobile-first checks at 360 dp (~9 min)
make down && make ci   # all four gates from cold — verified 27 Jul
```
