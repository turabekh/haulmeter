# HANDOFF-100 — the session the map got fast, and F8 got an audience

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 29 July 2026 · **Stack:** UP locally (`make down` to stop) · **Deployed:**
https://haulmeter.online (GCE, `uzimiz-prod`) — current with `66ef855`.

**State in one line:** the second half of a very long working session — the map's
performance, two features the owner asked for, and the discovery that F8 had been
deciding notifications nobody could read.

> **This continues HANDOFF-099, which is the same session.** 099 covers the E3.3 map
> work (§23 94–97, entry 99); this covers everything after. Read 099 first for the
> facility-merge story, the merged-id resolver and the Texas ingest — several
> corrections in it are load-bearing.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0053_f08_notification_read_at** |
| Tests | **pytest 1111 · vitest 547 · layout 169 · ruff + import-linter 30/30** |
| §23 decision log | **105 entries** (94–105 this session) |
| Handoffs | 000 → 100 |
| Git | **PUSHED** to `github.com/turabekh/haulmeter` (PUBLIC — see 099 §11) |
| Deployed | current with `6b681c2`; migration at head; zero errors; **all 13 module flags registered + enabled** |
| Working tree | clean except untracked `collect_files.py` (not mine) |

## 2. What shipped after 099

| Commit | What |
|---|---|
| `a8d28e6` | A merged `facility_id` resolves to the site it belongs to (§23 95) |
| `d68a111` | An unnamed host adopts the pump's name instead of losing it (§23 96) |
| `71f3a13` | Every kind that can host a pump reaches the Fuel preset (§23 97) |
| `67d2adb` | Texas ingested; two inherited claims falsified at source |
| `dfbfa58` | The map stops paying per pin for bulk data (§23 98) |
| `9bc99eb` | "Show me somewhere else" (§23 99) |
| `12275d4` | Coming back to the map no longer rebuilds it (§23 100) |
| `0194bc7` | Markers move on the compositor, not through Vue (§23 101) |
| `786f35d` | Notifications reach the driver at all (§23 102) |
| `874003b` | The driver can read what F8 decided (§23 102) |
| `8d974c6` | A live channel that cannot take the database down (§23 103) |
| `66ef855` | Crowd status goes live, without summoning a herd (§23 104) |
| `79e19cd` | docs: HANDOFF-100 |
| `8d4737a` | An admin-console test had an expiry date |
| `6b681c2` | Every module gets the kill switch PRD §6 already required (§23 105) |

## 3. The map, measured

**"Facilities not loading instantly" was three N+1s.** A coordinate read, a crowd-status
read and a fuel-badge read, each once PER FACILITY. Measured before touching anything:

| request | queries before | after |
|---|---|---|
| 7 pins | 31 | 16 |
| 263 pins | 273 | **11** |
| statewide pan (146 clusters) | **2,155** | **10** |

The worst case was work thrown away: over the pin cap the answer is CLUSTERS, yet the
code built all 609 pins in full and discarded them. Every batching primitive already
existed — F10's `beliefs_for_signal` says in its own comment that the map needs it
without an N+1, and the map never called it.

**But be honest about what a driver feels.** `/api/health` — a trivial endpoint — takes
**0.79 s** from a laptop and **0.025 s on the box**. With connection reuse a map fetch
is ~0.30 s, of which ~0.25 s is round-trip to `us-central1`. **Most of the latency is
distance, not the server**, and from Perth it is worse. The N+1 was real and made the
worst case 3× worse; it was not the whole of it.

## 4. Two features the owner asked for

**"Show me somewhere else" (§23 99).** A chip → sheet → geocode → the map moves. Both
never-improvise questions went to the owner (destination; one-shot vs persistent).
**It moves the VIEW and never `lastFix`** — that feeds the pings behind F3 arrival, the
geofence, the detention clock and `presence_proven`, so a driver in Perth who could
"pin" to Dallas would arm a stop there and run a clock on fiction. A test asserts
`lastFix` is untouched, because both implementations look identical on a screenshot.

**The notification inbox (§23 102).** See §5 — this one started as a different request.

## 5. F8 had been deciding notifications nobody could read

**The owner asked for SSE "for notifications" and was not sure where it fit. The
research answered a different question.** F8 has decided tiers, budgets, quiet hours
and classes since it shipped, and every decision ended in a row with no reader:

- **zero** notification endpoints in the OpenAPI schema
- no service worker, no manifest, no `PushManager` — the client cannot receive push
- the only gateway wired in application code is the **recording** one used by tests
- **no polling to replace** — the app's only two `setInterval`s are local clock ticks

§23 entry 429 caught the miniature ("nothing may be filed P2 until a surface renders
the digest"); the general case was larger.

**And SSE would not have fixed it.** A stream reaches only an app the driver is already
looking at. §13.1 calls background-permission survival "a platform-critical asset"
precisely because the model is about reaching someone who is NOT looking. **A P0
"detention started" to a phone in a pocket is push and can be nothing else.**

So the pull inbox was built first — no credentials, no provider, no background
permission. `read_at` is a new column because `status` records what the SYSTEM did; a
notification pushed at 03:00 and never opened is `sent` either way.

## 6. The live channel, and the connection it must not hold

SSE for **relay handoffs** and **crowd status** — the two places measured to earn it.

**The rule the design is shaped around: a stream holds a Redis subscription, never a
database session.** `Depends(get_db)` yields a session for the life of the REQUEST and
an SSE request lives for minutes, so wired the obvious way each connected driver pins a
pooled connection and the 31st (`pool_size=10, max_overflow=20`) takes the API down.
**§23 entry 93 already did that to this codebase from one phone's GPS stream.**

**Measured: 8 concurrent streams added +2 pooled connections, not +8**, and `/health`
still answered in 5.8 ms.

**The herd guard is the other half.** A fan-out cell is ~40 km, so one report wakes
every stream in it — and a naive client answers with one overlay request per driver in
the same instant, against the endpoint §23 98 had just made cheap. Arrivals coalesce
into one refetch, jittered across 0.8–3.0 s.

Failure is silent everywhere: publish swallows errors (it rides a committed write), the
stream answers a Redis outage with a polite `bye`, the client degrades with no
EventSource/session/network. **Every event is also a row REST returns**, so a dead
stream leaves a driver exactly one refetch behind — where they already were.

## 6b. Twelve modules had no kill switch (§23 105)

**PRD §6 is the governing rule — each module "built end-to-end behind its own feature
flag… for operational safety and controlled activation" — and it was true of ONE.**

| | before | after |
|---|---|---|
| Modules declaring `FLAG_KEY` | 13 | 13 |
| Flags registered in the database | **3** | **13** |
| Routers checking their flag | **1** (m13) | **13** |
| Calling `register_module` at startup | **nobody** | app lifespan |

M2–M10 and M12 were reachable with no gate. If M3's claim logic started producing wrong
money on the deployed box, the only remedy was a redeploy — and §23 entries 92 and 93
both happened without one. Verified live: `/money/earnings` **200 → 404 → 200** across
the flag, and `kill_switch` closes it independently.

**Two decisions worth knowing before touching this:**

- **The gate's predicate is `is_switched_off`, NOT `is_enabled`.** It fails OPEN on an
  unregistered flag and CLOSED on an explicit one. Registration runs at boot, so
  `is_enabled` semantics would turn a registry hiccup into twelve modules answering 404
  at once. The switch a driver-facing product needs is "turn M3 off NOW" — a row that
  exists and says off — and that still works.
- **A flag registered for the FIRST time comes up enabled; an existing one is never
  touched.** Owner decision: preserve today's behaviour. A flag somebody already set is
  an owner decision and a restart must not overrule it.

**`add_gate` was not idempotent** and now is — registration runs every start, so the
second boot hit `uq_validation_gate_flag_name` and rolled the whole registry back. An
existing gate is returned unchanged, because `satisfied` is an owner decision and a
legal sign-off must not be revoked by a deploy.

**I built this the wrong way first.** Registering flags in the test conftest polluted
global state and broke 84 tests, then 13. Reverting that and changing the GATE PREDICATE
instead took it to zero. **The failures were the signal that the design was wrong, not
that the tests were** — worth remembering before editing a test to accommodate a change.

## 6c. Nothing in this product has ever dispatched a P0

**Found while scoping push, and it changes what to build next.** `notify.dispatch` is
called from **five sites in two modules**:

- M5 protection — "Missing: BOL, photos" (you left without capturing), P1
- M5 protection — "CDL expires in 30 days", P1
- M13 vendor — vendor alerts, P1

Now compare against §13.2's own definition of the tiers:

| §13.2's named example | tier | dispatch sites |
|---|---|---|
| **detention started** | **P0** | **0** |
| booking failed | P0 | 0 |
| claim paid | P0 | 0 |
| free time 30-min warning | P1 | 0 |

**M3 does not call `dispatch` at all.** §12.6 quotes "Detention started · $75/h — Notice
ready to send" verbatim as the model notification, and nobody sends it.

**And the push blocker I reported was wrong.** Web Push with VAPID needs no Firebase or
Apple account — the keypair is self-generated, and Chrome/Edge/Firefox on Android
support it natively, which is exactly LAW 0's target device. iOS needs 16.4+ and an
installed PWA. So push is NOT blocked on the owner; it is simply the wrong thing to
build first, because it would carry two P1 classes reliably while the money event a
driver actually needs stays silent.

## 7. Method notes — read before trusting anything above

- **I took the local API down for several minutes.** `app.core.config` exports
  `get_settings`, not `settings`; the API crash-looped and `/health` returned `000`.
  Prod was never affected — the code had not shipped. **Check `/health` after touching
  an import in `core/`.**
- **I broke the `core → foundation` boundary** and import-linter caught it (2 contracts).
  `core/events.py` wanted F2's geohash. The cell is now computed one layer up and
  passed in; duplicating the encoder would have put two in the tree and eventually made
  publisher and subscriber disagree about the channel.
- **Two apparent flakes, one of which was not.** `login · pa` was a genuine harness
  flake (098 §5 records the same). `map · xx-XL` looked identical and was a REAL
  regression I had introduced — live markers sat at the container origin, half a puck
  off the left edge, between render and first paint. **Re-running the state in
  isolation is what distinguished them.** Do that before calling anything a flake.
- **A prod SSE test looked like a failure and was my stopwatch.** `gcloud ssh` takes
  ~6 s to connect, so the publish landed after the 10 s curl window.
- **One test I wrote was a tautology** (`expect(src).toBe("")`) asserting nothing.
  Replaced with a read of the shipped template.
- **522 green UI tests could say nothing about the marker change**, because a test
  runner has no WebGL: `live` is false and every mounted-canvas test exercises the
  FALLBACK path. The arithmetic moved to `core/` so it could be asserted at all.
- **A test had an expiry date, and it expired mid-session.**
  `test_overview_carries_the_overdue_count_separately` seeded a moderation report at a
  hard-coded `2026-07-26 08:00 UTC` and asserted the LIVE endpoint saw zero overdue.
  `MODERATION_SLA_HOURS` is 72, so it was true until **2026-07-29 08:00 UTC** and false
  after — it passed at 07:00 today and failed at 08:07. Confirmed pre-existing by
  stashing the working tree (1 failed / 1103 passed both ways). **A test that pins an
  instant and compares it to `datetime.now()` has an expiry nobody wrote down** —
  anchor to `now` instead.
- **Tests were proved RED before being trusted** for the resolver, the marker centring
  and the query budget — each by temporarily restoring the old behaviour.

## 8. Exact next task — wire the P0s, then push

**§6b is DONE — do not redo it.** The flag gap that §8 previously named is closed.

**1. Dispatch the notifications §13.2 already specifies.** See §6c: the tier/budget/
quiet-hours machinery is built and tested, the inbox now renders it, and **nothing has
ever dispatched a P0**. This is where the value is, and it is the smallest step to a
product that tells a driver the one thing they most need to know.

> **This needs an owner decision before any code.** Which moment IS "detention started"?
> Geofence ENTER, free-time expiry, or the first billable minute are three different
> instants and three different numbers on the driver's screen. **The recommendation is
> free-time expiry — the first instant money is owed** — but it is a product decision,
> so log a §23 proposal and ASK. §12.6 already fixes the copy: "Detention started ·
> $75/h — Notice ready to send."

**2. Then Web Push (VAPID).** Not blocked on credentials — see §6c. Needs: a VAPID
keypair in `infra/.env` (rule 9 — `.env.example` documents the names only), a service
worker + web manifest (the app becomes a PWA), a `push_subscription` table, a
`WebPushNotificationGateway` implementing the existing `gateway.py` Protocol, and a
permission-request flow whose TIMING is a §22 design question — asking on first launch
is the dark pattern §21.8 forbids in spirit.

**3. Coverage.** 9 states (WI IN IA MN KS KY MI OH TX). Anywhere else the map is
honestly empty of truck stops and a demo will look broken. `make osm-extract STATE=x`
then `make ingest-osm STATE=x`, then **BOTH repair passes** (see 099 §4d).

## 9. Debt

**New this session:**
- **Nothing dispatches a P0** (§6c). §13.2's own examples — detention started, booking
  failed, claim paid, free-time warning — have zero dispatch sites, and M3 never calls
  `dispatch` at all. This is bigger than the transport.
- **Push is unwired** — but NOT blocked on credentials (§6c). Web Push/VAPID is
  self-signed and covers LAW 0's target device.
- **`/events/stream` is NOT flag-gated.** It streams `handoff` (M10) and `status` (M1),
  so a module switched off can still have its events carried. Small, real, and left
  deliberately rather than bolted on at the end of a long session.
- **The SSE session travels in the QUERY string** — EventSource cannot set headers.
  Same TLS, same origin, same token, but query strings reach access logs. **A
  single-use stream ticket is the upgrade before real drivers.**
- **The SSE generator is synchronous**, so concurrent streams consume anyio threadpool
  workers (default 40). Beyond that they starve ordinary requests. An async Redis
  client is the fix when it matters; `MAX_STREAM_SECONDS` caps a forgotten tab.
- **`_enrich` is still per-pin** — 191 queries for 263 pins, bounded by the 300 cap,
  measured at ~0.055 s locally. Batching needs bulk reads in M6, M7 and M3.
- **Beliefs written against merged ids before §23 95** are still attached to shadows.
  The resolver fixes new writes; no repair pass walks the existing F10 rows.
- **The layout harness has at least one genuinely flaky state** (`login · pa`). A
  harness that cries wolf is one people stop believing.
- **`/admin/facilities/*` deliberately does not resolve merged ids** — correct, but an
  admin URL and a driver URL for the same id now answer about different facilities.

**Carried and still open:** M2-FR4 does not exist · per-stop detention terms not
expressible in the UI · the profit calculator opens on invented defaults · dwell-risk
thresholds unvalidated · `pin.shape` read by nothing · all live API keys on an
internet-facing VM · **no backups** beyond manual dumps · **no monitoring** · CLAUDE.md
rule 3 still says "NEVER push" while the repo is public and pushed (099 §11).

## 10. Restarting

```
make up                              # local stack
make test                            # pytest + vitest
make ui-layout                       # 169, ~2.5 min — run it alone
make repair-fuel / repair-scales     # DRY_RUN=0 to apply; BOTH after every ingest
./scripts/deploy.sh                  # push the working tree to haulmeter.online
```

**The standing warning, in the form this session kept finding it.** Every defect here
was invisible to a green suite: 2,155 queries behind a correct response; a merged id
answering 200 with the wrong place; a report accepted and discarded; markers trailing
the map; F8 deciding for months into rows with no reader. **The suite proves the code
does what it was written to do. It cannot tell you the code was written to do the wrong
thing, and it cannot see the thing nobody built at all.** Measure the real data, drive
the real screen, and re-run an isolated failure before calling it a flake.
