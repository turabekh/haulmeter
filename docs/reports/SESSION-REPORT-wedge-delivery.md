# SESSION-REPORT — wedge delivery: the broker's email, honest resends, M4 guards

2026-08-11 · branch `main` · nothing pushed, nothing deployed, stack left running.
Baseline commit `d5034b0`; seven commits, one per task (plus two lint fixes).
Companion to `SESSION-REPORT.md`, which is not modified.

**No migration, no `.env` change, no counterparty schema change, no backfill.** D1 exists
precisely so those could wait, and they did.

---

## 1. T1 verification

### Pre-session anchors — all REPRODUCE

| Claim | Evidence |
|---|---|
| `f05.Counterparty.contact_email` String(320) nullable, **no account column** | `models.py:35`; the row is id/name/kind/mc/email/phone/payment_behavior/claim_count/created_at |
| `create_counterparty` inserts a fresh row every call | `f05/domain/service.py` — plain construct, no lookup |
| Its only production caller is `POST /load` | grep: sole non-test site `api/load.py:197` |
| `/tonu` + `/lumper` resolve via `_require_load` — existence only | `m04_accessorial.py:49-53`, used at `:71`, `:97` |
| `/layover` does a bare `get_stop` null-check | `m04_accessorial.py:81-83` |
| The three amount inputs are unconstrained `int` | `TonuIn:36`, `LayoverIn:41`, `LumperIn:46` |
| `_file` creates the claim then opens the receivable, no idempotency | `m04/domain/service.py:70-105` |
| No M4 route test asserts a 403 | confirmed — this session's are the first |
| `m03.generate_pack` guards `amount_cents > 0` | the invoice branch; the precedent M4 lacked |

### Last session's claims — all REPRODUCE

`POST /load` accepts `counterparty_email` (**unvalidated** — so T2's validator is new on
that path) · five-state `notice_delivery` derived and rendered via a dynamic key ·
`no_email` copy reads "No broker email — add one to notify" · `start_notice_message_ref`
exists · 0067's partial unique index on `f07.receivable(external_ref)` ·
`SMTPRecipientsRefused` is in `PERMANENT_FAILURES` · dunning counts `skipped_no_email` ·
the screenshot spec runs inside `make ui-layout`.

### One new finding, from T1

**A delivered notice was still being resent.** `send_detention_start_notice` guarded only
`DELIVERY_RETRYING`, so a claim whose notice had actually gone fell through and sent a
second email to the broker — and, because the route appended `notice_sent` on synchronous
success, wrote a **second record into the tamper-evident evidence log** for one stop. The
UI hides it (the rung retires once `notice_sent`), so it needs a replayed request — which
is exactly what the offline write queue exists to produce. The previous session's fix was
incomplete rather than wrong: it closed the queued double-send and left the delivered one
open. D2 closes it, and §3 below records a second defect that fell out of fixing it.

### Baseline vs final

| | Baseline (T1) | Final | |
|---|---|---|---|
| pytest | 1620 | **1676** | +56 |
| vitest | 755 (41 files) | **769 (42 files)** | +14 |
| layout | 286 | **289** | +3 |
| ruff + import-linter | clean · 30/30 | **clean · 30/30** | |

All four green: `1676 passed` · `769 passed (42)` · `289 passed` · `All checks passed!`.
The `sheet-facility · pa` contention flake noted in the prior report did **not** recur.

> The T1 background lint run reported exit 2. It is not a real baseline failure — it ran
> after editing had begun and caught two of my own in-progress errors. The true baseline
> was clean, verified at the previous session's end and again immediately after.

---

## 2. Task status

| Task | Status |
|---|---|
| **T1** Verify and baseline | CLOSED |
| **T2** Backend: the email's lifecycle | CLOSED |
| **T3** Frontend: collect, show, fix-in-place | CLOSED |
| **T4** M4 filing guards | CLOSED |
| **T5** Finish line | CLOSED |

Nothing BLOCKED.

---

## 3. Revert-checks

Every fix reverted locally, the named test confirmed red, then restored.
**Two stayed green on the first attempt.** Both were my tests being weak, not the fixes
being unnecessary — and both are the most useful rows here.

| # | Reverted | Went red |
|---|---|---|
| T2-a | PATCH ownership check | `test_patching_another_drivers_load_is_refused` |
| T2-b | Copy-on-write collapsed to in-place | `..._is_copied_not_edited`, `..._identity_forward`, `test_the_patch_reports_a_copy_when_the_row_is_shared` |
| T2-c | D2 loosened to resend a delivered notice | `test_case_2_a_delivered_notice_is_never_sent_again` |
| T2-d | Validator bypassed on `POST /load` | `test_a_junk_address_at_creation_is_refused_before_the_load_exists` |
| T2-e | Validator bypassed on the PATCH | `test_a_junk_address_on_the_patch_is_refused` |
| T3-a | Inline affordance removed from `no_email` | `puts the input inline...`, `re-derives the delivery state on save...` |
| T3-b | Client validation removed from the shared field | `blocks the save while the address is junk` |
| T3-c | Client validation removed from the creation form | `refuses to submit a junk address, and says why` |
| T4-a | TONU ownership | `test_tonu_on_another_drivers_load_is_refused` (+ the 404 test) |
| T4-b | Layover ownership | `test_layover_on_another_drivers_stop_is_refused` |
| T4-c | Lumper ownership | `test_lumper_on_another_drivers_load_is_refused` |
| T4-d | `gt=0` alone, service guard intact | `test_the_route_refuses_a_nonsense_amount` — **see below** |
| T4-e | Service amount guard alone, `gt=0` intact | `test_the_service_refuses_a_nonsense_amount_too` ×3 |
| T4-f | `external_ref` removed | the two double-file tests + the orphan test |
| T4-g | Savepoint removed | the two double-file tests + the orphan test |

### The two that needed a second attempt

**T4-d — two layers that were not independently testable.** Removing `gt=0` left the test
green, because the service guard caught the zero and the route translated it to **the same
422**. A bare status assertion cannot tell two layers apart, which is precisely how one
layer rots behind the other. The shapes differ — Pydantic returns a list of errors naming
the field, the service a plain string — so the test now pins the error *shape*. Two layers
are only two layers if each fails on its own.

**T2's evidence double-append**, found while making D2's tests pass rather than by a
revert: the route conditioned its `notice_sent` record on `message is not None`, which
under D2 now means *"there is a message"*, not *"we sent one"* — so returning the existing
delivered message re-appended the record. Freshness is read off the claim relinking, which
only a fresh send does.

---

## 4. Decisions under §3 authority

| Decision | Reasoning |
|---|---|
| **The client validator lives in `ui/src/core/contact.js`, duplicating the server rule** | Two copies is a drift risk, taken deliberately and stated in the file: the server decides (it is the only one an offline-queued write or a second client can be held to), the client exists so a typo is caught while the driver is still holding the paper. If they disagree, the UI is the bug — and the server's own refusal is rendered when it happens. |
| **One `BrokerEmailField` for both surfaces, `variant` chooses the framing** | The load tab states a fact; the claim screen presents a blocker. Two components would drift exactly the way the five delivery states nearly did. Copy is passed in; behaviour is not. |
| **The load-tab field sits OUTSIDE the checklist `<ul>`** | A checklist item is evidence the driver captured; this is a property of the load. A count-based test caught the distinction, which is the right reason to respect it. |
| **`copied` is in the PATCH response** | Under copy-on-write the load's counterparty id changes, and a client holding the old one shows a stale address. The caller cannot infer it. |
| **The creation field blocks submit when invalid, but never when empty** | An invalid address would be a 422 the sheet's catch swallows, losing a confirmed rate con. Empty is the normal case and must stay frictionless. |
| **Saving re-reads rather than patching local state** | `notice_delivery` is derived server-side from the linked message *and* the address; the only honest way to show the new state is to ask again. |
| **Validation errors are translation KEYS, not sentences** | Six locales, and the component renders `t(key)`. The server's message is English and shown only when the client's rule let something through. |
| **`test_the_route_refuses_a_nonsense_amount` asserts the error shape** | See §3. Status alone cannot distinguish the layers. |
| **All test addresses use reserved example domains** | §2. Two validator fixtures originally used `a@b.co` and `acme@x.com` — never sent anywhere, but changed to `.example` because "never sent" is a property of today's code. |

### Divergences from the prompt

- **`POST /load` was not already validating** the email (the prompt said "confirm whether"),
  so the validator is new on that path as well as the PATCH.
- **T1 found one defect the brief did not describe** — the delivered-notice resend, above.
- **A second defect surfaced while implementing D2** — the evidence double-append, above.
- Nothing else. D1, D2 and D3 are implemented as written.

---

## 5. Manual verification

### 5.1 D2's five cases, over HTTP

`tests/api/test_counterparty_email_api.py`, one test each, plus two composite cases:

| Case | Behaviour |
|---|---|
| no linked message | sends |
| linked and delivered | never resends; **one** `notice_sent` in the timeline, asserted |
| retryable, same address | no new message, answers `retrying`, one row in the dead-letter queue |
| permanent failure | sends fresh, relinks, **old row survives as history** |
| failed to a different address | sends fresh to the new address |
| retryable to a *stale* address | sends fresh — the sweep would otherwise re-present the old address forever |
| `no_email` → address added → send | delivers to the new address |

### 5.2 Dunning inherits the fix with no code change

`test_a_claim_skipped_for_no_email_dunned_once_the_address_exists`: a claim counted
`skipped_no_email` dispatches on the next run once the address exists and its action is
still in the window. **No dunning code was touched** — it reads the address at send time,
which is what makes this free.

### 5.3 Screenshots (360 × 800 dp, dark)

Added to the same `make ui-layout` observation spec, opt-in behind `OBSERVE_SHOTS=1`:

| State | File |
|---|---|
| The creation field | `docs/handoffs/assets/broker-email-create-360dp.png` |
| The inline fix in `no_email` | `docs/handoffs/assets/broker-email-inline-fix-360dp.png` |
| Sendable after saving | `docs/handoffs/assets/broker-email-fixed-360dp.png` |

The creation shot is driven through the **real path** — open the sheet, hand it a file, let
the parse come back unreadable (the state this stack runs in with no model key), land on the
confirm form. The first version clicked with a catch-all and asserted nothing, which is a
screenshot pretending to be a test.

```
OBSERVED — creation: the broker email field is offered on the confirm form
OBSERVED — no_email: the input is inline, in the state that complains
OBSERVED — fixed: the blocker is gone, the notice is merely unsent
6 passed
```

### 5.4 Safety

No email left this machine. Every send path ran against the recording gateway
(`SMTP_HOST` blanked by conftest) or a `FailingGateway`/`CountingGateway` double. Every
address in every new file is a reserved example domain — verified by grep across the diff.
`infra/.env` untouched; the owner's SMTP fix is untouched and unprepared.

---

## 6. Follow-ups

1. **Counterparty identity is not designed — an F5-section question, and the largest one
   here.** Rows are created per load and never deduped, while M8/M12 aggregate payment
   behaviour by *name*. So "the counterparty registry" does not exist as an entity: a
   broker is N rows with one name, and `claim_count`/`payment_behavior` accumulate per row
   rather than per broker. D1 is written to be correct either way, which is why this could
   wait — but until it is decided, no screen can honestly show "your history with this
   broker". Needs: a decision on identity (MC number? name+MC? an explicit registry?), and
   only then a migration.
2. **Lumper dedup needs a per-stop shape.** Multiple lumper fees per load are legitimate,
   one per stop, and the route carries no `stop_id`. Deliberately excluded from D3 and
   pinned by a test so it stays a decision. Fixing it means changing the route's contract.
3. **Recipient permanence after D2.** `SMTPRecipientsRefused` is still permanent, which is
   right for a malformed address. D2 makes it livable by sending fresh when the address
   changes — but a broker who fixes their *own* mail server still needs a driver to retype
   the same address to trigger a resend. A "try again" affordance on `failed` would close
   it; not built, because it is a new control rather than a state.
4. **An account column on `f05.counterparty`**, and/or dedupe in `create_counterparty` —
   both deliberately deferred by D1, both dependent on (1).
5. **m05's no-recipient refusal returns 503** (carried from the prior session).
6. **The `no_email` state is still the normal case for existing loads.** Nothing backfills
   addresses, correctly — but every load created before this session has none, and only the
   claim screen tells the driver so.

### Recommendation to the owner

**After the production SMTP fix, send the first live notice to an inbox you control.**

Until now no counterparty message could reach anyone, so the SMTP path has never been
exercised end to end against a real recipient — and this session removes the *other* reason
it couldn't. Two independent things change at nearly the same time, and the first real send
is the only test that covers both. Create a load with your own address as the broker email,
accrue a stop past free time, tap Send, and confirm what arrives: the subject, the body, and
that the evidence share link in it opens. A rehearsal costs one load; the alternative is
finding out from a broker.
