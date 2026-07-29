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
| Tests | **pytest 1104 · vitest 547 · layout 169 · ruff + import-linter 30/30** |
| §23 decision log | **104 entries** (94–104 this session) |
| Handoffs | 000 → 100 |
| Git | **PUSHED** to `github.com/turabekh/haulmeter` (PUBLIC — see 099 §11) |
| Deployed | current; migration at head on the box; zero errors in the log |
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
- **Tests were proved RED before being trusted** for the resolver, the marker centring
  and the query budget — each by temporarily restoring the old behaviour.

## 8. Exact next task — the flag gap

**PRD §6 says every module is "built end-to-end behind its own feature flag… for
operational safety and controlled activation." Audited this session:**

| | |
|---|---|
| Modules declaring `FLAG_KEY` | **13 of 13** |
| Flags actually **registered in the database** | **3** (m01_map, m11_voice, m13_vendor) |
| Module routers that **check** their flag | **1** (m13_vendor) |
| Module services checking their own `FLAG_KEY` | **1** (m13_vendor) |
| Who calls `register_module` at startup | **nobody** (m11 does it lazily, inside a request) |

**M2–M10 and M12 are reachable with no gate at all, and there is no kill switch.** If
M3's claim logic produces wrong money on the deployed box — the failure class this
session kept finding — the only remedy is a redeploy. `is_enabled` returns **False** for
an unregistered flag, so adding gates without registering first would switch the
product off.

**The owner decision this forces: what the default should be.** Registering
`enabled=True` preserves today's behaviour exactly; `False` follows M13's precedent
(`default OFF`) and switches the product off until turned on. **Ask before writing.**

Then, in order: **2.** wire push (needs FCM/APNs credentials + a service worker — the
only thing that makes §13 reach a backgrounded driver). **3.** ingest more states —
coverage is 9 (WI IN IA MN KS KY MI OH TX) and anywhere else the map is honestly empty.

## 9. Debt

**New this session:**
- **Push is unwired.** F8 decides correctly and reaches nobody who is not looking.
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
