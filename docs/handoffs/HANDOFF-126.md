# HANDOFF-126 — the stand-in that agreed with the other stand-in

> **Stack UP · everything PUSHED · production CURRENT at `0077`.**
> Three owner instructions, **§23 entries 152–154**, three commits, one migration.
> This handoff supersedes `HANDOFF-125.md`, which stays readable for the wallet,
> queued-capture and image-pipeline detail.
>
> ---
>
> **THE PATTERN TO CARRY FORWARD — and it is the fifth face of the same coin.**
> 122's was *built, correct, reached by nothing*. 123's was *specified, shipped as done,
> never built*. 124's was *correct in one process, wrong in another*. 125's was *renders
> in every case except the one it exists for*. **126's is the one that explains why the
> other four survived so long: A SUBSTITUTE THAT ANSWERS FOR THE SYSTEM WILL AGREE WITH
> ANOTHER SUBSTITUTE BEFORE IT AGREES WITH THE SYSTEM.**
>
> | The check | What it talked to | What it therefore could not see |
> |---|---|---|
> | `ui-components.test.js` + the layout harness mock | a fixture carrying `name` | **the API has never sent `name`** — a blank `<h1>` on every facility page |
> | every facility test | `askQuestion()`, the function *under* the button | **the button was permanently disabled** — nobody has ever asked a question |
> | `test/pwa.test.js` | the manifest file on disk | the app was installable and **nothing ever asked to install it** |
> | *my own new* `ui-pwa` check | `Page.getInstallabilityErrors` | **it returns `[]` for everything headless** — including a bare page with no manifest |
>
> **I wrote the fourth row myself, this session, and it passed against a manifest sabotaged
> back to entry 143's `"icons": []`.** It reads like the strongest assertion available —
> Chromium's own verdict — and it asserts nothing. It was REMOVED rather than annotated,
> because a check that does not exist is worse than no check: it makes the next person
> stop looking. `pwa/offline.spec.js` now opens with that argument so the next session
> meets it before re-adding the call.
>
> **The fix, every time, was to move the assertion to the boundary the real thing crosses.**
> `test_facility_api.py` asserts `name` over HTTP, where the browser talks. The new UI tests
> mount and *click*, because a test that proves a button works has to press the button. The
> replacement PWA check *fetches every icon from the serving origin* and checks the PNG
> magic bytes — which is what catches 124's `try_files` defect, where the bad path answers
> **HTTP 200** and only the bytes disagree.
>
> ---
>
> **THE SECOND FINDING, and it cost a driver real money: A ZERO THAT MEANS "WE DID NOT
> MEASURE THIS" WAS RENDERED AS A MEASUREMENT.** `expected_detention_cost` returns
> `(0, 0)` with no dwell samples and `route_fuel_cost` returns `(0, None,
> "no_network_fuel")` with no station in range. Both rendered as a confident **−$0.00**
> and were folded into the headline — on the screen a driver uses to accept or refuse a
> load, inside the app whose entire thesis is that detention is what costs them. The
> template's `=== null` guard fired only on the OFFLINE path, the one place the UI writes
> the nulls itself, so the two states that actually occur against a working server were
> the two it did not cover. **A zero is indistinguishable from a dock that never detains
> anyone.**

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **0 ahead / 0 behind `origin/main`** at `55500d2` (OBSERVED, fetched) |
| Gates | **pytest 1942 · vitest 962 (57 files) · layout 349 · `make ui-image` · `make ui-pwa` · import-linter 30/30 · ruff clean** |
| Migrations | local **and production** at **`0077_settlement_period_uniq`** (one added this session) |
| Working tree | clean |
| Stack | **UP** |
| Deploy | **ALL THREE ENTRIES ARE LIVE.** Latest backup `haulmeter-20260815T034304Z.dump`, offsite |
| Email | production sends real mail; dev points at the same live Gmail |

**Session-125 baseline: pytest 1935 / vitest 918 / layout 333.**
Net: **+7 pytest, +44 vitest, +16 layout, +1 migration.**

**The deploy verification that matters:** the served bundle went
`index-Gir04Vz_.js` → `index-DC_aCBaz.js` and was read for `profile__bare`,
`result__excludes`, `receiver__opt`, `basis_recovery`, `prompt-mute__toggle` and the copy
in all six locales. Migration 0077's effect was measured on production **before and
after**: settlements 3 → 2, the one duplicate collapsed, `duplicate_groups_left: 0`,
`acted_on_discrepancies: 0 → 0`.

### A correction to 125

**HANDOFF-125 §1 says "151 IS NOT DEPLOYED." It was.** `qa__item--pending` — a string that
exists only in entry 151's commit `1594754` — was already in the served bundle before this
session's first deploy. 125 introduced the rule "read the SERVED bundle rather than trust
the exit code" and applied it to entry 150 but not to 151. Nothing was broken by it; the
board was wrong about one item, and it is the second time in three sessions that a deploy's
actual state differed from what was written down. `HANDOFF.md`'s 125 block carries the
correction inline.

### The audit queue

**All 8 Criticals closed. All 17 Highs, all 11 Mediums.** Two Lows remain (F-19, F-27).
Nothing found this session came from the audit — all three entries are PRD-versus-built
gaps and defects found by looking at running screens.

---

## 2. What each entry closed

**152 — the app asks to be installed, and iOS is told how.** Entry 143 made the app
installable and stopped one step short of anything that invites a driver to install it:
**`beforeinstallprompt` appeared ZERO times in the codebase.** That event is the browser
handing the app the right to raise the dialog and then waiting; with no handler the
browser keeps only a passive menu entry. Safari fires it never and exposes no install API,
so on iPhone the three Share steps ARE the path — and index.html has said since entry 111
that iOS needs an installed PWA for push *at all*. The strip row **yields** to offline,
queued, failed and update-waiting, which is what keeps LAW 0 satisfiable on a 360 dp row;
§6.5's 48 dp is **met rather than excused**, unlike `.strip__update` beside it, because
this one gets layout states. Dismissing silences the strip forever and keeps the More card
(§15.5).

**153 — the facility page a driver can use.** Four defects, all measured in a real browser
against the real API and the real 18,326-row table. **The `<h1>` was empty on every
facility page in this product's life** — the surface renders `profile.name`, the endpoint
never sent one, and `/public/facility/{id}` *did*, so an anonymous visitor was told which
place they were looking at while the signed-in driver was not. **Nobody had ever asked a
question** (`asking` was the sheet's open flag and the button's busy flag at once).
**A submitted review vanished** — 8 pending, 2 approved, both approvals the July seed —
so the owner chose publish-on-submit with moderation as take-down, and the "checked before
they appear" copy had to change with it. And **41 of 18,326 facilities have a profile**, so
for 99.8% of pins the screen was six cards each announcing that it had nothing; §15.3 is
applied to the surface now — one sentence, two actions. Fixing the name then exposed a
**39 × 48** back button: an empty heading pushes against nothing, so the missing title had
been hiding a §6.5 violation.

**154 — two figures a driver acts on were arithmetic about nothing.** **Re-running a
settlement audit multiplied the money owed** — `flagged_cents` 15000 → 30000 → 45000 over
three presses of Run, and pressing it again is the *normal* act because the figures are
typed by hand. Audit F-23 closed the neighbouring case and left this one. A settlement is
unique on (driver, carrier, period) now; re-auditing clears prior **flagged** findings and
deliberately keeps `submitted`/`resolved`, which record a person acting. **And the
true-profit calculator rendered −$0.00 for the thing it exists to count** — see the header.
The driver names the dock now, every cost renders from its **basis**, and entry 134's
`detention_recovery: "assumed_none"` reaches a screen for the first time since it was
written.

---

## 3. Exact next task

### Three things need the owner and none is code

**1. 140 production records have no bytes.** 82 documents and 58 evidence artifacts, all
uploaded **26–28 July**, from the swallowed `SignatureDoesNotMatch` era. Everything from
**4 August** onward is intact. Marked `missing`, no longer retried. **Leave them, purge the
rows, or tell the affected drivers.** The metadata and hash chains survive; only the images
are gone, and the backups contain the same absence. *Recommendation on record: tell the
drivers. A wallet listing a permit it cannot produce is the exact failure this product
exists to prevent.* Open since 124.

**2. `--marker-500` at 2.04:1 in dark.** Fails contrast, open since session **119**, and it
is the token the expiring-document pills use — so it is on the wallet. A §22.2 palette
decision: **needs the owner's replacement value**, it cannot be improvised.

**3. The handset background-sensor test.** v2.0 DoD #8, named as next since session 115 and
deferred **eleven** times. It needs a human, a handset and a drive. It is upstream of more
than it looks: `activeStopId` gates the whole condition flow and the calculator's prefill,
and entry 138's arrival record — device fix, accuracy, distance — has never been produced
by a real phone.

### Then, the work I would pick up

The owner asked what remains on `/load/calc`, `/money/audit` and `/protection/condition`;
two items were fixed (entry 154) and the rest is named here rather than left to be
rediscovered.

- **`/money/audit` — the period is hardcoded to the last 7 days.** `isoDaysAgo(7)` →
  `isoDaysAgo(0)`, no picker. **A settlement covering any other week cannot be audited at
  all**, and settlements arrive days after the period closes. This is the largest remaining
  hole in M9-FR1 and the cheapest to close.
- **`/money/audit` — `owed` and `paid` are returned and never rendered.** The driver sees
  "Detention $150" without "owed $400, paid $250", which is exactly what they would take to
  the carrier. §11.7's "a figure does not travel without what produced it".
- **`/money/audit` — `evidence_ref` is anchored on every discrepancy and never leaves the
  API.** M9-FR1 asks for "attached evidence packs formatted for carrier submission". The
  anchor is written; the response omits it; there is no export. Built-and-inert again.
- **`/money/audit` — no settlement upload, no F9 parse.** PRD says "settlement upload → AI
  parse (F9)"; it is four hand-typed numbers. `parse_settlement_lines` exists and is wired
  to nothing but its own test.
- **`/protection/condition` — the phase is recorded and ignored.** `start_condition_capture`
  takes and stores `phase`, `condition_sequence()` returns the same four steps regardless,
  and the UI always sends `"delivery"`. The module's own comment three functions away says
  *"A DELIVERY is not a PICKUP… Asking for the wrong artifact is how a checklist teaches
  people to ignore it."* **Reefer setpoint is asked of every load, including dry vans**, and
  there is no skip — the sequence only advances on a successful photo.
- **`/protection/condition` — two checklists, one the wrong shape.** `a01.capture_checklist`
  is F13 config and phase-aware; `CONDITION_SEQUENCE` is a hardcoded list whose own
  neighbouring comment says changing it "means a deploy".
- **`/load/calc` — MPG is hardcoded at 6.0.** The driver's truck is never asked and never
  stored, so every fuel figure is for a 6 mpg truck.

---

## 4. Things a later session will trip over

1. **`Page.getInstallabilityErrors` IS INERT IN HEADLESS CHROMIUM.** It returns `[]` for
   everything — the real app and `setContent("<html>bare</html>")` alike. Measured both
   directions. Do not re-add it to `ui-pwa`; the file argues the case at the top.
2. **A FIXTURE THAT SUPPLIES A FIELD THE API DOES NOT SEND IS INVISIBLE UNTIL SOMETHING
   ASSERTS AT THE HTTP BOUNDARY.** Two of them agreed with each other about
   `profile.name` for the life of the product. When a surface reads a field, assert the
   ENDPOINT returns it.
3. **A TEST THAT CALLS THE FUNCTION UNDER A CONTROL PROVES NOTHING ABOUT THE CONTROL.**
   Every facility test called `askQuestion()` while the button that calls it was disabled
   in every state it rendered in.
4. **A ZERO FROM THE SERVER MAY MEAN "NOT MEASURED".** `expected_detention_cost` →
   `(0, 0)`; `route_fuel_cost` → `(0, None, "no_network_fuel")`. Render from `basis`,
   never from the number.
5. **`Settlement`'s RELATIONSHIP COLLECTIONS ARE NOT TRUSTWORTHY.** `audit_settlement`
   writes with `db.add`, not through `settlement.discrepancies`, so the collection can be
   stale on a re-used object — it produced `[15000, 15000, 30000]`, right twice and wrong
   on the third. Delete by statement, then `db.expire`. Deleting through a `delete-orphan`
   collection AND `db.delete` issues a second DELETE for a row already gone.
6. **`/facility/search` IS A SEMANTIC SEARCH OVER REVIEW TEXT**, not a name lookup. The
   name search is `/public/facilities?q=`.
7. **THE API WEDGES MID-RELOAD IF A CONNECTION IS OPEN**, and it looks like a slow
   endpoint. Measured: `/intel/true-profit` timed out at 60 s wedged and returns in
   **0.24 s** after `docker compose restart api`. Restart before believing a latency number.
   (Carried from 122 §5.10 and hit twice this session.)
8. **AN AD-HOC PLAYWRIGHT PROBE MUST RUN `playwright install --with-deps chromium` FIRST**,
   the way the Makefile targets do. Without it the browser dies with
   `Target page, context or browser has been closed` and a wall of Chromium flags, and the
   real cause — `libglib-2.0.so.0` missing — is buried far below. Cost four wasted runs.
9. **A PROBE THAT HITS THE REAL API NEEDS `page.route` TO REWRITE `localhost:8008` →
   `api:8008`** (the browser is inside the compose network), the proxy must
   `route.abort()` on failure so one stalled background write cannot kill the page, and
   `waitUntil: "networkidle"` NEVER settles here — SSE keeps it busy. Use
   `domcontentloaded` plus an explicit wait.
10. **`infra/.env` on the VM is `0600 root:root`** — `sudo` the `grep` too, not just the
    `docker compose`. A bare grep fails with "Permission denied" and the psql invocation
    then eats the flags as a port number.
11. **A QUEUED-ITEM ROW MUST LIVE OUTSIDE ITS SURFACE'S LOAD-STATE CHAIN** (125 §4.2 —
    still true; `DocsSurface` and `FacilityProfileSurface` do this correctly).
12. **A LAYOUT STATE THAT SEEDS THE WRITE QUEUE MUST ALSO HANG THE REPLAY** (125 §4.3).
13. **THE TWO IMAGE URL SCHEMES ARE NOT AN INCONSISTENCY TO TIDY UP** (125 §4.1).
14. **A SINGLE-FILE BIND MOUNT GOES STALE ON DEPLOY** and the deploy reports success;
    `deploy.sh` force-recreates caddy for this reason (125 §4.6).
15. **A MIGRATION-ONLY CONSTRAINT IS INVISIBLE TO THE SUITE** — the test DB is
    `create_all`. Declare it on the MODEL too (125 §4.10). 0077 does both.
16. **`alembic_version.version_num` is `varchar(32)`.** Keep revision ids short.
17. **`make ui-image` needs the DEV server**; `make ui-pwa` needs the built app.
18. **A `.cta--ghost` SELECTOR IS NO LONGER UNIQUE ON THE FACILITY SURFACE.** Asking became
    a screen action, so `findAll(".cta--ghost").at(-1)` silently selected the wrong button.
    The mute toggle is `.prompt-mute__toggle` now. Name controls; do not index them.

---

## 5. Known gaps this session left

- **The facility fix is verified on DEV against the real API, and on production only to
  the level of "the code is in the served bundle."** Driving it live needs a real driver
  session and I did not create an account on production. The live probe returned §15.4's
  failed line for a rejected token, which is correct behaviour and not a check of the fix.
- **8 legacy `pending` reviews on production stay invisible forever** under the new
  publish-on-submit policy. They read `sdfgsdfg`, `asdf`, `good` — bench junk from the
  owner's own testing, not driver contributions — so they were deliberately left rather
  than retro-published onto real facility pages. Purging the rows is a one-line decision if
  the owner would rather.
- **`/protection/condition` is entirely untouched.** Everything in §3 about it stands.
- **The COLD offline case on a facility is deliberately uncovered** (125 §5).
- **Push delivery has never run against a real subscription.** Production has VAPID
  configured and **zero** subscriptions — and now, for the first time, an install prompt
  that could produce one. Worth checking after a real driver installs.
- **The PDF attachment has still not been confirmed in a real inbox.**
- **`SESSION-REPORT*.md` still live at the repo root** (six, from 122).

---

## 6. Restarting

```
make up                              # preflight, then the full stack
make seed-where                      # the Tampa origin — paste into Sensors
make test                            # 1942 pytest + 962 vitest — do NOT pipe it
make lint                            # ruff + import-linter (30 contracts)
make ui-layout                        # 349 checks, ~3.5 min, runs ALONE
make ui-image                        # 3 checks, real browser, needs the DEV server
make ui-pwa                          # builds, previews, drives a browser offline
make down
```

`make ui-layout-only STATE=<name>` measures one state in ~45 s — use it while building.

**Do not run pytest while `make test` is running** — same database, phantom failures.

`infra/.env` carries the live Gmail block and is gitignored. **A send from dev is a real
send — and so is a send from production.**

---

Each session ends by writing the next `HANDOFF-<n>.md` here and updating `HANDOFF.md` to
point at it.
