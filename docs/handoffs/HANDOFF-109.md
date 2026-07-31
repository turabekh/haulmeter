# HANDOFF-109 — the session that measured the flake instead of believing it

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 31 July 2026 · **Stack:** **DOWN** (`make up` to start) · **Deployed:**
https://haulmeter.online (GCE, `uzimiz-prod`) — **CURRENT and correct.** 108's three
commits are pushed and live, so the box has stopped telling drivers "Held until morning"
about notifications that never arrive.

**State in one line:** the false copy is off production, and the layout harness's
"known flake" turned out to be a real failure that the proposed fix would have buried.

> This continues HANDOFF-108. It closes its §7.1, §7.3 and the label-shape half of its
> §8, and it **corrects 108 §5**, which was wrong on the numbers.

**Nothing is half-finished.** The working tree is clean, every test is green, and the
two unpushed commits are complete units — see §1 and §7.1 for the one decision waiting
on the owner.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0055_f08_push_subscription** (no new migration this session) |
| Tests | **pytest 1235 · vitest 596 · ruff + import-linter 30/30** — all green |
| Layout | **181 states, 181 passed** — run three times, once under heavy load. No flake observed. |
| §23 decision log | **116 entries** (none added — see §4 for why) |
| Handoffs | 000 → 109 |
| Git | **two commits ahead** of `origin/main`: `d111a4b` (label test) and `d9235f3` (this doc). **Both are local-only and test/docs — nothing production-facing is unpushed.** |
| Deployed | **CURRENT.** `af2dda1` and everything before it is on the box. |
| Working tree | clean except untracked `collect_files.py` (still not mine, still untouched) |
| Local stack | **DOWN**, brought down deliberately at end of session |

**The two unpushed commits need no deploy** even when pushed: one is the Playwright
harness, one is this document. Neither is in the built app. `git push` alone is enough.

## 2. What shipped

| Commit | What | Pushed? |
|---|---|---|
| `71e1855`…`5f987a9` | 108's three commits — **pushed AND deployed**, nothing new in them | ✅ deployed |
| `af2dda1` | A `ready` timeout is a defect, not weather — and it now says which | ✅ pushed |
| `e6c0d5d` | This handoff, first form | ✅ pushed |
| `d111a4b` | The SHAPE of a held label is asserted, not its i18n key (108 §8) | ❌ local |
| `d9235f3` | This handoff, extended with §5 | ❌ local |
| _(this commit)_ | This handoff, final form | ❌ local |

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

## 5. The label test (108 §8, closed) — and the FOURTH copy of the retired claim

108 §8 asked for a test that renders each `suppressed_reason` and asserts the label does
not claim a time. It exists now, and writing it turned up the thing that justifies it.

**`ui/test/notifications.test.js` still asserted "Quiet hours defer, they do not
destroy"** in its own header. 108 corrected that claim in three files —
`api/app/api/notifications.py`, `f08.inbox`, §23 entry 102 — and **missed the fourth,
which was sitting in the test file for the very feature.** A claim that rots in three
places rots in four; the only reason this one was found is that someone opened the file
to write a test about it.

**Then the obvious thing was done: `defer` was grepped across `api/app`, `ui/src`,
`ui/test` and both governing docs. There is no fifth.** The two remaining mentions in
`f08` are correct — both put "deferring" in scare quotes to negate it — and everything
else is the unrelated Stripe/voice seams. Cheap, and it converts "I fixed the one I
tripped over" into an answer.

**Why the old tests could not have caught the label.** Every assertion here compares the
render against `en["notifications.held"]` — the same table the component renders from.
That proves the plumbing works and nothing else: it is true whatever the string says,
which is why "Held until morning" was green for two sessions while being wrong for four
of the five reasons. **A test that reads its expectation from the code under test is not
a test of the content.**

What is asserted instead is §13.3's operative clause — *no surface may promise that a
held notification will arrive later* — in all six locales, plus that all five reasons
render **one identical label**, which is what makes a single-string check sufficient.

**Matching is per-term by mode, and that is not fussiness — one mode is wrong in two of
these languages:**
- **exact** — `до` is a Russian preposition; as a prefix it also fires on `документ`,
  failing a *correct* label. A check that cries wolf is a check people delete.
- **prefix (`утр*`)** — inflection: catches `утра` and `утром` without listing either.
- **suffix (`*gacha`)** — **Uzbek is agglutinative and glues the postposition on**, so
  "until morning" is the single token `ertalabgacha`, which a prefix match sails past.

**All three modes proved independently, because an unexercised term in a forbidden list
asserts nothing** — the same defect as prose, one layer down. Exact on a bare `до`;
prefix on `Придержано до утра`; suffix on `tongacha` (chosen because it matches no
listed prefix, so only the suffix rule can catch it); and the false-positive guard
proved by a legitimate `документ` **passing**. English `Held until morning` and a clock
time `Held · sends 06:00` both caught. Locale files restored and verified byte-clean
afterwards.

## 6. Method notes

- **The flake did not reproduce, twice.** 181/181 in 2.3 min, and again in 3.4 min under
  load. That is not proof the intermittent failure is gone — it is intermittent by
  definition — but combined with the 80 ms ceiling it is enough to say the *mechanism*
  §4 proposed is not the mechanism.
- **The instrumentation was thrown away.** Ready waits were measured with a temporary
  `console.log` over a real sweep, read, and removed. The number lives in the comment
  where the next person will read it, not in the harness where it would cost 181 lines
  of noise per run.
- **`make test` piped through `tail` reports `tail`'s exit code, not `make`'s.** My first
  green was worthless; pytest was re-run on its own to confirm 1235. Worth remembering
  before trusting a piped suite.

## 7. Exact next task

**0. `git push`** — two local commits, `d111a4b` and `d9235f3` plus this one. **No deploy
needed**: the harness and this document are not in the built app. This is the only loose
end of the session and it is deliberate, not forgotten — rule 3 makes the push the
owner's call each time.

**1. Put a push on a real handset — THIS NEEDS THE OWNER'S HANDS, and no amount of
further work here substitutes for it.** Unchanged from 108 §7.2 and 107 §7.1, and now
the top item three sessions running. It is the only link in the notification stack that
nothing in this repo can exercise: every layer beneath it is tested and green, and the
whole feature is still unproven end to end.

> Android Chrome on https://haulmeter.online → sign in → More → notifications →
> turn on **BOTH** "Turn on alerts" and "Ask me about lots" → park inside a truck-stop
> geofence for 15 minutes. **Confirm the tray actions appear, and that tapping one posts
> the report WITHOUT opening the app.**
>
> If it fails, the likely suspects in order: the class opt-in (§23 114 — the switch that
> did not exist), the IndexedDB token mirror (§23 113 — `sw.js` reads what `api.js`
> writes), and `sw.js`'s hardcoded `/api/map/report` (correct in prod, wrong in dev).
> iOS is untested and needs an INSTALLED PWA for push at all.

**2. If the layout sweep fails, READ THE MESSAGE — do not re-run it.** As of `af2dda1`
it names its own cause. "the named surface did not open" is a defect to chase; "#app
NEVER MOUNTED" is the dev server. **Neither is load, and the budget does not need
raising** — §4 is the measurement that settles it.

**3. An honest "what is waiting" surface** (108 §8) — a driver who was not interrupted
has no reason to open the inbox, so a held notification can sit unseen indefinitely.
§13.3 forbids promising delivery; it does not forbid saying how many held notifications
are **unread**, which is a fact rather than a promise. **Shape is a §22.2 question and
therefore an OWNER DECISION — do not improvise it.** §10.5 keeps it away from a badge,
which rules out the obvious answer and is most of why this is still open.

**4. Watch whether prompted beliefs disagree with volunteered ones** (§23 entry 112).
Check before the 1/day cap is ever raised.

**5. Give "claim paid" a second actor**, or accept it stays dormant (102 §4).

**6. Coverage.** 9 states (WI IN IA MN KS KY MI OH TX). Unchanged.

## 8. Debt

**Closed from 108:** the box is current and the false copy is gone · the map states'
`ready` budget is resolved — **as a measurement, not a change** · the suppression-label
shape test exists (§5), and took a fourth stale "defer" claim with it.

**New this session (109):**
- **The label test guards ONE string.** §13.3 says *no surface* may promise later
  delivery; `TIME_PROMISE_TERMS` checks `notifications.held` and nothing else. The
  quiet-hours caption, the class-switch copy and every server-side notification body are
  unguarded, and the server's copy is English-only anyway (carried from 101). Widening it
  means deciding which keys are in scope, which is a real question rather than a loop.
- **The forbidden vocabulary is hand-maintained, per locale.** A seventh locale ships
  with no terms and would pass vacuously — the same shape as the harness state that goes
  green having measured nothing. There is no mechanism tying the term table to the locale
  list; `locale-completeness.test.js` is where that link would belong.

**Carried from 108:**
- **An honest "what is waiting" surface does not exist** (§7.3 above). The only
  carried item from 108 still open.

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

**The stack was brought DOWN at the end of this session.** Nothing is mid-migration and
no container holds state that `make up` will not rebuild — Postgres is a named volume
and survives.

```
make up                              # local stack — it is DOWN. Runs the port preflight first.
make test                            # pytest 1235 + vitest 596
make lint                            # ruff + import-linter 30/30
make ui-layout                       # 181 states, ~2.5 min
git push                             # two local commits; NO deploy needed (§7.0)
```

**Three things that will save the next session time, all learned the hard way here:**

- **Never pipe `make test` through `tail`/`grep`.** The pipeline reports the LAST
  command's exit code, so a failing suite exits 0 and reads as green. Redirect to a file
  and check `$?` instead. My first green this session was worthless.
- **Other projects run on this machine** (`sift`, `atlas` containers were up throughout).
  `make down` only touches LONGHAUL's compose project; leave the others alone. The port
  preflight in `make up` is what protects against the collision.
- **`make ui-layout-only STATE=<name>` (~45 s)** is the right loop while building. The
  full sweep is for shared tokens, global stylesheets, `layout.spec.js` itself, and
  handoffs. Note `STATE` is a `-g` pattern: `STATE="sheet-map-report — "` matches the
  layout-rules test only, `STATE="sheet-map"` matches all six map sheets.

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

**And the corollary, from §5.** 108 retired the "quiet hours defer" claim in three files
and a fourth copy survived — in the test file for that exact feature, found only because
someone opened it for an unrelated reason. **A claim does not live in one place.** When
you retire one, grep for it; the copy you miss is the one that will be read next.
