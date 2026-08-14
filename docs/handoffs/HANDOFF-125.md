# HANDOFF-125 — the queue learned to say what is in it

> **Stack DOWN (owner ended the session) · everything PUSHED · production CURRENT at `0076`.**
> Session 124 ran to nine owner instructions and **§23 entries 144–151**. This handoff
> supersedes `HANDOFF-124.md`, which stays readable for the email/attachment detail.
>
> **ONE THING IS NOT DEPLOYED: §23 entry 151** (the facility page's queued question and
> review). 149 and 150 are live and verified. See §1.
>
> ---
>
> **THE PATTERN TO CARRY FORWARD — and it is the fourth face of the same coin.**
> 122's was *built, correct, reached by nothing*. 123's was *specified, shipped as done,
> never built*. 124's was *correct in one process, wrong in another*. **125's is the
> quietest of the four: A THING THAT RENDERS IN EVERY CASE EXCEPT THE ONE IT EXISTS FOR.**
>
> | The thing | Renders correctly | Absent exactly where it is needed |
> |---|---|---|
> | the wallet's queued capture | online, wallet loaded | **offline, where the wallet fetch failed** |
> | the facility's queued question | online, Q&A loaded | **offline, where the Q&A fetch failed** |
> | `docs-queued` in the layout harness | never — it drained before the first assertion | — |
> | `facility-queued` in the layout harness | never — same reason | — |
>
> **I built the first one wrong.** The queued row went inside the surface's four-state
> load chain, which is the obvious place, and that chain is in its FAILED branch precisely
> when the driver is offline — precisely when the queued item exists and precisely when it
> is the only thing on the screen not in doubt. It would have shipped rendering perfectly
> in every state a developer looks at. **The layout harness caught it**, because the
> harness could not render the state either. The capture chip at the foot of `DocsSurface`
> has been outside that chain for exactly this reason since it was built, with a comment
> saying so, and the reasoning had simply never been carried up the file.
>
> **AND THE HARNESS ITSELF MEASURED NOTHING, TWICE.** Seeding the write queue and pointing
> a state at it is not enough: the harness's app is ONLINE, so `flushQueue` drained the
> queue against the mocks before the first assertion ran, and `docs-queued` cheerfully
> measured an empty wallet under that name. A hanging POST is what "no signal" actually
> is. **This is the same shape as the defect it was measuring** — a check that passes
> while asserting nothing about the thing it is named for.
>
> **The corollary that saved the wallet: the fix NOT made (entry 149).** The obvious move
> was to give the wallet the signed `/media` URLs that made the contact sheets fast. A
> signed URL carries a fresh `exp` and `sig` per render, so the browser's cache key changes
> every time, and the viewer's contract — *"a document opened at home opens again at the
> scale"* — holds only while the immutable year-long cache is hit by the SAME url twice.
> **On the screen that produces a CDL to a DOT officer, a changed cache key with no signal
> is the document not existing.** Two surfaces, two mechanisms, deliberately not unified.
> `test_document_thumb.py` opens with that argument so the next session meets it first.

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **0 ahead / 0 behind `origin/main`** at `1594754` (OBSERVED) |
| Gates | **pytest 1935 · vitest 918 (54 files) · layout 333 · `make ui-image` · `make ui-pwa` · import-linter 30/30 · ruff clean** |
| Migrations | local **and production** at **`0076_message_attachment`**. Nothing pending, none added this session |
| Working tree | clean |
| Stack | **DOWN** — `make down` at the owner's request |
| Deploy | **149 + 150 are LIVE and verified.** **151 IS NOT DEPLOYED.** Latest backup `haulmeter-20260814T022517Z.dump`, offsite |
| Email | production sends real mail; dev points at the same live Gmail |

**Session-124 baseline: pytest 1842 / vitest 885 / layout 325.**
Net across the whole session: **+93 pytest, +33 vitest, +8 layout, +1 make target.**

**The deploy verification that matters:** `queued__row` was confirmed present in the
SERVED bundle (`/assets/index-CatgDiRC.js`), not merely in the deploy script's exit code.
Twice this session a deploy reported success and changed nothing (§4.2), so reading the
artifact the browser actually receives is now the standard for "deployed".

### The audit queue

**All 8 Criticals closed. All 17 Highs, all 11 Mediums.** Two Lows remain (F-19, F-27),
each waiting on work scoped elsewhere. `OPEN-FINDINGS.md` is current.

---

## 2. What each entry closed

**144 — the driver's photograph left the main thread and localStorage.** Every upload path
read 3–8 MB to base64 on the main thread, then `JSON.stringify`, then a **synchronous**
`localStorage` write of the whole queue — and localStorage is ~5 MB per origin, so one
camera photo exceeded it alone. `setItem` threw, the `catch {}` swallowed it, and
`pendingWrites` counted a photograph written nowhere. Now downscaled 2048 px/q0.85 in a
Worker (**6.7 MB → 731 KB in 187 ms, measured**), held as an **ArrayBuffer** in IndexedDB.

**145 — the contact sheets stopped downloading photographs to draw thumbnails.**
"Thumbnail" was a variable name and never a file. A worker job derives 320 px JPEGs
(**78 of them, 0.35 MB against 14.34 MB of originals**).

**146 — email and push left the request thread.** **2,490 ms measured** of
connect/STARTTLS/AUTH before a byte moved, holding a pooled DB connection; **25.9 ms
after.** A sixth delivery state (`queued`), and §13.1's interruption budget re-based on a
new `decided_at`.

**147 — one email per purpose, enforced by Postgres.** Five ad-hoc guards across four
modules became one `dedupe_key` with a partial unique index.

**148 — the pack rides WITH the email, and the link had never reached the document.** The
edge proxied only `/api/*`, so **every pack link ever emailed to a broker returned HTTP 200
with the driver app's sign-in screen.** Found by the owner asking whether the link needed a
sign-in. Fixed with `handle /pack/*`; the PDF is now attached **beside** the link, never
instead of it, because the first open is written into the chain and an attachment cannot be
tracked or revoked.

**149 — the wallet shows the documents, and keeps the URL that made it trustworthy.**
Measured on production first: credentials are 1–12 KB, but load paperwork averages
261–853 KB and reaches **6.3 MB**. `?size=thumb` on the existing session-authenticated
route serves the derivative the job already makes — **1,836,147 → 3,988 bytes on
production, 460×** — and the viewer shows it at `0.55` opacity while the document loads.
The grid gained a thumbnail per row, fetched in parallel. `load_paperwork` deliberately
gets none: those rows are per-load summaries with no single document to show. **And the
signed-URL fix was deliberately not made** — see the header.

**150 — the capture that never left the phone is on the screen.** §15.1's glyph reached the
wallet. Built wrong first (inside the load-state chain), caught by the layout harness. The
queue is held as ITEMS now and `pendingWrites` is derived from them, because a count cannot
answer the question a screen has.

**151 — the question a driver TYPED is on the screen.** The same defect one surface over
and worse in one respect: a photograph still exists in the camera roll, while a question
and a review are text composed in this app and **nowhere else on earth**. Both `catch`
blocks said *"queued/offline in a later pass"*. Filtered by facility, which a path check
alone cannot do — `/community/questions` carries its facility in the BODY, so every
facility page would otherwise show a question about a lot 600 miles away.

---

## 3. Exact next task

**Deploy 151 first** if the owner wants the facility work live — it is the only committed
work that is not. `./scripts/deploy.sh`, then confirm `qa__item--pending` is in the served
bundle rather than trusting the exit code.

### Two things need the owner and neither is code

**1. 140 production records have no bytes.** 82 documents and 58 evidence artifacts, all
uploaded **26–28 July**, from the era `wiring.py`'s own comment describes — a swallowed
`SignatureDoesNotMatch` sent every upload to an in-process dict that evaporated on restart.
Everything from **4 August** onward is intact. They are marked `missing` and no longer
retried. **Leave them, purge the rows, or tell the affected drivers.** The metadata and
hash chains survive; only the images are gone, and the backups contain the same absence.
*Recommendation on record: tell the drivers. A wallet listing a permit it cannot produce is
the exact failure this product exists to prevent.*

**2. The handset background-sensor test.** v2.0 DoD #8, named as next since session 115 and
deferred **ten** times. It needs a human, a handset and a drive. Still the only way to
validate entry 138 — the arrival record's device fix, accuracy and distance have never been
produced by a real phone — and it unblocks the f03 knobs.

### Then, the work I would pick up

- **Finish §15.1's glyph: the map's lot/signal report, incident, and fuel price confirm.**
  `pendingByPath(path)` makes each one small. **But the shape is genuinely different** — a
  queued report changes a PIN'S STATE, not a row in a list, so it needs a decision about
  what "pending" looks like on a map before any code. Two of the three are one-tap
  contributions, so the case is weaker than the typed ones. This is the tail, not the head.
- **`--marker-500` at 2.04:1 in dark.** Fails contrast, open since session **119**, and it
  is the token the expiring-document pills use — so it is on the wallet, which is now the
  best-tested surface in the app. A §22.2 palette decision: **needs the owner's replacement
  value**, it cannot be improvised.
- **The wallet's full document.** A 6.3 MB BOL still downloads whole behind the thumbnail,
  on whatever LTE a truck stop has. The honest fix is a mid-size derivative (the job makes
  one edge today, 320 px) — but **measure first** whether a driver ever needs more than the
  thumbnail plus pinch-zoom at 360 dp. Building the derivative before that measurement is
  how this codebase has historically acquired unused machinery.

### Owner decisions still open

| | |
|---|---|
| **The 140 lost records** | the sharpest — see above |
| **`--marker-500` at 2.04:1 in dark** | a §22.2 palette colour, open since **119** |
| **Email verification at signup** | Owner-LOCKED. Gates three things (122 §4) |
| **External anchoring** | two options costed in the evidence report |
| **A second alert channel** | A12 has exactly one |
| **The f03 knobs** | `exit_confirm_pings` / `accuracy_gate_m`. The handset test is the prerequisite |
| **A far-future appointment overflows the Meter** | capping the figure changes §9 |
| **§7.2's anchored action on the other surfaces** | built on Load only |

---

## 4. Things a later session will trip over

1. **THE TWO IMAGE URL SCHEMES ARE NOT AN INCONSISTENCY TO TIDY UP.** Signed `/media` URLs
   go in an `<img src>` and are fast; the wallet's `/protection/documents/{id}` is
   session-authenticated, needs a fetch-to-blob, and is the RIGHT one there — a signed
   URL's `exp`/`sig` change per render, so the immutable cache is never hit twice and the
   offline guarantee dies silently. Anyone "unifying" these makes the wallet fast on a good
   connection and empty at a scale house. Argued at the top of `test_document_thumb.py`.
2. **A QUEUED-ITEM ROW MUST LIVE OUTSIDE ITS SURFACE'S LOAD-STATE CHAIN.** Inside it, the
   row renders in every case except the offline one it exists for. Two surfaces now do this
   correctly (`DocsSurface`, `FacilityProfileSurface`); any third must follow.
3. **A LAYOUT STATE THAT SEEDS THE WRITE QUEUE MUST ALSO HANG THE REPLAY.** The harness's
   app is online and `flushQueue` drains the queue before the first assertion, so the state
   measures an empty surface under a name that claims otherwise. `docs-queued` and
   `facility-queued` both hit this.
4. **`apiGet` SERVES ITS CACHE OFFLINE**, so "offline" is not "every read fails". A facility
   or wallet already opened still renders; the endpoints that do NOT cache
   (`fetchQuestions` calls `fetch` directly) are the ones that fail around it. A test that
   rejects every fetch is testing the COLD case, which is a different and rarer state.
5. **`ui-components.test.js`'s facility fixture is WRONG-SHAPED.** It nests the profile
   under `facility` while the surface reads `profile.name` and `profile.reviews` flat — so
   it renders an empty `<h1>` and no reviews list, and every assertion in that file passes
   because none of them read the name. Not fixed here (out of scope); `dwell.overall` is
   also required or the render throws. `facility-queued-contributions.test.js` has the
   correct shape.
6. **A SINGLE-FILE BIND MOUNT GOES STALE ON DEPLOY, and the deploy reports success.**
   `deploy.sh` unpacks a tar — a new inode — while a file bind mount stays pinned to the
   old one, and `caddy reload` re-reads the stale inode. `deploy.sh` force-recreates caddy
   now. **Anything else mounted as a FILE rather than a directory will hit this.**
7. **The edge is invisible to every test in the suite**, because they all talk to the
   router directly. `test_broker_link_is_reachable.py` asserts against `infra/Caddyfile`,
   mounted at `/repo/infra` beside the compose files for exactly that reason.
8. **`alembic_version.version_num` is `varchar(32)`.** A 38-character revision id applied
   its `DELETE` and then failed writing its own version row. Keep ids short.
9. **Rebuilding an enum needs the column DEFAULT dropped first.**
10. **A migration-only constraint is invisible to the suite** — the test DB is built by
    `Base.metadata.create_all`. Declare indexes on the MODEL too. *(Checked across the whole
    schema: 130 unique indexes identical in both. This was the only deviation.)*
11. **The worker wires object storage itself** (`app/wiring.py`, at the app root — `core`
    may not import `foundation`, and import-linter caught the first attempt).
12. **`gateway` is still a parameter of `send_counterparty_message` and is ignored.** The
    transport lives in the sweep. `_ = gateway` says so out loud.
13. **Two sweeps, both 60 s, both unflagged:** `outbound_mail` and `push_delivery`. The
    interval is FIRST-DELIVERY latency, not retry cadence.
14. **`make ui-image` needs the DEV server**; `make ui-pwa` needs the built app.
15. **`crypto.subtle` is undefined in the browser harness** — plain http, not a secure
    context. Compare bytes, do not hash.
16. **A Worker reply is structured-cloned.** Assert on bytes, never on identity.
17. **Vue's deep reactivity hands back PROXIES**, so `s !== shot` is true for every element.
    Use an id.
18. **`infra/.env` on the VM is `0600 root:root`** and holds the SMTP block. Read it with
    `sudo`; `deploy.sh` excludes it, so a deploy cannot overwrite it.
19. **The API wedges mid-reload if SSE streams are open.** (Carried from 122 §5.10.)

---

## 5. Known gaps this session left

- **Entry 151 is not deployed.** Everything else is.
- **§15.1's glyph is on three surfaces of six.** `ConditionSurface`, `DocsSurface`,
  `FacilityProfileSurface`. The map's lot/signal report, incident and fuel price confirm
  still show nothing but the global strip count.
- **The COLD offline case on a facility is deliberately uncovered** — offline on a facility
  never opened, `apiGet` has no cache, and there is no facility on the screen to attach a
  queued contribution to. Written into the test file rather than left to be found.
- **Production thumbnail state:** `ready` 48 artifacts / 15 documents · `none` (not an
  image) 4 / 18 · `missing` 58 / 82 · `(pending)` 31 artifacts with no `storage_key`.
- **`MEDIA_SIGNING_SECRET` is set on the VM** but the code still supports it being unset
  (per-process key). Safe at one uvicorn worker; breaks intermittently the day anyone adds
  `--workers`.
- **Push delivery has never run against a real subscription.** Production has VAPID
  configured and **zero** subscriptions.
- **The PDF attachment has not been confirmed in a real inbox.** Production sent one to an
  owner-controlled address; whether Gmail delivered it intact needs a human looking.
- **`SESSION-REPORT*.md` still live at the repo root** (six, from 122).

---

## 6. Restarting

```
make up                              # preflight, then the full stack
make seed-where                      # the Tampa origin — paste into Sensors
make test                            # 1935 pytest + 918 vitest — do NOT pipe it
make lint                            # ruff + import-linter (30 contracts)
make ui-layout                       # 333 checks, ~6 min, runs ALONE
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
