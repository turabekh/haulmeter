# HANDOFF-124 — the request thread gave back everything it was holding

> **Stack UP · everything PUSHED · DEPLOYED · `haulmeter.online` CURRENT at `0076`.**
> Fourteen commits, §23 entries **144–148**, six migrations applied on the box
> (`0071`→`0076`), a backup taken and verified offsite before each of the six deploys.
>
> **F-01 IS CLOSED. Every Critical in the 2026-08-07 audit is now closed.** Production
> email leaves the box for the first time in the product's life — verified by a rehearsal
> notice to an owner-controlled inbox carrying a real Gmail Message-ID.
>
> One session, six owner instructions: make images faster, move email to background jobs,
> deploy, stop duplicate emails, and send the broker the actual PDF. Each one ended somewhere
> further down than it started — and **the last one, a single question about whether the
> link needed a sign-in, found the sharpest defect of the session.**
>
> ---
>
> **THE ONE THING TO CARRY FORWARD.** 122's pattern was *built, correct, reached by
> nothing*. 123's was *specified, shipped as done, never built at all*. **124's is the
> third face of the same coin: a thing that is CORRECT IN ONE PROCESS AND WRONG IN
> ANOTHER — and every test that could see it was written in the process where it is right.**
>
> | The thing | Right where it is written | Wrong where it is used |
> |---|---|---|
> | `media_url`'s `/media/…` | the API router, which serves that path | an `<img src>`, which resolves against the PAGE |
> | **the pack link's `/pack/s/…`** | **the API router, which serves that path** | **a broker's browser, where only `/api/*` is proxied** |
> | `_wire_object_storage` | the API's FastAPI lifespan | the worker, a different process, which had no storage |
> | `dedupe_key`'s unique index | migration 0073, which production runs | the test DB, built by `create_all`, which never had it |
> | the budget's `dispatched_at` | a synchronous send, where it equals the decision | an asynchronous one, where it is NULL for a minute |
>
> **I shipped the first of those to production and it broke every contact sheet in the
> product.** Caddy's SPA `try_files` answered `haulmeter.online/media/…` with **HTTP 200 and
> `index.html`** — not a 404, a 200, which the browser tried to decode as an image. Nothing
> threw, nothing logged, no error state rendered. It failed identically in dev and the curl
> checks I "verified" it with hit `localhost:8008` directly, supplying by hand the one thing
> a browser never supplies. **A test that compares `src` to a STRING cannot catch this,
> because a string has no origin.** They resolve with `new URL(src, pageOrigin)` now.
>
> **THE SAME SHAPE TWICE MORE, and the second one is the one to read.** Every pack link
> ever emailed to a broker returned **HTTP 200 with `index.html`** — the driver app, whose
> router guard sends an unauthenticated visitor to sign-in. The API route is correctly
> session-free; the link simply never reached it, because the edge proxies only `/api/*`.
> It had never worked in production, and **F-01 hid it**: no counterparty mail left the box
> until the day before, so nobody had ever clicked one. Found by the owner asking a
> question, not by anything in the tree.
>
> **And then the fix deployed twice and did nothing.** The Caddyfile is a SINGLE-FILE bind
> mount; `deploy.sh` replaces files by unpacking a tar, which writes a new inode while the
> mount stays pinned to the old one. `up -d --build` does not recreate a service whose
> definition has not changed, and `caddy reload` re-read the same stale inode and logged
> *"using config from file"*. Host `grep` found the new route; container `grep` found
> **zero**. A deploy that reports success and changes nothing is the worst failure mode
> available, and it is now closed by a force-recreate in `deploy.sh`.
>
> **And the twin, in the tests: three of my four race tests proved nothing.** Sequential
> sends take the fast path; REPEATABLE READ is stricter than the app's own isolation;
> signalling after the loser's check lets thread scheduling decide. Only the fourth — which
> waits on `pg_stat_activity` until the loser is genuinely BLOCKED on the index — fails when
> the index is removed. **Measured, before that: the unique index could be dropped and all
> 24 dedupe tests still passed.**

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **0 ahead / 0 behind `origin/main`** at `3767e05` (OBSERVED) |
| Gates | **pytest 1929 · vitest 905 (52 files) · layout 325 · `make ui-image` · `make ui-pwa` · import-linter 30/30 · ruff clean** |
| Migrations | local **and production** at **`0076_message_attachment`**. Nothing pending |
| Working tree | clean |
| Stack | **UP** |
| Deploy | **DONE ×6 and verified.** Latest backup `haulmeter-20260813T180615Z.dump`, offsite |
| Email | **PRODUCTION SENDS REAL MAIL NOW.** dev still points at the same live Gmail |

**Baseline at session start: pytest 1842 / vitest 885 / layout 325.**
Net: **+87 pytest, +20 vitest, +1 make target (`ui-image`, in `make ci`).**

### The audit queue is nearly empty

**All 8 Criticals closed. All 17 Highs, all 11 Mediums.** Two Lows remain (F-19, F-27),
each waiting on work scoped elsewhere. `OPEN-FINDINGS.md` is updated.

---

## 2. What each entry closed

**144 — the driver's photograph left the main thread and localStorage.** Every upload path
read 3–8 MB to base64 on the main thread, then `JSON.stringify`, then a **synchronous**
`localStorage` write of the whole queue. localStorage is ~5 MB per origin, so one camera
photo exceeded it alone: `setItem` threw, the `catch {}` swallowed it, and `pendingWrites`
counted a photograph written nowhere. Now: downscaled 2048 px/q0.85 in a Worker
(**measured 6.7 MB → 731 KB in 187 ms**), held as an **ArrayBuffer** in IndexedDB — not a
Blob, because Safari detaches them and `fake-indexeddb` round-trips a Blob to `{type}`
with the bytes gone. Plus §15.1's per-item pending glyph, built for the first time.

**145 — the contact sheets stopped downloading photographs to draw thumbnails.** "Thumbnail"
was a variable name and never a file. A worker job derives 320 px JPEGs (**78 of them,
0.35 MB against 14.34 MB of originals**); the evidence route gained the `Cache-Control` it
never had. And the signed-URL regression above.

**146 — email and push both left the request thread.** **2,490 ms measured** of
connect/STARTTLS/AUTH before a byte moved, holding a pooled DB connection; **25.9 ms after.**
A sixth delivery state (`queued`) so a waiting notice does not read as failed, and §13.1's
interruption budget re-based on a new `decided_at` so deferring delivery does not silently
switch every daily cap off.

**147 — one email per purpose, enforced by Postgres.** Five ad-hoc guards across four
modules became one `dedupe_key` with a partial unique index. A re-send after a permanent
failure is not a duplicate, so M3's five-case rule hands the purpose over rather than the
key being weakened.

**148 — the pack rides WITH the email, and the link had never reached the document.** Two
things under one owner request. The link is fixed at the edge (`handle /pack/*`, prefix
preserved) and a broker now gets `HTTP 200, application/pdf` with no session — measured on
the live domain, where the day before the same URL returned the app's sign-in screen. And
the PDF is attached to every mail that already linked a pack, **beside** the link rather
than instead of it: §23 entry 432 chose the link partly because "the first open is written
into the chain … is evidence", and an attachment can be neither tracked nor revoked. The
message stores a KEY, not bytes — delivery is asynchronous, so the sweep produces the
document a minute later from the copy F4 already pinned, and a test asserts the attached
bytes are byte-identical to what the link serves. Verified against real SMTP:
`load-record.pdf`, `application/pdf`, **98,214 bytes**, link still in the body.

**And the send paths stopped lying.** `POST /protection/{kind}/{ref}/share` emailed
**nobody** — measured, `outbound_message` unchanged across a share — while two screens said
"Sent. The broker has the link." Four paths refused duplicates *invisibly*; they report
`already_sent` now, and `force` is the driver's deliberate override. A forced detention
notice sends a copy and **does not move the dispute anchor**.

---

## 3. Exact next task

**Two things need the owner and neither is code.**

**1. 140 production records have no bytes.** Everything uploaded **26–28 July** — 82
documents and 58 evidence artifacts, including rate cons, permits and condition photos.
The dates are exact and the cause is known: the era `main._wire_object_storage`'s own
comment describes, when a swallowed `SignatureDoesNotMatch` sent every upload to an
in-process dict that evaporated on restart. Everything from **4 August** onward is intact.
They are marked `missing` and are no longer retried. **The decision is yours: leave them,
purge the rows, or tell the affected drivers.** The metadata and hash chains survive; only
the images are gone, and the backups contain the same absence.

**2. The handset background-sensor test.** v2.0 DoD #8, named as next since session 115 and
deferred **nine** times now. It needs a human, a handset and a drive. It is still the only
way to validate entry 138 — the arrival record's device fix, accuracy and distance have
never been produced by a real phone — and it now also unblocks the f03 knobs, because real
device fixes finally enter the chain.

**Then, the work I would pick up first:**

- **The wallet read path.** `DocumentViewer` still does fetch → blob → objectURL at full
  size: no thumbnail, no lazy load, no browser cache. The contact sheets are fast; opening
  a CDL at a scale house is exactly as slow as it was. The whole apparatus (`media.py`,
  the derivative job, `mediaUrl`) already exists and is tested.
- **§15.1's pending glyph on the other queued writes.** It exists only on
  `ConditionSurface`; everywhere else a queued write still shows nothing but the global
  strip count.

### Owner decisions still open

| | |
|---|---|
| **The 140 lost records** | new, and the sharpest — see above |
| **`--marker-500` at 2.04:1 in dark** | a §22.2 palette colour, open since **119** |
| **Email verification at signup** | Owner-LOCKED. Gates three things (122 §4) |
| **External anchoring** | two options costed in the evidence report |
| **A second alert channel** | A12 has exactly one |
| **The f03 knobs** | `exit_confirm_pings` / `accuracy_gate_m`. The handset test is the prerequisite |
| **A far-future appointment overflows the Meter** | capping the figure changes §9 |
| **§7.2's anchored action on the other surfaces** | built on Load only |

---

## 4. Things a later session will trip over

1. **`alembic_version.version_num` is `varchar(32)`.** A 38-character revision id applied
   its `DELETE` and then failed writing its own version row. It rolled back, but that is a
   bad place for a migration to stop. Keep ids short.
2. **Rebuilding an enum needs the column DEFAULT dropped first.** `status` carries
   `'pending'::f08.notification_status`, and Postgres refuses to re-type a column whose
   default is expressed in the type being replaced. 0075's downgrade drops and restores it.
3. **A migration-only constraint is invisible to the suite** — the test DB is built by
   `Base.metadata.create_all`. Declare indexes on the MODEL too. *(Checked across the whole
   schema afterwards: 130 unique indexes and 1 check/exclude constraint, identical in both.
   This was the only deviation, not a systemic gap.)*
4. **The worker now wires object storage itself** (`app/wiring.py`, at the app root — `core`
   may not import `foundation`, and import-linter caught the first attempt). Before this,
   no worker job had ever reached for a stored byte, so nothing had failed.
5. **`gateway` is still a parameter of `send_counterparty_message` and is ignored.** Removing
   it is a five-module edit for no gain; `_ = gateway` says so out loud. The transport lives
   in the sweep.
6. **Two sweeps, both 60 s, both unflagged:** `outbound_mail` and `push_delivery`. The
   interval is now FIRST-DELIVERY latency, not retry cadence — it is how long a screen reads
   `queued`.
7. **`make ui-image` needs the DEV server** (it imports `src/core/*`), unlike `make ui-pwa`
   which needs the built app.
8. **`crypto.subtle` is undefined in the browser harness** — the dev server is plain http,
   so it is not a secure context. Compare bytes, do not hash.
9. **A Worker reply is structured-cloned**, so a passed-through blob is a different object
   with the same contents. Assert on bytes, never on identity.
10. **Vue's deep reactivity means `shots.value` hands back PROXIES.** `s !== shot` compares a
    proxy against its own target and is true for every element — a filter by identity
    silently removes nothing. Use an id.
11. **`infra/.env` on the VM is now `0600 root:root`** and holds the SMTP block. Read it with
    `sudo`; `deploy.sh` excludes it, so a deploy cannot overwrite it.
12. **A SINGLE-FILE BIND MOUNT GOES STALE ON DEPLOY, and the deploy reports success.**
    `deploy.sh` replaces files by unpacking a tar — a new inode — while a file bind mount
    stays pinned to the one it was created with. `up -d --build` will not recreate a service
    whose definition has not changed, and `caddy reload` re-reads the same stale inode and
    logs "using config from file". The Caddyfile hit this; anything else mounted as a FILE
    rather than a directory will too. `deploy.sh` force-recreates caddy now.
13. **The edge is invisible to every test in the suite**, because they all talk to the
    router directly, where a missing proxy route cannot be seen.
    `test_broker_link_is_reachable.py` asserts against `infra/Caddyfile`, which is mounted
    at `/repo/infra` beside the compose files for exactly that reason.
14. **The API wedges mid-reload if SSE streams are open.** (Carried from 122 §5.10.)

---

## 5. Known gaps this session left

- **Production thumbnail state:** `ready` 48 artifacts / 15 documents · `none` (not an
  image) 4 / 18 · `missing` 58 / 82 · `(pending)` 31 artifacts with no `storage_key` at all.
  The job converges and re-reads nothing.
- **`MEDIA_SIGNING_SECRET` is set on the VM** but the code still supports it being unset
  (per-process key). That is safe at one uvicorn worker and breaks intermittently the day
  anyone adds `--workers`.
- **Push delivery has never run against a real subscription.** Production has VAPID
  configured and **zero** subscriptions, so the whole path is exercised only by tests. That
  is also why moving it was cheap: no backlog, no behaviour change for anyone.
- **`SESSION-REPORT*.md` still live at the repo root** (six, from 122).
- **The attachment has not been seen in a real inbox yet.** Production sent one to an
  owner-controlled address; whether Gmail delivered the PDF intact or stripped it is the
  one step that needs a human looking at a mail client.

---

## 6. Restarting

```
make up                              # preflight, then the full stack
make seed-where                      # the Tampa origin — paste into Sensors
make test                            # 1929 pytest + 905 vitest — do NOT pipe it
make lint                            # ruff + import-linter (30 contracts)
make ui-layout                       # 325 checks, ~3.6 min, runs ALONE
make ui-image                        # 3 checks, real browser, needs the DEV server
make ui-pwa                          # builds, previews, drives a browser offline
make down
```

`make ui-layout-only STATE=<name>` measures one state in ~45 s — use it while building.

**Do not run pytest while `make test` is running** — same database, phantom failures.

`infra/.env` carries the live Gmail block and is gitignored. **A send from dev is a real
send — and now so is a send from production.**

---

Each session ends by writing the next `HANDOFF-<n>.md` here and updating `HANDOFF.md` to
point at it. Full history is in `docs/handoffs/`; the Session-0 bootstrap is `HANDOFF-000.md`.
