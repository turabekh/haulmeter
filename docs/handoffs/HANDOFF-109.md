# HANDOFF-109 — the session that measured the flake instead of believing it

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 31 July 2026 · **Stack:** **UP** · **Deployed:** https://haulmeter.online (GCE,
`uzimiz-prod`) — **CURRENT.** 108's three commits are pushed and live, so the box has
stopped telling drivers "Held until morning" about notifications that never arrive.

**State in one line:** the false copy is off production, and the layout harness's
"known flake" turned out to be a real failure that the proposed fix would have buried.

> This continues HANDOFF-108. It closes its §7.1 and its §7.3, and it **corrects 108 §5**,
> which was wrong on the numbers.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0055_f08_push_subscription** (no new migration) |
| Tests | **pytest 1235 · vitest 594 · ruff + import-linter 30/30** |
| Layout | **181 states, 181 passed** — twice, once under heavy load. No flake observed. |
| §23 decision log | **116 entries** (none added — see §4) |
| Handoffs | 000 → 109 |
| Git | one commit ahead of `origin/main` (this session's harness fix + this doc) |
| Deployed | **CURRENT** as of this session |
| Working tree | clean except untracked `collect_files.py` (still not mine) |

## 2. What shipped

| Commit | What |
|---|---|
| `5f987a9`…`71e1855` | 108's three commits — **pushed and deployed**, nothing new in them |
| `af2dda1` | A `ready` timeout is a defect, not weather — and it now says which |
| _(this commit)_ | This handoff |

## 3. The deploy (108 §7.1, closed)

Pushed `bd15495..5f987a9` and ran `./scripts/deploy.sh`. **Verified against the artifact
rather than the script's "done"**, which is the only check that means anything here: the
served JS bundle renders **"Held · not sent"**, and a scan of every served asset for
`until morning` / `hasta la ma` / `до утра` returns **zero hits**. All six locales carry
the corrected string. `/api/health` → `{"status":"ok","environment":"test"}`.

The outgoing diff was scanned for secrets before the push (rule 3, public repo). Every
hit was doc prose or a test fixture like `"tok-crossing"`.

## 4. 108 §5 WAS WRONG, and the fix it proposed would have made things worse

108 §5 recorded the map states' `ready` budget as marginal — *"`sheet-map-report` needs
~21 s even alone on this machine, so the 15 s `ready` budget is inside the noise"* — and
told the next person to **raise the budget or give the map states their own worker
count.** I measured before touching it.

**Across a full 181-state sweep at four workers, the slowest `ready` in the entire suite
is 80 ms.** The two suspect map states sit at **29–39 ms**. The budget has roughly **190×
headroom.** Nothing about it is marginal.

That inverts the diagnosis. **A wait that is normally 39 ms does not become 15 000 ms
under load — it becomes 80 ms.** The two states that "timed out" in 108's run did not
need more time; their selector **never attached**. Raising the budget would have changed
nothing except how long the same real failure took to report, and would have buried it
under a bigger number.

**Where 108's 21 s came from:** it is the whole test's duration, not the `ready` wait —
`goto` + `networkidle` + five checks against a WebGL surface. §5 read a total as if it
were the wait, and the two numbers have nothing to do with each other. Under a heavier
run this session, per-test time for those states doubled from 7.4 s to 14.6 s and
**`ready` still never came close** — which is exactly the signature of the two being
independent.

**So the number is unchanged and the reasoning was replaced.** On timeout the harness
now distinguishes the causes it can actually prove from the DOM:

- **`#app` never mounted** → the dev server or a boot error. Never load.
- **`#app` mounted and the named surface did not open** → a defect.

The open-step census is reported as **evidence, never as a verdict.** A third branch
naming "the surface changed under the harness" was written and then removed: a missing
step target proves nothing on its own, because `click()` would already have thrown its
own error had the target been absent when it mattered, and a chip legitimately replaced
by the sheet it opens is absent at diagnosis time for an innocent reason. Asserting a
cause the DOM cannot support is the same move that cost two sessions here.

**Both branches proved RED against the real harness**, not against a mock of it: an
unsatisfiable `ready` on `sheet-map-report` reports the app mounted with 149 elements
and `.report-chip=1` present; aborting `/src/main.js` reports `#app` never mounted with
2 elements. The full sweep is 181/181 after restoring.

**No §23 entry.** This is a harness decision, not a design one — no colour, type size,
spacing, component pattern, navigation or notification class was touched.

## 5. Method notes

- **The flake did not reproduce, twice.** 181/181 in 2.3 min, and again in 3.4 min under
  load. That is not proof the intermittent failure is gone — it is intermittent by
  definition — but combined with the 80 ms ceiling it is enough to say the *mechanism*
  §5 proposed is not the mechanism.
- **The instrumentation was thrown away.** Ready waits were measured with a temporary
  `console.log` over a real sweep, read, and removed. The number lives in the comment
  where the next person will read it, not in the harness where it would cost 181 lines
  of noise per run.
- **`make test` piped through `tail` reports `tail`'s exit code, not `make`'s.** My first
  green was worthless; pytest was re-run on its own to confirm 1235. Worth remembering
  before trusting a piped suite.

## 6. Exact next task

**1. Put a push on a real handset** — unchanged from 108 §7.2 and 107 §7.1, and now the
top item. Still the only link in the notification stack no test here can exercise, and
**it needs the owner's hands.** Android Chrome on https://haulmeter.online, sign in,
More → notifications, turn on **both** "Turn on alerts" and "Ask me about lots", park
inside a truck-stop geofence for 15 minutes. **Confirm the tray actions appear and that
tapping one posts the report WITHOUT opening the app.**

**2. If the layout sweep fails again, READ THE MESSAGE.** It now names the cause. If it
says "the named surface did not open", that is a defect to chase, not a re-run to
schedule.

**3. An honest "what is waiting" surface** (108 §8) — a driver who was not interrupted
has no reason to open the inbox. §13.3 forbids promising delivery; it does not forbid
saying how many held notifications are unread. Shape is a §22.2 question.

**4. A test that asserts the SHAPE of a suppression label** (108 §8). Every test compares
against the i18n key, which is how "Held until morning" was wrong for four of five
reasons across two sessions with a green suite throughout.

**5. Watch whether prompted beliefs disagree with volunteered ones** (§23 entry 112).
Check before the 1/day cap is ever raised.

**6. Give "claim paid" a second actor**, or accept it stays dormant (102 §4).

**7. Coverage.** 9 states (WI IN IA MN KS KY MI OH TX). Unchanged.

## 7. Debt

**Closed from 108:** the box is current and the false copy is gone · the map states'
`ready` budget is resolved — **as a measurement, not a change.**

**New this session (109):** none. The harness gained a diagnostic; nothing was deferred.

**Carried from 108:**
- **An honest "what is waiting" surface does not exist** (§6.3 above).
- **No test asserts the SHAPE of a suppression label** (§6.4 above).

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

## 8. Restarting

```
make up                              # local stack
make test                            # pytest 1235 + vitest 594 — do NOT pipe through tail (§5)
make ui-layout                        # 181 states, ~2.5 min
make lint                            # ruff + import-linter 30/30
```

**The standing warning, sixth form.** 104: a suite answers "does this do what it was
written to do", never "is this reachable". 105: the agreement between two components can
be owned by neither. 106: the tests kept entering where a driver cannot. 107: the code was
right and the **default** was wrong. 108: the code was right and the **prose** was wrong.
This one: **the prose about the prose was wrong.** 108 ended on "read the sentences in
this repo as claims, and check them like claims" — and its own §5 was a quantitative
claim that nobody had measured, in the same document. A number in a handoff is a claim
too, and this one was off by two orders of magnitude and pointed the next session at a
change that would have hidden a real bug. **Measure before you tune, especially when the
last session already told you what the answer is.**
