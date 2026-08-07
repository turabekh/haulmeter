# Backend audit — Haulmeter

**Date:** 2026-08-07 · **Reviewer:** Claude (session with Turaboy)
**Source:** `longhaul_latest.txt` split, 721 files · tree state = HANDOFF-118
**Scope:** backend only — `api/app/**`, `api/migrations/**`, `infra/**`. UI, tests-as-artefacts and
docs were read only where they bear on backend behaviour.

## How to read this

Every finding is marked with what kind of claim it is:

| Mark | Meaning |
|---|---|
| **OBSERVED** | Read directly in the dump. The code says this. |
| **INFERRED** | Follows from code + committed config, but depends on runtime state I cannot see (the VM's `infra/.env`, the live DB). Needs one command to settle. |
| **ABSENT** | A thing that is not there. The riskiest category — see the standing warning in PRD v2.0 §9. |

Nothing here has been verified against a running system. `deploy.sh`, `Makefile` and
`check_ports.sh` are **not in the dump** (F-11), so anything depending on them is inference.

---

## Summary

| # | Finding | Severity | Kind | Bears on |
|---|---|---|---|---|
| F-01 | Production counterparty email probably delivers to Mailpit on the VM | **Critical** | INFERRED | DoD #3, A1 |
| F-02 | Validation gates have never governed a flag; `register_all` force-enables | **Critical** | OBSERVED | A7, M3/M6/M7 |
| F-03 | Every SMTP send returns the same provider ref `smtp-1` | High | OBSERVED | A1 req 4 |
| F-04 | `_LazyCounterpartyGateway` has zero test coverage | High | ABSENT | F-03 |
| F-05 | Ledger `external_ref` has no unique constraint — `post_entry` not idempotent | High | OBSERVED | F7, M3/M6/M7 |
| F-06 | No retry or dead-letter on counterparty email | High | ABSENT | DoD #3 |
| F-07 | No rate limit or lockout on `/auth/login` | High | ABSENT | security, A12 |
| F-08 | Gmail as counterparty transport (owner decision — see ladder) | **Accepted** | OBSERVED | A1 validation |
| F-09 | `purge_pings_older_than` exists, is exported, and is never scheduled | Medium | OBSERVED | privacy, A12 |
| F-10 | Worker scheduler state is in-process; no lock, resets on restart | Medium | OBSERVED | A12 |
| F-11 | `deploy.sh` / `Makefile` / `check_ports.sh` outside every review | Medium | ABSENT | process |
| F-12 | Module gate and worker disagree on flag polarity | Medium | OBSERVED | interacts with F-02 |

**Clean:** admin authorization (§6.1), core double-entry invariants (§6.2), share-link access
control (§6.3), datetime handling (§6.4), map N+1 (§6.5).

---

## F-01 — Production counterparty email probably delivers to Mailpit · **Critical** · INFERRED

**What the code says.** `SmtpNotificationGateway.configured` returns `bool(smtp_host and smtp_port)`.
`config.py` defaults `smtp_host="mailpit"`, `smtp_port=1038`. The committed `infra/.env.example`
ships `SMTP_HOST=mailpit`. And `infra/docker-compose.deploy.yml` **runs a mailpit service on the
deployed stack.**

**Therefore**, unless the VM's `infra/.env` explicitly *blanks* `SMTP_HOST`, on the box:

1. `configured` → `True`
2. `_LazyCounterpartyGateway._pick()` → `SmtpNotificationGateway`, not the recording gateway
3. `mailpit` resolves on the compose network
4. The send **succeeds** into a Mailpit inbox nobody reads
5. `send_email` returns `smtp-1`; the F8 row records delivery; the driver sees "Sent"

**Why this matters more than it looks.** This is the defect class §23 entry 122 just fixed —
F8 rows asserting sends that never left the box — reproduced one layer up, and now with a
*successful* SMTP transaction backing the false claim.

**Contradicts the record.** HANDOFF-118 §5.2 states that without production `SMTP_*` the box
"falls back to the recording gateway." Reading the code, fallback requires `SMTP_HOST` to be
**blank**, not merely un-overridden. If the VM's `.env` came from `make env`, it says `mailpit`.

**Settle it with one command on the box:**

```bash
docker compose exec api python -c \
  "from app.core.config import get_settings as g; s=g(); print(repr(s.smtp_host), s.smtp_port)"
```

Then check whether the deployed mailpit has messages in it. If it does, every counterparty email
believed sent since 2026-08-02 needs re-examining before DoD #3 can be pursued.

---

## F-02 — Validation gates have never governed a flag · **Critical** · OBSERVED

`app/module_registry.py::register_all()`:

```python
for key in registered:
    if key in known_before:
        continue                      # existing state is the owner's — correct
    flag = db.get(flags.FeatureFlag, key)
    if flag is not None:
        flag.enabled = True           # <-- direct assignment
```

`enable()` is the only function in F13 that checks gates. It is **not** called here, nor in
`register_flag`. On first boot every module flag is switched on by assignment with its gates
unread.

**Three modules carry gates, and they are the money ones:**

| Module | Gates | Real-world meaning |
|---|---|---|
| M3 detention | `legal_signoff`, `collection_partner_agreement` | The wedge |
| M6 parking | `refund_policy`, `damage_liability_posture` | PRD §17 Q5 insurance |
| M7 fuel | `merchant_agreement`, `payment_partner` | The deal that doesn't exist |

On any box booted after 2026-07-29, all three came up enabled with all six gates unsatisfied.

**The 29 July owner decision is not the bug.** Preserving live behaviour on a product already
serving drivers was the right call; registering off would have taken M3 down on deploy. The bug is
that the mechanism silently produced the same outcome for M6 and M7, whose gates encode business
preconditions that do not exist.

**Call sites of `enable()` in the entire codebase:** one — `api/app/api/admin.py:1071`.
Every flag that is on today got there by assignment.

**Forward risk.** PRD v2.0 §3 specifies `a07_parking_ahead` with an **F13 validation gate on
inventory**, and states the reason plainly: *a parking search that returns zero results teaches a
driver the app is empty, and that lesson is not easily unlearned.* Built on the current mechanism,
that gate does nothing.

**Design note.** `register_flag`'s own AI-CONTEXT already draws the right distinction for
descriptions — a code default that refreshes, versus `enabled`, which is "the operator's state, and
a redeploy must never silently flip a flag back." A5's `SERVICE_PRESET_FLAG` and `register_all` both
use `enabled` to express a **code default**. A separate `default_on` column, consulted by
`is_switched_off` when no operator decision exists, would let `enable()` regain its monopoly on
writing operator state without any module going dark. **Owner decision — see F-12 for the
interaction.**

---

## F-03 — Every send returns the same provider ref · High · OBSERVED

```python
class _LazyCounterpartyGateway:
    def _pick(self):
        smtp = SmtpNotificationGateway(self._explicit)   # NEW instance every call
        return smtp if smtp.configured else RecordingNotificationGateway()
```

`SmtpNotificationGateway.__init__` sets `self.delivered = 0`. `send_email` increments and returns
`f"smtp-{self.delivered}"`. Because `_pick()` builds a fresh instance per call, the counter never
exceeds 1 — **every successful send in the product's life returns `smtp-1`.**

`.delivered` / `.failed` are read nowhere else in the codebase; they exist only to build that
string. So they are not metrics either.

A1 requirement 4 depends on F8 per-thread tracking. A constant ref cannot distinguish two sends.

---

## F-04 — The gateway production uses is untested · High · ABSENT

`_LazyCounterpartyGateway` appears **nowhere** in `api/tests/**`. The API modules hold one at module
scope — it is the object every real send goes through. Tests exercise `SmtpNotificationGateway`
directly, where the counter increments correctly and F-03 is invisible.

This is §23 entry 113's shape again: two constructors for one behaviour, tests on the one production
does not use.

---

## F-05 — The ledger is not idempotent · High · OBSERVED

`post_entry` is otherwise sound — ≥2 postings, positive amounts, per-account currency match,
`debits == credits` enforced before write, `CurrencyMismatch` on an unknown account.

But `JournalEntry.external_ref` is `String(300), nullable=True` with **no unique constraint and no
index**, in both the model and migration. Nothing prevents posting the same real-world event twice.

**Why this is worse than it sounds.** A duplicate entry still balances. The double-entry invariant
holds, so a reconciliation check passes while a driver's payable is doubled. The error is invisible
to exactly the test you would write to catch it.

**The pattern already exists in the codebase.** F2's `source_record` carries
`uq_source_record_kind_ref` on `(source_kind, external_ref)` for precisely this reason.

No money moves today (payment partner is a seam). That is the argument for the constraint now,
not after the first webhook retry.

---

## F-06 — No retry, no dead letter · High · ABSENT

One `smtplib.SMTP` attempt, 10-second timeout. On failure the exception class name is formatted into
a return string and dropped:

```python
except Exception as exc:
    self.failed += 1
    return f"smtp-failed-{type(exc).__name__}"
```

A transient blip or a Gmail rate-limit permanently loses a detention notice. F12 queues *driver-side*
offline actions; it does not cover a server-side send that failed after the driver's action
succeeded. With A12's "no monitoring," nothing would ever surface it.

DRIVE.md J0 §7 documents the driver-visible half: *"a wrong App Password fails as
`smtp-failed-SMTPAuthenticationError` in the F8 provider ref while the driver still sees 'Sent'."*

---

## F-07 — No throttle on authentication · High · ABSENT

```python
@router.post("/login", response_model=TokenOut)
def login(body: Credentials, db: Session = Depends(get_db)) -> TokenOut:
    account = identity.authenticate(db, body.email, body.password)
```

No rate limiter, no lockout, no attempt counter anywhere in the application. Two consequences:

1. **Credential stuffing** is unbounded against a live product with real driver accounts.
2. **CPU exhaustion.** `authenticate` runs Argon2 verify, which is deliberately memory-hard and
   slow. A few hundred concurrent POSTs to `/auth/login` can take the single VM down — no
   credentials required. This is a denial-of-service vector on a box with no monitoring and no
   backups.

Session tokens themselves are sound: `secrets.token_urlsafe(48)`, unique-indexed, expiry checked
with tz-normalisation, impersonation tokens explicitly refused by `current_account`.

---

## F-08 — Gmail as counterparty transport · **ACCEPTED (owner decision, 2026-08-07)** · OBSERVED

> **Decision:** Gmail remains the transport for all email operations for now. This finding is
> therefore **not a defect to fix** but a risk to hold deliberately, with the mitigation ladder
> below. Recorded rather than removed — the technical facts are unchanged by the decision, and a
> future session must be able to see what was accepted and why.

### What is being accepted

From `infra/.env.example`'s own AI-CONTEXT:

> `SMTP_FROM` MUST equal `SMTP_USERNAME` on Gmail. Google rewrites the From header to the
> authenticated account unless the address is a verified "Send mail as" alias.

So on a **consumer** Gmail account, a broker's accounts-payable clerk receives a detention notice
from a personal address, not `@haulmeter.online` — with no SPF/DKIM/DMARC alignment for the domain
the document itself claims to come from. A1's validation criterion is *"the recipient confirms it
arrived usable."* Spam-foldering is the failure mode, and a claim that lands in spam cannot reach
payment (DoD #3).

Two secondary constraints: a free-tier daily recipient cap in the low hundreds (the `.env.example`
records ~500), and dev and production sharing one account per the 2026-08-04 decision, so a test
send and a real send are indistinguishable after the fact.

### The mitigation ladder — Gmail stays at every rung

None of these require leaving Gmail. They are ordered by cost-to-benefit.

**Rung 1 — separate the dev account from the production account. (cheapest, do first)**
One extra Gmail account and one `.env` line. Removes the "a send from dev is a real send" hazard that
DRIVE.md J0 §7 warns about in bold, makes the production sent-folder an audit trail rather than a
mixed bin, and means a dev experiment cannot consume the production daily cap. This costs nothing and
addresses the one risk that is purely self-inflicted.

**Rung 2 — Google Workspace on `haulmeter.online`. (the one that actually fixes deliverability)**
Workspace is still Gmail — same SMTP endpoint, same App Password flow, same client code, no change to
`SmtpNotificationGateway`. What it buys is the thing consumer Gmail structurally cannot provide:

- `SMTP_FROM` can be `paperwork@haulmeter.online` and Gmail will not rewrite it
- SPF via the Google include, **DKIM signing on the haulmeter.online domain**, and a DMARC record
- A materially higher daily cap

That converts F-08 from *"the From line contradicts the document"* to *"the From line is
authenticated by the domain the document comes from"* — which is the single largest lever on whether
a broker's mail filter accepts a detention notice. **This is the rung that unblocks A1's validation
criterion.** Everything below it is mitigation; this is resolution.

**Rung 3 — verify the sending domain's DNS and prove it.**
Send a test to a seed address and read the received headers for `spf=pass`, `dkim=pass` and
`dmarc=pass` with alignment on `haulmeter.online`. Do this **before** asking a real driver to send a
real packet to a real broker, because A1's validation observation is unrepeatable — a first
impression in an AP clerk's spam folder is not one you get to retake.

**Rung 4 — record the bounce path.**
Gmail bounces return to the sending account. Nothing in the product reads that inbox, so a hard
bounce is invisible to both driver and system (compare F-06). At minimum, know whose job it is to
look. `@bolt.example` seed counterparties bounce back to the same inbox by design, per DRIVE.md.

### What this does *not* change

- **F-01 becomes more urgent, not less.** If the intent is "Gmail for all email operations," then a
  box silently configured to `mailpit` is a direct contradiction of the decision. The decision makes
  verifying the deployed `SMTP_HOST` the first thing to do, not an optional check.
- **F-03, F-04 and F-06 are transport-independent.** The constant `smtp-1` provider ref, the
  untested `_LazyCounterpartyGateway`, and the absent retry/dead-letter are properties of the gateway
  code, not of Gmail. They stand exactly as written.
- **Rung 2 is a purchase, not a code change.** No session can do it; it is an owner action, and it
  gates a Phase DoD item.

---

## F-09 — Location pings are never purged · Medium · OBSERVED

`f03_location` defines `purge_pings_older_than(db, cutoff)` and exports it through `public.py`.
Grepping the whole tree, its only caller is `api/tests/…` (one test). It is **not** in the worker's
`_jobs()` list, which contains exactly: `tpims_dynamic`, `tpims_static`, `eia_regional`,
`document_expiry`, `detention_clock`.

So `location_ping` grows without bound on a box with no backups, and whatever retention window the
PRD states is not enforced anywhere. F3 is the sensory system for the entire evidence engine, so
this table is also the fastest-growing one.

---

## F-10 — Worker scheduling is in-process only · Medium · OBSERVED

`Job.next_run` and `Job.failures` are fields on an in-memory dataclass keyed off `time.monotonic()`.

- **No advisory lock, no DB-side claim.** Two worker containers both run every job. Compose runs one
  replica, but a rolling restart briefly has two.
- **Every restart resets `next_run` to 0.0**, so all five jobs fire immediately on boot. Harmless for
  the idempotent upserts; `document_expiry` sends F8 notifications, so a crash-loop replays
  credential warnings with only F8's budget as a backstop.
- Per-attempt rows *are* persisted to `f14.job_run`, which is good — but they record history, not
  schedule state, so they cannot prevent a duplicate run.

---

## F-11 — The deploy path is outside every review · Medium · ABSENT

`10-infra-and-scripts.md` contains the compose files, `.env.example`, `.github/workflows/ci.yml` and
`api/scripts/*.py`. It does **not** contain `deploy.sh`, the `Makefile`, or `scripts/check_ports.sh`
— `collect_files.py`'s `EXTENSIONS` tuple has no `.sh` and no extensionless entry.

So the script that puts code on the box, and the one enforcing the locked ports, have never been in
a dump anyone reviewed. This is also why HANDOFF-118's claim about `deploy.sh:46` cannot be checked
from the dump.

**Cheapest fix in this document:** add `.sh` and an explicit filename list to `EXTENSIONS`.
(See also HANDOFF-118 §4 — that file is now tracked and public.)

---

## F-12 — Module gate and worker disagree on flag polarity · Medium · OBSERVED

| Predicate | Unregistered flag | Used by |
|---|---|---|
| `is_switched_off` | `False` → **runs** (fails open) | module gates |
| `is_enabled` | `False` → **does not run** (fails closed) | worker jobs, `/me`, feature checks |

Both defaults are individually well-argued (§23 entry 105: a bootstrap hiccup must not take twelve
modules dark). But they are opposite answers about the same key, and today they only agree because
F-02 force-enables everything.

**Sequencing consequence:** closing F-02 without also deciding M3's gates would leave M3's API open
(fails open) while `detention_clock` — M3's P0, the alert that free time expired — goes silent
(fails closed). **Fix F-02 and F-12 in the same change, or the wedge feature loses its clock.**

---

## 6. What is clean

Stated explicitly, because "we looked and found nothing" is a result.

### 6.1 Admin authorization
25 routes under `/admin`, all carrying `Depends(current_admin)`. `current_admin` checks
`platform_admin` in `account.roles` and raises 403. No unguarded route found.

### 6.2 Double-entry invariants
`post_entry` enforces ≥2 postings, strictly positive amounts, per-account currency match against the
entry currency, and `debits == credits` — all *before* any write. `balance()` is a plain
sum-debits-minus-sum-credits. Correct. (Idempotency is F-05; the arithmetic itself is sound.)

### 6.3 Share-link access control
`secrets.token_urlsafe(32)`; unknown, revoked and expired all raise the same `ShareNotFound` so a
caller cannot distinguish them by probing; bytes are **pinned** at share time and hashed, so a
refresh cannot silently show a grown chain; `extend_share` counts from now and never shortens;
opens are appended to the evidence chain. This is the best-designed surface I read.

### 6.4 Datetime handling
Zero occurrences of `datetime.now()`, `datetime.utcnow()` or `date.today()` in backend code. 110
uses of `datetime.now(UTC)`. Naive values read from the DB are tz-normalised at comparison sites
(`resolve_session`, `resolve_share`). Given a Perth-based owner and a US-only driver base, this is
the bug class that should have bitten and did not.

### 6.5 Map N+1
`_statuses_for` and `_default_badges_for` batch by signal type; `_build_pin` is a single pin
constructor with an AI-CONTEXT explaining why there must only be one. A9 §4's predicted `_enrich`
cost was measured at 5 ms and the real cost attributed correctly to the loop.

---

## 7. Suggested order

Not a plan — a sequencing argument. Each is its own plan-first session.

1. **F-01** — one command on the box. Everything about DoD #3 depends on the answer, and if it
   confirms, the fix is a config line plus a re-examination of the F8 record.
2. **F-05** — one migration, no behavioural risk, closes a class of error that is invisible once it
   happens. Do it while no money moves.
3. **F-07** — a login throttle. Live product, real accounts, single VM, no monitoring.
4. **F-02 + F-12 together** — needs an owner decision first (`default_on` versus tightening
   `enable()`), and must not be split or M3's clock stops.
5. **F-03 + F-04 + F-06** — one session on the counterparty gateway: real refs, retry with a dead
   letter, and a test against `_LazyCounterpartyGateway` rather than around it.
6. **F-09, F-10, F-11** — operational tail; folds naturally into A12.

**F-08 is decided, not open.** Gmail stays. Two owner actions remain and neither is a code change:
separate the dev and production accounts (rung 1, free), and move to Workspace on `haulmeter.online`
for domain-aligned SPF/DKIM/DMARC (rung 2), which is what actually gates A1's validation criterion.

---

---

# Part 2 — module deep sweep

Covering the three areas Part 1 listed as unread: M3 detention arithmetic, M6 booking, F6 document
storage. Plus F12, which turned out to matter to F-05.

| # | Finding | Severity | Kind | Bears on |
|---|---|---|---|---|
| F-13 | `book()` is a check-then-act race — no lock, no exclusion constraint | **Critical** | OBSERVED | M6, F7 |
| F-14 | `nights` is counted in UTC, not facility-local time | High | OBSERVED | M6 pricing |
| F-15 | `_overlaps` and `visit_window` scan unbounded history in Python | Medium | OBSERVED | A9 density |
| F-16 | `Content-Disposition` interpolates an unsanitised filename | Low | OBSERVED | F6 |

---

## F-13 — Double-booking race, and it posts money twice · **Critical** · OBSERVED

```python
def book(db, spot, driver_account_id, start_at, end_at, ...):
    if _overlaps(db, spot.id, start_at, end_at):
        raise SpotUnavailable(str(spot.id))
    ...
    entry = ledger.post_entry(db, ledger.EntryType.booking_payment, [...])
    booking = Booking(...)
    db.add(booking)
```

Read-then-write with **no `SELECT … FOR UPDATE` on the spot and no database constraint** behind it.
Two concurrent requests for the same spot and overlapping window both pass `_overlaps` and both
insert.

**The money consequence is worse than the double-booking.** Each call posts its own balanced journal
entry crediting `owner:{id}`, so the owner is credited twice for one night — and both entries pass
every invariant in §6.2. Note also that `post_entry` is called here **with no `external_ref` at
all**, so F-05's missing constraint could not have caught it even if it existed.

**The fix belongs in Postgres, not application logic.** With `btree_gist`:

```sql
ALTER TABLE m06.booking ADD CONSTRAINT ex_booking_no_overlap
  EXCLUDE USING gist (
    spot_id WITH =,
    tstzrange(start_at, end_at) WITH &&
  ) WHERE (state IN ('booked','checked_in','checked_out'));
```

That makes the race impossible rather than unlikely, and it survives a second API replica — which
`_overlaps` cannot, however carefully written.

**Not currently exploitable at scale**, since M6 activation waits on a payment partner and insurance
(PRD §17 Q5). But per F-02 the flag is *enabled* on every box, so the endpoint is live — and A7 is
specifically about driving booking volume through it.

---

## F-14 — Nights are counted in UTC · High · OBSERVED

```python
nights = max(1, (end_at.date() - start_at.date()).days)
```

`.date()` on a timezone-aware datetime returns the date **in that datetime's own tzinfo**. Values
arrive as UTC, so the night boundary is UTC midnight, not the facility's local midnight.

Worked example, US Central (UTC−5):

| Local stay | In UTC | `.date()` diff | Charged | Actual |
|---|---|---|---|---|
| 11pm Aug 7 → 5am Aug 9 | 05:00 Aug 8 → 11:00 Aug 9 | 1 | 1 night | **2 nights** |
| 6pm Aug 7 → 6am Aug 8 | 23:00 Aug 7 → 11:00 Aug 8 | 1 | 1 night | 1 night ✓ |

The `max(1, …)` papers over the short cases, which is why this reads as correct in most tests. A
stay starting late-evening local systematically undercounts by one night for facilities west of UTC
— in a US-only product spanning at least four time zones.

**This is the one place Part 1's clean datetime finding (§6.4) does not hold.** Every *instant* is
handled correctly; the bug is converting instants into **calendar days**, which needs the facility's
timezone and does not consult it. Worth checking whether `F2.Facility` carries a timezone column at
all — if not, that is the real prerequisite.

---

## F-15 — Unbounded history scans in two hot paths · Medium · OBSERVED

Both load every historical row and filter in Python:

```python
def _overlaps(db, spot_id, start_at, end_at) -> bool:
    for booking in db.scalars(select(Booking).where(Booking.spot_id == spot_id)):
```

```python
def visit_window(db, account_id, facility_id, since):
    sessions = db.scalars(select(GeofencePresence).where(...).order_by(entered_at))
```

Neither filters on time. A spot with two years of bookings is fully scanned on every availability
check, and `bookable_summary` calls `_overlaps` **once per spot** — an N+1 on top of a full scan.
`visit_window` walks every visit a driver ever made to a dock to answer a question about one of them.

Correct at today's volume; A9 §4 warns about exactly this shape at national density. Both are one
`WHERE` clause from bounded — `.where(Booking.end_at > start_at)`, and for `visit_window`
`.where(exited_at.is_(None) | (exited_at > floor)).limit(1)`.

---

## F-16 — Filename interpolated into a response header · Low · OBSERVED

```python
headers={"Content-Disposition": f'inline; filename="{doc.filename or doc.doc_type.value}"'}
```

`filename` is stored from upload with no sanitisation visible in `f06_documents`. A filename
containing `"` breaks the quoting and can inject a `Content-Disposition` parameter. Newlines would be
rejected by the ASGI layer, so this is parameter confusion rather than response splitting.

Low severity — the route enforces `doc.account_id != account.id`, so an attacker can only target
themself. Still worth `urllib.parse.quote` plus the `filename*=UTF-8''` form, which also fixes
non-ASCII filenames across the six launch locales.

---

## What is clean, part 2

### M3 detention arithmetic — correct, and unusually well-reasoned
`compute_detention` derives the amount from the **reported integer seconds**, not the float behind
them, so a clerk recomputing `seconds × rate` from the invoice face reproduces the figure exactly.
The AI-CONTEXT cites the real `0:00:38 · $120/h · $1.29` mismatch that motivated it. Free-time
boundary, `max(0.0, …)` on early departure, and the `ended` vs `accruing` split all check out.

### `visit_window` — §23 entry 73 is properly fixed
The $187.76 defect (earliest-ENTER-ever becoming this claim's clock start) is corrected at source:
F3 exposes `GeofencePresence` sessions, and the resolver returns the visit belonging to `since`,
skipping sessions closed before it. M3 no longer rebuilds "this visit" from raw events. Performance
is F-15; the logic is right.

### F6 document access control
`GET /documents/{id}` checks `doc.account_id != account.id` and returns an indistinguishable 404 for
a stranger's id. `Cache-Control: private`. Bytes are immutable by design (replace, never edit), so
the long cache is safe. `documents_for_account` filters at the query level rather than post-filtering.

### F12 offline ingest — the idempotency primitive done properly
`UniqueConstraint("account_id", "idempotency_key", name="uq_sync_account_idempotency")` in **both**
model and migration, with the handler running only on first apply and `SyncReceipt.applied`
distinguishing new from duplicate. Four call sites use it.

**This is the pattern F-05 and F-13 are missing.** The project already knows how to do this
correctly; the ledger and the booking table simply do not use it.

---

## 8. Caveats

- No running system was observed. Every INFERRED item needs one command.
- `deploy.sh`, `Makefile`, `check_ports.sh` were not available (F-11).
- The UI, the test suite as an artefact, and the migration chain's ordering were not audited.
- Not read closely, and therefore **not cleared**: M4 accessorial, M8 intelligence, M9 money tools,
  M12 fleet, F9's AI-gateway budget enforcement, and the F2 ingestion/dedupe pipeline. Absence from
  this report is absence of review, not evidence of correctness.

---

# Part 3 — residual sweep (F2, F9)

Covering the F2 ingest/dedupe pipeline and F9's AI gateway. M4, M8, M9 and M12 remain unread.

| # | Finding | Severity | Kind | Bears on |
|---|---|---|---|---|
| F-17 | AI module budgets are never configured — the cap is inert | High | OBSERVED | F9, cost |
| F-18 | `budget_used` sums all history — a budget is a lifetime cap, not a period cap | Medium | OBSERVED | F9 |
| F-19 | No merge-review queue; auto-merges land with no human in the loop | Medium | ABSENT | A9 §5 |
| F-20 | PRD v2.0 §3 A9 describes a dedupe mechanism the code does not implement | Low | OBSERVED | doc drift |

---

## F-17 — The AI budget cap is inert · High · OBSERVED

```python
def _check_budget(db: Session, module: str) -> None:
    budget = db.get(ModuleBudget, module)
    if budget is not None and budget_used(db, module) >= budget.budget_micros:
        raise BudgetExceeded(module)
```

**A module with no `ModuleBudget` row has no cap at all** — `_check_budget` returns silently and
`budget_remaining` returns `None`. Grepping the whole tree, `set_module_budget` has **no caller
outside `api/tests/`**. No module registers a budget; no migration seeds one; the admin console does
not appear to write one.

So F9's cost control is a mechanism that has never governed a call — **structurally the same finding
as F-02.** The pattern is now twice-confirmed in this codebase: a well-designed guard, tested in
isolation, with nothing in the product wired to switch it on.

**Severity is currently latent, not live.** `anthropic_api_key` defaults to `""`, so the gateway
falls back to `FakeModelProvider` and no money is spent. The exposure opens the moment a real key is
added — and M4 (lumper extraction), M9 (settlement parsing) and M11 (ghostwriter) all register
prompts at module load, so there are three callers waiting.

**Fix shape:** seed a default budget per module in `register_module`, the same place the flag is
registered. Note the ordering trap from §23 entry 105 — register the budget *before* enabling
anything that spends against it.

---

## F-18 — A budget is a lifetime cap, not a period cap · Medium · OBSERVED

```python
def budget_used(db: Session, module: str) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(AiCall.cost_micros), 0)).where(AiCall.module == module)
    )
```

No time window. `budget_used` sums **every call ever made** for that module, so once cumulative spend
crosses `budget_micros` the module is blocked permanently until a human raises the number. There is
no monthly or daily reset.

This may well be deliberate — a hard lifetime ceiling is a defensible design for a product that has
never spent a cent on inference. But nothing in the code says so, and "budget" in every other part of
this codebase (F8's `p1_budget_used`, §13.1's two-per-day) means a **recurring** allowance. A future
session reading `set_module_budget(db, "m04", 5_000_000)` will reasonably assume it renews.

Two smaller notes on the same function:

- **No reservation.** `_check_budget` reads, then the call happens, then `_record_call` writes.
  Concurrent calls can both pass the check and overshoot the cap. Bounded overshoot, not unbounded —
  worth knowing, not worth a lock.
- **Unindexed aggregate.** Summing `AiCall.cost_micros` filtered on `module` runs on every gated
  call. Needs an index on `module` before volume, not after.

**Resolve by writing down which one it is** — either rename to make the lifetime semantics explicit,
or add a period column. Ambiguity here becomes a silent outage the first time a module goes quiet.

---

## F-19 — No merge-review queue · Medium · ABSENT · *already known*

PRD v2.0 §3, A9 requirement 5: *"An admin merge-review surface is required."*

What exists: `POST /admin/facilities/{id}/merge` — a manual, human-initiated merge. What does not
exist: a queue of merges the **ingest pipeline performed automatically**, presented for review.
`upsert_record` → dedupe → `merge_facilities` runs with no human in the loop and leaves no
"someone should check this" record.

**This is already on the record, not a discovery.** HANDOFF part 3 §371 states *"a merge happened on
one click, and there is no unmerge from this console,"* and `13-ui-surfaces` carries an AI-CONTEXT
saying the same. Repeating it here because A9 multiplies facility count roughly fivefold, and the
two properties compound: automatic merges, at higher density, with **no reverse operation anywhere in
the tree** (`grep -rn "def unmerge\|def split_facility"` → nothing).

`merge_facilities` itself is careful — resolves to canonical first, refuses self-merge, refuses cycle
closure, enforced in one place for all four callers. The gap is not the merge; it is that a wrong one
is permanent.

**This is the strongest candidate for the propose-and-approve agent pattern** discussed earlier in
the session: deterministic blocking does the confident 95%, the ambiguous tail goes to a queue, a
human approves. Building the queue is a prerequisite either way.

---

## F-20 — The amendment describes a mechanism the code does not implement · Low · OBSERVED

PRD v2.0 §3, A9 requirement 5:

> geohash-7 blocking with 0.4 name similarity will produce more false merges once metros are dense

The code blocks on **distance**, not geohash:

```python
DEDUP_RADIUS_M = 60.0
DEDUP_NAME_SIMILARITY = 0.4
...
.where(func.ST_DWithin(cast(Facility.geom, Geography), point, DEDUP_RADIUS_M))
.where(func.similarity(Facility.name, name) >= DEDUP_NAME_SIMILARITY)
```

`Facility.geohash` is stored and indexed, but `find_duplicate_candidates` does not use it — and a
60 m radius is not equivalent to a geohash-7 cell (~150 m × 150 m, with the cell-boundary miss that
HANDOFF part 3 §288 measured: *"every sampled one in a different cell"*).

The similarity figure is right; the blocking description is stale. Low severity on its own, but the
governing document is what a future session plans against, and this project has been bitten by
prose-versus-code drift before (§23's "stopped believing the documents" sessions).

**Fix is one sentence in the amendment**, not code.

---

## What is clean, part 3

### F2 dedupe rules — the most carefully reasoned code in the backend
Every guard carries its measurement: placeholder names rejected as evidence (69 of 191 missed pairs
were two rows both named "Rest Area"); opposite carriageways separated only on *stated* disagreement,
so "Homestead SB" beside "Homestead" at 18 m still merges; numbered facilities blocked when numbers
differ; co-located amenities merged by proximity but only when the adapter marked them, only into a
destination host, never chaining. `fuel_station` and `repair` were each removed from the host set
with a measured reason (4 of 29 within-radius repair pairs in Wisconsin are different businesses).

### `merge_facilities` — cycle-safe and single-sourced
Resolves to the canonical row before writing, refuses self-merge and cycle closure, and the rule
lives in the function rather than in its four callers. The AI-CONTEXT names the measured defect it
replaced (146 local and 149 production rows pointing at an already-merged facility).

### `canonical_facility_id` — now covers admin too
The A9 §5 complaint that "an admin URL and a driver URL for the same id answer about different
places" **has been fixed.** Three admin facility routes now take `Depends(canonical_facility_id)`,
with an AI-CONTEXT explaining that an admin editing a merged id was editing the shadow. Worth
updating the amendment.

---

## 9. Still unread

M4 accessorial · M8 intelligence · M9 money tools · M12 fleet · the F2 **ingest adapters**
(NTAD/OSM/TPIMS/EIA parsing, as distinct from the dedupe rules audited above) · the migration chain's
ordering and downgrade paths.

Absence from this report is absence of review.

---

# Part 4 — M4, M9, migrations

| # | Finding | Severity | Kind | Bears on |
|---|---|---|---|---|
| F-21 | §23 entry 73 was never carried across to M4 — layover files false claims | **Critical** | OBSERVED | M4-FR, credibility |
| F-22 | M4's overnight test compares UTC dates — refuses genuine layovers | High | OBSERVED | M4, same root as F-14 |
| F-23 | `audit_settlement` compares a period document against an unscoped balance | High | OBSERVED | M9, DDD counter |
| F-24 | 57 of 59 migrations have a real `downgrade()`; 2 are `pass` | Low | OBSERVED | ops |

---

## F-21 — The $187.76 defect is still live in M4 · **Critical** · OBSERVED

§23 entry 73 was fixed in M3 by introducing `location.visit_window()`. **M4 has its own copy of the
original bug, unfixed.**

```python
# m04_accessorial/domain/service.py
def _arrival_departure(db: Session, account_id, facility_id):
    arrival = departure = None
    for event in location.list_events(db, account_id, facility_id):
        if event.event_type == location.GeofenceEventType.ENTER and arrival is None:
            arrival = event.occurred_at          # EARLIEST enter, ever
        elif event.event_type == location.GeofenceEventType.EXIT:
            departure = event.occurred_at        # LATEST exit, ever
    return arrival, departure
```

Side by side with the module that was fixed:

| | M3 detention | M4 accessorial |
|---|---|---|
| Resolver | `location.visit_window(…, claim.clock_since)` | `list_events()`, earliest ENTER / latest EXIT |
| Scoped to one visit | **Yes** | **No** |
| Takes a time anchor | `clock_since` | **no `since` parameter at all** |

M4's function does not even accept a time argument, so it cannot be scoped without a signature
change. A driver's second load to the same dock reads the *first* visit's arrival.

**The consequence is worse than M3's was.** M3's version produced a wrong *amount* on a real claim.
M4's decides whether a claim exists:

```python
if _as_utc(arrival).date() == _as_utc(departure).date():
    raise NoLayover("dwell did not span overnight")
```

With `arrival` from a visit weeks ago and `departure` from today, the dates differ, `NoLayover` is
**not** raised, and a **layover invoice is filed for a stop that was never overnight** — then sent to
a broker under the driver's name. A wrong figure invites a question; a fabricated claim invites a
refusal to deal.

`accrue_events` in M3 also calls `list_events`, but bounds it by `floor`/`departure` derived from
`visit_window` — correct. M4 is the only unscoped caller left.

**Fix:** give `_arrival_departure` a `since` and route it through `visit_window`, exactly as M3 does.
The primitive already exists; M4 was written before it and never revisited. Worth checking M4's
tests: they will pass either way, because a fixture with one visit cannot distinguish the two
implementations — which is why nine sessions of green suites did not see this.

---

## F-22 — "Overnight" is measured in UTC · High · OBSERVED

Same line, second defect, same root cause as F-14:

```python
if _as_utc(arrival).date() == _as_utc(departure).date():
```

`.date()` on a UTC-normalised value gives the UTC calendar day. A layover is a *local* overnight.

US Central (UTC−5), a genuine overnight stop:

| Local | In UTC | UTC dates equal? | Result |
|---|---|---|---|
| 8pm → 4am next day | 01:00 → 09:00 **same UTC day** | yes | **`NoLayover` raised — claim refused** |

So the two errors point in opposite directions: F-21 files claims that should not exist, F-22 refuses
claims that should. Both stem from the same missing input — the facility's timezone.

`_as_utc()` is doing exactly what its name says and is not the problem. The problem is asking a
calendar-day question of a UTC instant.

**Prerequisite:** does `F2.Facility` carry a timezone column? If not, that is the change that unblocks
F-14 and F-22 together. A US-only product spanning four time zones needs it for both pricing and
accessorials.

---

## F-23 — Settlement audit compares scoped against unscoped · High · OBSERVED

```python
def audit_settlement(db, settlement) -> list[Discrepancy]:
    paid = {}                                   # THIS settlement's lines
    for line in settlement.lines:
        paid[line.kind] = paid.get(line.kind, 0) + line.amount_cents
    owed, refs = _owed_by_kind(db, settlement.driver_account_id)   # ALL open receivables, all time
    ...
    missed = owed_cents - paid_cents
```

`paid` is scoped to one settlement document. `owed` is every unsettled receivable of that kind the
driver has, across every load, with no period or load filter. Subtracting one from the other is not a
like-for-like comparison.

Two consequences:

1. **False discrepancies.** A lumper receivable from a load this settlement does not cover is counted
   as "missed" on this settlement. The driver is told the broker underpaid on money that broker was
   never billed for yet.
2. **Repeat flagging.** `_owed_by_kind` only excludes `recovered` and `written_off`. A receivable
   stays "owed" until someone taps *the broker paid this* — and the AI-CONTEXT at
   `mark_receivable_paid` states that path is **driver-initiated and, until a second actor exists,
   the only way a receivable reaches `recovered`**. So a partially-paid balance is re-flagged on
   every subsequent settlement, and `_flagged_total` sums the duplicates.

`_flagged_total` feeds the earnings dashboard. Overstating "money the broker owes you" is the
same honesty failure §11.7 forbids elsewhere, pointed at the driver instead of the counterparty —
and it inflates a number adjacent to the North Star.

**Fix shape:** scope `owed` to the loads this settlement covers, or to its pay period. That requires a
settlement→load link; if none exists, that is the actual gap.

---

## F-24 — Migration downgrades · Low · OBSERVED

59 `downgrade()` functions, 57 with real bodies, 2 empty (`pass`). Better coverage than most projects
this size. Worth identifying which two, since an unreversible migration in the middle of the chain
means the rollback story ends there — relevant given A12's "deployment by tarball of the working
tree" and no proven restore.

---

## What is clean, part 4

### M3's `accrue_events` — the near-miss that was caught
The same unscoped `list_events` read sat three lines above the clock defect and was missed while
fixing it (§23 entry 75). It is now bounded by `floor` and `departure` from `visit_window`, with an
AI-CONTEXT noting that an append-only chain already polluted stays polluted — hence scoping the
write rather than filtering the read. Correct reasoning.

### `mark_receivable_paid` — honest about what did not happen
Posts **no ledger entry**, and explains why: a driver invoices the broker in their own name and is
paid into their own bank, so no cash crosses the platform. Posting `cash_clearing → driver_payable`
would record a movement that never occurred. The receivable's state carries the fact instead. This is
the correct call and the kind that usually gets made the other way.

### The `claim_paid` notification
Fires only when someone *other than* the driver records the recovery, so the person who just tapped
the button is not pushed about their own action. Dormant today by construction rather than by
oversight, and right the moment M12 or the collection partner exists.

---

## 10. Still unread after part 4

M8 intelligence · M12 fleet · the F2 **ingest adapters** (NTAD/OSM/TPIMS/EIA parsing) ·
migration chain ordering · the two empty downgrades (F-24).

Absence from this report is absence of review.

---

# Part 5 — M8, M12, ingest adapters (sweep complete)

| # | Finding | Severity | Kind | Bears on |
|---|---|---|---|---|
| F-25 | `true_profit` assumes zero detention recovery, and says so nowhere | Medium | OBSERVED | M8, §11.7 |
| F-26 | `rpm_after_cents` returns 0 for "undefined" | Low | OBSERVED | §11.7 |
| F-27 | Fleet rollups are N+1 per member | Low | OBSERVED | M12 at scale |

---

## F-25 — The profit model assumes the product does not work · Medium · OBSERVED

```python
net = revenue_cents - fuel_cost - tolls_cents - det_cost
```

`expected_detention_cents` is subtracted **in full**. That is the standard owner-operator "true rate"
calculation and it is defensible — detained hours are hours you cannot earn in.

But this platform's entire thesis is that detention gets *recovered*. Subtracting the full expected
cost silently models a world in which the driver recovers nothing, on a screen inside the app whose
job is recovering it. Two loads with identical revenue — one to a dock that detains you three hours
and pays, one to a dock that detains you three hours and does not — score identically here.

The `basis` dict carries `detention_sample_size` and `detention_confidence`, so the *confidence* in
the estimate is disclosed. What is not disclosed is the **assumption**: nothing in the payload says
"assumes no recovery." §11.7's rule is that a figure does not travel without what produced it, and an
unstated modelling assumption is exactly the kind of thing that rule exists to surface.

**Not necessarily a code change.** It may be the right conservative default. But it should be a
stated one — a `"detention_recovery": "assumed_none"` key in `basis` costs nothing and stops a future
session re-deriving the question.

---

## F-26 — Zero standing in for undefined · Low · OBSERVED

```python
rpm = round(net / loaded_miles) if loaded_miles else 0
```

Zero loaded miles yields `rpm_after_cents = 0`, which renders as a real rate of $0.00/mi rather than
"not applicable." This is the absence-dressed-as-a-result pattern §11.7 forbids, and the same shape
as the merged-facility crowd report (§23) that told a driver their submission landed when nothing
would ever see it.

`None` with a basis note is the honest answer. Small, but this codebase treats these as
non-negotiable everywhere else.

---

## F-27 — Fleet rollups are N+1 per member · Low · OBSERVED

`fleet_report` and `fleet_claims_desk` both loop over `_member_ids` calling `m4.money_owed`,
`m7.driver_analytics` and `ledger.list_receivables` once per driver. A 50-truck fleet costs ~150
queries per report load. Same family as F-15; M12 is not activated, so it is latent.

Note also that both compute "owed" from receivable state (`state not in _SETTLED`), which inherits
F-23's problem: a receivable stays owed until a driver taps *the broker paid this*. A fleet manager's
dashboard overstates for the same reason a driver's does.

---

## What is clean, part 5

### A9 requirement 1's named trap is already closed
The amendment's highest-risk instruction is *"Extend the osmium filter FIRST… if the filter does not
pass those tags into the extract, the rules never fire. HANDOFF-099 hit this exact trap."*

**It has been fixed.** `OSM_EXTRACT_TAGS` is a single tuple; `osm_extract_filter_args()` **renders the
osmium selectors from it**, and `api/scripts/osm_filter_args.py` prints them for the Makefile. The
AI-CONTEXT records the original defect verbatim — the Makefile kept its own copy, drifted, and *"six
of eight service rules read tags the extract never passed, so they had never fired."*

Cross-checked every service rule against the extract list — all present:

| Rule reads | In `OSM_EXTRACT_TAGS` |
|---|---|
| `shop=tyres`, `service:vehicle:tyres` | ✓ |
| `amenity=car_wash`, `service:vehicle:car_wash` | ✓ |
| `shop=truck_repair`, `shop=car_repair`, `service:vehicle:truck_repair` | ✓ |
| `service:vehicle:mobile_repair` | ✓ |
| `shop=truck_parts`, `service:vehicle:parts` | ✓ |
| `amenity=weighbridge` / `weigh_station` | ✓ |

`SERVICE_TOWING` has no selector, which is deliberate per A6 — it arrives from an admin edit or a
claiming vendor, and that absence is the argument for A6 over more ingestion.

**The amendment should be updated:** A9 requirement 1 reads as outstanding work and is done.
One residual caveat — whether the Makefile actually *invokes* `osm_filter_args.py` cannot be verified,
because the Makefile is not in the dump (F-11). That is the one link still taken on trust.

### M12's consent gate is enforced at the data layer
```python
def _member_ids(db, fleet_org_id) -> list:
    # the ONLY driver ids whose data may enter a fleet view — consent-gated
    return [m.driver_account_id for m in list_members(db, fleet_org_id, consented_only=True)]
```
Both `fleet_report` and `fleet_claims_desk` route through it, so an invited-but-not-consenting
driver's figures cannot enter a fleet view even though a manager can issue the invite. Route-level
`_require_manager` guards sit on top. Defence in depth, done the right way round — the data layer
enforces, the route layer is convenience.

### M8's basis discipline
Every estimate carries its provenance: `predict_parking` returns a basis, `detention_risk_flag`
returns `"no_data"` rather than a fabricated zero, `route_fuel_cost` returns `"no_network_fuel"`
when it cannot answer. F-25 and F-26 are the two places the discipline slips, and they are the
exceptions.

---

# Sweep complete — consolidated view

27 findings across five parts. Everything named in the original scope has now been read.

| Severity | Count | IDs |
|---|---|---|
| **Critical** | 4 | F-01, F-02, F-13, F-21 |
| High | 7 | F-03, F-04, F-05, F-06, F-07, F-14, F-17, F-22, F-23 |
| Medium | 8 | F-09, F-10, F-11, F-12, F-15, F-18, F-19, F-25, F-27 |
| Low | 4 | F-16, F-20, F-24, F-26 |
| Accepted | 1 | F-08 (owner decision, 2026-08-07) |

## The three patterns worth naming

**1. A mechanism built, tested, and never registered.** F-02 (validation gates) and F-17 (AI budgets)
are the same defect in different foundation modules: a well-designed guard whose precondition the
product never creates, with tests that construct the precondition themselves. One countermeasure
covers both — a startup assertion that every module has a flag row *and* a budget row, or the app
refuses to boot. That turns a silent absence into a loud one.

**2. A fix applied to the module being worked on, not to the defect class.** F-21 is §23 entry 73
still live in M4, nine sessions after M3 was fixed and `visit_window` was written for exactly this.
F-14 and F-22 are the same UTC-calendar-day error in two modules. When a defect gets a §23 entry,
the entry should name *every* call site of the bad pattern, not the one that was found.

**3. Idempotency present in one place, absent in three.** F12 does it correctly —
`uq_sync_account_idempotency` in model and migration, handler on first apply only. F7 (F-05) and M6
(F-13) do not, and M6's booking race posts money twice. The pattern is in the codebase; it just was
not reused.

## Where the four criticals sit relative to Phase DoD

- **DoD #3** (a detention claim reaching actual payment) is downstream of F-01 (the notice may never
  have left the box), F-08 (it may arrive in spam), and F-21/F-22 (M4 may file a claim that should
  not exist, damaging the same broker relationship).
- **A7** inherits F-02 — its inventory gate, the thing standing between a driver and an empty
  parking search, would not fire.
- **A9** is largely unblocked on the ingest side (part 5) and blocked on the operational side by
  A12, which F-07, F-09 and F-10 all belong to.

## Not read, and therefore not cleared

M10 community · M11 voice · the NTAD/TPIMS/EIA adapters (OSM was read) · migration chain ordering ·
the two empty `downgrade()` bodies · every line of the UI.

---

# Part 6 — M10, M11, migration chain (backend sweep closed)

| # | Finding | Severity | Kind | Bears on |
|---|---|---|---|---|
| F-28 | `redeem_points` is a check-then-act race — balance can go negative | High | OBSERVED | M10, A11 |
| F-29 | The daily contribution cap is coupled to the reward and can be silently disabled | Medium | OBSERVED | M10, A11 |
| F-30 | M11's intent classifier is English-only substring matching | High | OBSERVED | M11 DoD, six locales |
| F-31 | The two empty `downgrade()` bodies identified (closes F-24) | Low | OBSERVED | ops |

---

## F-28 — Points can be spent twice · High · OBSERVED

```python
def redeem_points(db, account_id, points, now=None) -> int:
    if points <= 0:
        return 0
    if points_balance(db, account_id) < points:      # READ
        raise InsufficientPoints(str(account_id))
    ...
    ledger.post_entry(db, ledger.EntryType.points_redeem, [...])   # WRITE
```

`points_balance()` is `sum(debits) − sum(credits)` over the account. Read, then write, with **no row
lock and no constraint**. Two concurrent redemptions both pass the check and both post — the balance
goes negative and stays there, because nothing in F7 forbids a negative points account.

**This is F-13's shape a third time** (after the ledger's missing `external_ref` constraint and the
booking overlap race). Points redeem against real parking bookings at `REDEEM_CENTS_PER_POINT`, so
this is money, not a scoreboard.

**Note on `book_with_points`:** it redeems *first*, then calls `m6.book()`, which can raise
`SpotUnavailable`. Today that is survivable only because `get_session()` rolls the whole request back
on an exception — the ordering is correct by ambient transaction semantics rather than by
construction. Any future caller that commits between the two steps loses the points. Book first,
redeem second, is the ordering that does not depend on the caller.

**A11 makes this live.** The requirement is explicitly *"points issue on accepted crowd reports →
earn points → discount the booking."* Issuing at volume against an unlocked balance is the moment
this stops being theoretical.

---

## F-29 — The daily cap can be turned off by a pricing knob · Medium · OBSERVED

```python
def award_contribution(db, account_id, kind, now) -> int:
    if _rate_limited(db, account_id, now):
        raise RateLimited(str(account_id))
    points = _earn_points(db, kind)
    if points > 0:                                   # <-- the log write is conditional
        crowd.issue_points(db, account_id, points)
        db.add(ContributionLog(...))
```

`_rate_limited` counts `ContributionLog` rows in the last 24 hours. But a row is only written **when
the contribution earns points**, and `_earn_points` reads a **live F13 config value**
(`m10_earn_<kind>`) that an admin can edit to `0`.

So setting an earn rate to zero in the admin console does not merely stop paying for that
contribution type — it makes those contributions **invisible to the rate limiter**, removing the
daily cap for them entirely. The anti-abuse control and the pricing control are the same lever, and
nothing says so.

Secondary: `_rate_limited` is itself check-then-act, so concurrent awards can exceed
`RATE_LIMIT_PER_DAY`. Bounded overshoot; worth knowing, not worth a lock.

**Fix:** log every contribution, paid or not, and let `points > 0` gate only the ledger issue.

---

## F-30 — Voice understands one of six languages · High · OBSERVED

```python
def classify_intent(utterance: str) -> str:
    u = utterance.lower()
    for intent, required, any_of in _RULES:
        if all(term in u for term in required) and (not any_of or any(term in u for term in any_of)):
            return intent
    return "unknown"
```

`_RULES` is a list of **English substrings**: `"start"`, `"detention"`, `"clock"`, `"meter"`,
`"saved"`, `"diesel"`, `"book"`, `"parking"`, `"sleep"`, `"what should i do"`. Nothing else.

A Spanish, Punjabi, Russian, Uzbek or Somali utterance matches no rule and returns `"unknown"` —
**five of the six launch locales**, against a module DoD that specifies ≥95% intent accuracy *per
language*.

This is a different and deeper gap than the known one. The handoffs record M11 as blocked on an
STT/TTS provider, which is true. But transcription is not the constraint here: **even with perfect
Spanish transcription, the classifier returns `unknown`.** The provider gap is procurement; this is
architecture. Ranked keyword rules do not extend to six languages by adding vocabulary — the
morphology of Russian and Uzbek alone defeats substring matching.

Two smaller notes in the same function:

- `.lower()` where the rest of this codebase uses `.casefold()` (F2's `_names_disagree`). For the
  five non-English locales, `.lower()` is the wrong normaliser regardless.
- Rules are **order-sensitive** and untested for ambiguity: `fuel_nearby` precedes `parking_nearby`,
  so *"where can I park near a gas station"* classifies as fuel.

M11 is not activated, so nothing is broken for a driver today. It matters because the module reads
as "built, pending a provider," and it is not — the six-locale requirement needs a different design.

---

## F-31 — The two empty downgrades, identified · Low · OBSERVED

Closing F-24. Of 59 migrations, 57 have real `downgrade()` bodies. The two that are `pass`:

- `0033_f01_vendor_role.py`
- `0058_a01_checklist_doc_types.py`

Both add enum values, which Postgres cannot drop from a type — so an empty body is the *honest*
implementation, not neglect. Worth a one-line comment in each saying so, since a bare `pass` is
indistinguishable from an unfinished one, and A12's restore story depends on knowing where the chain
genuinely cannot be reversed.

---

## What is clean, part 6

### The migration chain is linear with one head
59 revisions, one root (`down_revision = None`), no duplicate revision ids, and the chain resolves
`0057_a01_stop_packet → 0058_a01_checklist_doc → 0059_f13_config_decl`. `0059` is the single head,
matching the `alembic current` recorded in HANDOFF-118 for both dev and production. No branch, no
orphan.

*(My first automated pass reported three heads; that was a regex artefact — two `down_revision`
declarations use a formatting my pattern missed. Recorded because a false alarm about a migration
chain is worth being explicit about.)*

### Points are a real ledger currency
`points_balance` reads through F7 with `Currency.points`, and redemption posts a proper double-entry
`points_pool → points_balance`. Most implementations would have used an integer column on the
account and drifted. The race (F-28) is a locking gap, not a modelling one — the model is right.

### The ghostwriter prompt is hard-coded to English
```python
"Write a {tone} {kind} to the counterparty in ENGLISH. Facts: {facts}"
```
§12.3 says counterparty-facing text is always English regardless of the driver's locale, and the
prompt enforces it at the point of generation rather than trusting a caller. Correct, and the kind of
rule that usually leaks.

---

# Backend sweep closed

31 findings across six parts. Every backend area named in the original scope has been read.

| Severity | Count |
|---|---|
| **Critical** | 4 |
| High | 10 |
| Medium | 10 |
| Low | 6 |
| Accepted | 1 |

## The fourth pattern

Part 5 named three. F-28 adds a fourth instance to one of them and makes it the dominant finding of
this audit:

**Check-then-act on a value that decides money — four times, in four modules.**

| Finding | Module | What races | Result |
|---|---|---|---|
| F-05 | F7 ledger | no `external_ref` uniqueness | duplicate posting, balanced and invisible |
| F-13 | M6 booking | `_overlaps` then insert | two drivers, one spot, owner paid twice |
| F-28 | M10 points | `points_balance` then post | negative balance |
| F-29 | M10 contributions | count then insert | daily cap exceeded |

All four have the same fix shape — a database constraint or a row lock — and F12 already demonstrates
the pattern correctly with `uq_sync_account_idempotency`. **This is one session's work across four
modules, and it is the highest value-per-hour item in this document.** None of it needs an owner
decision.

## What has not been read

M10's community surfaces beyond points · NTAD / TPIMS / EIA adapters (OSM was read) · the F14 admin
domain · every line of the UI, including the 40 surfaces and the layout harness.

Absence from this report is absence of review.

---

# Part 7 — remaining adapters, F14 (backend complete)

| # | Finding | Severity | Kind | Bears on |
|---|---|---|---|---|
| F-32 | A TPIMS record with no `timeStamp` is stamped with ingest time | Medium | OBSERVED | A3, §11.7 |
| F-33 | `derive_parking_status` returns "some" from no reading if called ungated | Low | OBSERVED | §11.7 |

---

## F-32 — A missing feed timestamp becomes a fresh reading · Medium · OBSERVED

```python
def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(UTC)       # <-- ingest time stands in for reading time
```

The handoffs record the correct property explicitly — *"the WI belief carries `freshest_at` = the
**real feed timestamp**, not ingest time."* That holds whenever `timeStamp` is present. When it is
absent or unparseable, the reading is stamped **now**, and a driver sees `0m · IDOT` on a reading
whose actual age is unknown.

This matters more under A3 than it did before. A3's whole point is that a feed reading must be
attributed to the feed rather than to "1 driver" — so the badge is about to become *more* trusted,
not less. A fabricated freshness on an authoritative-labelled reading is the §11.7 failure in its
most damaging form: the two honesty signals (source and age) disagree, and only one of them is
visible.

**Fix shape:** return `None` and let the caller skip the record, the same way `parse_available`
returns `None` for `"Unknown"` and `has_usable_reading` drops it. The pattern is already in the file,
one function above.

Narrow in practice — it needs a malformed feed record. But TPIMS is the only live availability feed,
IL is the only live state, and A9 requirement 6 is about adding eight more publishers whose payload
conformance is unknown.

---

## F-33 — A defensive branch that asserts · Low · OBSERVED

```python
def derive_parking_status(status: DynamicStatus) -> str:
    ...
    return "some"  # unknown count but open -> conservative "some"
```

Reachable only if a caller skips `has_usable_reading`. Today exactly one caller exists and it gates
correctly (`run_tpims_dynamic` counts the skip). So this is unreachable in practice.

Recording it because "conservative" is doing work the value cannot support: `"some"` is a positive
claim about spots existing, derived from no reading. `"empty"` would be worse and `"full"` would be
wrong, but the honest answer is *no belief*, which is what the gate already produces. A defensive
branch that fabricates is a landmine under the second caller.

---

## What is clean, part 7

### TPIMS honours its own trust flag — just not where I first looked
`trust_data` is parsed in the adapter and *not* consulted in `has_usable_reading`, which initially
reads like a dropped signal. It is enforced one layer down in F10: `if not trust_data: return` — the
reading is never recorded, so it cannot present as a belief. Correct placement, since the decision
belongs to whatever writes beliefs, not to the parser.

### `parse_available` — a category is never a number
`"Low"` returns the `LOW` sentinel and is never int-parsed; `"Unknown"`, `"n/a"` and empty return
`None` rather than 0. The AI-CONTEXT notes real Illinois feeds emit `"Unknown"`, which is not in the
V2.2 spec. Parsing a category as a count is exactly how a "0 spots available" fabrication would have
entered the map, and it is explicitly prevented.

### F14 moderation implements Q-8 as specified
`MODERATION_SLA_HOURS = 72` matches the M13 extension's Q-8 law; `overdue_moderation` queries against
it; and reported content transitions to `hidden_pending` on both reviews and promotions — so it
leaves the driver's view at report time rather than at resolution time. The read paths filter on
`ModerationStatus.pending` rather than post-filtering.

### The notification inbox is honest about suppression
`INBOX_STATUSES` deliberately includes `suppressed` and excludes `pending`, with the reasoning
written down: a quiet-hours-suppressed P1 is never re-dispatched, so the inbox is *the only delivery
it ever gets* — hiding it would destroy it, not defer it. And `pending` is excluded because showing a
driver a decision the system has not finished making is how a half-written row becomes a fact. Both
calls are right and neither is obvious.

---

# Backend audit complete

**33 findings across seven parts.** Every backend package in the repository has now been read:
`api/app/foundation/f01`–`f15`, `api/app/modules/m01`–`m13`, `api/app/api/*`, `api/app/ingest`,
`api/app/core`, `api/migrations`, and `infra/`.

| Severity | Count | IDs |
|---|---|---|
| **Critical** | 4 | F-01, F-02, F-13, F-21 |
| High | 11 | F-03, F-04, F-05, F-06, F-07, F-14, F-17, F-22, F-23, F-28, F-30 |
| Medium | 10 | F-09, F-10, F-11, F-12, F-15, F-18, F-19, F-25, F-27, F-29 |
| Low | 7 | F-16, F-20, F-24, F-26, F-31, F-32, F-33 |
| Accepted | 1 | F-08 |

## What the backend is actually like

The prevailing quality is high and the reasoning is unusually well recorded — most non-obvious
decisions carry an AI-CONTEXT explaining the measurement behind them, and several of the cleanest
results in this document (the pinned share links, F12's idempotency, the TPIMS category handling, the
suppression-visible inbox) are calls that most codebases get wrong.

The defects cluster in three places, and none of them is "the logic is wrong":

1. **Concurrency** — four check-then-act races on values that decide money (F-05, F-13, F-28, F-29).
   One session, one pattern, no owner decision required.
2. **Registration** — two guards that were built, tested, and never switched on (F-02, F-17).
3. **Propagation** — fixes applied to the module in hand rather than the defect class (F-21 is §23
   entry 73 still live in M4; F-14/F-22 are one timezone error in two modules).

Every one of these was invisible to a green suite, which is the standing warning in PRD v2.0 §9
holding true a sixth time.

## The three questions this audit cannot answer

1. **What is `SMTP_HOST` on the box?** (F-01) One command. Everything about DoD #3 turns on it.
2. **Does `F2.Facility` carry a timezone?** (F-14, F-22) If not, that column is the prerequisite for
   both.
3. **Does the Makefile invoke `osm_filter_args.py`?** (F-11) The single-source-of-truth for OSM tags
   exists in Python; the invocation lives in a file no review has seen.

## Not audited

The UI in full — 40 surfaces, 44 core files, the layout harness, and the Quasar/Vue state machine.
That is a separate sweep of comparable size.
