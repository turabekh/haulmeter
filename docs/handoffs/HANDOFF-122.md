# HANDOFF-122 — six hardening passes, and the wedge that still cannot deliver

> **Stack UP · 43 commits UNPUSHED · NOTHING DEPLOYED · three migrations pending on production.**
> `haulmeter.online` still serves **121 at `0066`**. Local head is **`0069_f01_attempt_kind`**.
>
> One session, six owner-supplied work contracts, run back to back. Each ended with its own
> report at the repo root — **read those for detail; this file is the map.**
>
> | Report | Subject |
> |---|---|
> | `SESSION-REPORT.md` | M3 detention hardening (11 findings) |
> | `SESSION-REPORT-wedge-delivery.md` | the broker's email, honest resends, M4 guards |
> | `SESSION-REPORT-location-integrity.md` | f03 geofence: armings, ordering, inert knobs |
> | `SESSION-REPORT-evidence-integrity.md` | f04 chain, anchors, packs that refuse to lie |
> | `SESSION-REPORT-auth-boundary.md` | f01 sessions, hashing bounds, registration throttle |
> | `SESSION-REPORT-credential-control.md` | the password a driver can actually change |
>
> ---
>
> **THE ONE THING TO CARRY FORWARD.** Across six passes the same defect recurred in six
> different subsystems: **a mechanism that was built, correct, exported — and reached by
> nothing.** The dunning cadence, `send_pre_detention_notice`, `needs_rehash`, `build_trace`,
> `complete_credential_change`, `must_change`. Every one had tests. Every one was green. None
> had a caller. The audit tally of "built-and-inert engines" is now **six**, and the pattern is
> no longer a coincidence — it is what this codebase produces when a capability is finished
> at the seam and never wired to a person.
>
> **And its twin, in the tests: six consecutive passes caught a revert-check that proved
> nothing.** The species is named now — *the test arranged the appearance of the condition
> rather than the condition*: a monkeypatched name over a shared object, a flood below the
> ceiling it meant to breach, a race planted inside one session, an identity map answering for
> Postgres, and finally a shell variable that made six reverts silently not happen. **Do not
> accept a green revert-check without asking whether it reached the real mechanism.**

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **43 commits ahead of `origin/main`** (`1254d48`, OBSERVED — `git fetch` works) |
| Gates | **pytest 1813 · vitest 796 (45 files) · layout 289 · import-linter 30/30 · ruff clean** — all measured on the final tree |
| Migrations | local head **`0069_f01_attempt_kind`**. **Production is at `0066`.** Three pending: `0067` (M3 claim/receivable uniqueness), `0068` (f03 presence uniqueness + evaluation cursor), `0069` (f01 attempt `kind`) |
| Working tree | clean |
| Stack | **UP**, all seven containers, `/health` 200 `environment=dev` |
| Dev data | Tampa origin intact · 4 DEV facilities · 80 claims · 21 active armings (was 22; one orphan reconciled) |
| Email | **dev still points at live Gmail. A send from dev is a real send.** |
| Deploy | **NOT RUN.** Nothing from this session has left the machine |

**Baseline at session start was pytest 1558 / vitest 746 / layout 283.** Net across the
session: **+255 pytest, +50 vitest, +6 layout.**

---

## 2. What each pass closed

**M3 detention** — 41 of 45 audit findings were already closed; this took the remaining
module-level ones. Duplicate claims and receivables made impossible in Postgres; `"sent"`
redefined to mean the message row carries `sent_at`; the invented `counterparty@unknown`
removed from four sites; dunning wired to a real scheduled job with three bounds; the broker's
pre-detention warning wired; `/detention/start` given the ownership check it never had.

**Wedge delivery** — the broker's email became recordable at load creation, on the load, and
inline where the claim screen complains; a resend rule that cannot double-notify; M4's first
403s, an amount floor at two layers, and once-per-target filing.

**Location integrity** — armings became mortal (get-or-create + a nightly reconcile); a
per-account evaluation cursor made ping evaluation serial and forward-only; two inert knobs
(`exit_confirm_pings`, `accuracy_gate_m`) shipped **off**; `build_trace` deleted with a tombstone.

**Evidence integrity** — `verify_chain` now cross-checks its anchors, so a consistent rewrite
fails; a pack that fails its own verification cannot be pinned, shared or emailed; link opens
left the hash chain; a Location basis section states what the GPS data is; counterparty copy
stopped saying "GPS-verified".

**Auth boundary** — a credential change ends every other session; a real logout route; hashing
bounded wherever it runs with a separate creation pool; registration throttled on its own
counter; a password floor that is never retroactive; hashes that upgrade themselves.

**Credential control** — `POST /auth/password`, the flag on `/me`, and the forced-change gate.

---

## 3. The three things that were worse than their findings said

**The detention wedge could not deliver to anybody, by construction.** Nothing in the product
had ever written `contact_email` — `POST /load` was the only route that created a broker and
never set one, and no screen collected it. So every counterparty row carried NULL and every
notice went to an invented address. Combined with F-01 (production SMTP pointed at Mailpit),
that is **two independent mechanisms** by which no broker has ever received anything. Both are
now addressable; see §4.

**A broken evidence pack was being sent to brokers.** `render.py` has printed *"HASH CHAIN
BROKEN — do not rely on this pack"* since it was written, and nothing stopped that PDF being
pinned, linked and emailed under the driver's name.

**An admin-issued temporary password silently became the permanent one.** `must_change` was set
by the reset, displayed in the *admin console*, and returned to no driver-facing surface —
while `complete_credential_change` had no route at all. The admin who issued it knew a working
credential indefinitely.

---

## 4. Exact next task

**The owner's two actions come first, and neither is code.**

1. **`SMTP_HOST` on the VM** (F-01, open since HANDOFF-121 §11.1). Production points at the
   Mailpit container, so every counterparty email lands on the box. One `.env` edit; rule 9
   makes it yours.
2. **Push and deploy.** 43 commits and three migrations. `0067` and `0068` both carry refusing
   pre-checks that name offending rows rather than dying mid-apply; dev had zero violations for
   both. Take the backup first, as 121 did.

**Then the first live send should be a rehearsal to an inbox you control** — create a load with
your own address as the broker email, run a stop past free time, tap Send, and confirm what
arrives. Two independent blockers are lifting at once and the first real send is the only test
that covers both.

**The oldest unmet item is still v2.0 DoD #8 — the handset background-sensor test.** Named as
the next task since session 115, deferred seven times. Everything in the A1 stop auto-pilot
rides on a sensor nobody has watched work on a real phone. It needs a human, a handset and a
drive; no test in this repo can substitute.

### Owner decisions still open

| | |
|---|---|
| **`--marker-500` at 2.04:1 in dark** | A §22.2 palette colour, open since 119. Entry 118's delegation does not reach it |
| **Email verification at signup** | Owner-LOCKED. It gates *three* things now: closing the registration enumeration oracle, self-service password recovery, and notifying a driver by email when their password changes |
| **External anchoring** | Two options costed in the evidence report: an OpenTimestamps-style calendar (independent forever, free, but an outbound dependency) vs a signed daily digest to an owner-controlled archive (instant, nothing to explain, but the attestation is still ours) |
| **A second alert channel** | A refused pack logs at ERROR and nothing else. A12 has exactly one channel |
| **The f03 knobs** | `exit_confirm_pings` (1) and `accuracy_gate_m` (0) are declared and OFF. Turning either moves money timing. **The dev accuracy data is synthetic — every ping reads exactly 150.0 — so it cannot inform a threshold.** Needs a week of real handset pings |
| **D5's non-dismissibility** | The forced password screen is inescapable by design. One condition in `installAuthGuard` if you want it skippable |

---

## 5. Things a later session will trip over

1. **Dev's `migrate` service now mounts the source** (N-04). Before that fix a newly written
   migration was invisible to it, and once the DB was stamped ahead of the image, api *and*
   worker refused to start. Production correctly mounts nothing.
2. **`evaluate_ping` returns `PingResult`, not a list.** It is iterable over `.events` so old
   callers work; five assertions across the suite compare `.events` explicitly.
3. **`share_pack` refuses an invalid chain.** Any new pack path inherits the gate and must
   translate `ChainInvalid`.
4. **`append_record` retries once on a seq collision** inside a savepoint.
5. **A new driver route must declare `meta.driving` AND back it** by consulting `isDriving`,
   and must be added to `driving-posture.test.js`'s `SOURCE` map. The guard caught this session.
6. **New i18n strings must survive the pseudo-locale's +40% inflation.** A message that is
   mostly an interpolation token will fail — the prose has to carry it.
7. **The password floor is 8 and is never retroactive.** It lives in `register_account`, so
   direct service callers are covered; seed passwords were measured before it was chosen.
8. **Three throttle kinds now share `f01.login_attempt`** — `login`, `register`,
   `password_change` — with separate F13 keys. The discriminator exists so one cannot lock out
   another; a test must breach the *real* ceiling to prove it.
9. **`revoke_sessions` expires in place, never deletes.** Assert the invariant ("no session
   resolves"), not a row count.
10. **The API wedges mid-reload if SSE streams are open** when a layout run has been driving it.
    Symptom: `/health` hangs. `docker compose restart api` clears it.

---

## 6. Known gaps this session left

- **Screenshots not taken** for the evidence session's three D8 states and the credential
  session's three password states. Both are covered by component tests and both are one
  addition to the existing `OBSERVE_SHOTS` spec. Recorded in their reports rather than glossed.
- **`SESSION-REPORT*.md` files live at the repo root** — six of them. They are the detailed
  record; if they belong in `docs/` instead, moving them is a rename.

---

## 7. Restarting

```
make up                              # preflight, then the full stack
make seed-where                      # the Tampa origin — paste into Sensors
make test                            # 1813 pytest + 796 vitest — do NOT pipe it
make lint                            # ruff + import-linter (30 contracts)
make ui-layout                       # 289 checks, ~3.5 min, runs ALONE
make down
```

`make ui-layout-only STATE=<name>` measures one state in ~45 s — use it while building a screen.

**Do not run pytest while `make test` is running** — same database, phantom failures. And do not
start a background full-suite run and then edit: **four of this session's six baseline runs were
contaminated that way** and reported failures that passed in isolation. Let the baseline finish
before touching the tree.

`infra/.env` carries the live Gmail block and is gitignored. **A send from dev is a real send.**

---

Each session ends by writing the next `HANDOFF-<n>.md` here and updating `HANDOFF.md` to point
at it. Full history is in `docs/handoffs/`; the Session-0 bootstrap is `HANDOFF-000.md`.
