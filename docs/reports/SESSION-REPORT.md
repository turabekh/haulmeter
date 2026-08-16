# SESSION-REPORT — M3 detention hardening

2026-08-11 · branch `main` · nothing pushed, nothing deployed, stack left running.
Baseline commit `5af1e9e`; nine commits, one per task.

---

## 1. Findings

| ID | Status | What happened |
|---|---|---|
| **F1** | **CLOSED** | Duplicate open claims are impossible in Postgres; `start_claim` is get-or-create; `claim_for_stop` is deterministic. T2, T3. |
| **F2** | **CLOSED** | `generate_pack` refuses a claim that has left `open`; a second receivable for one detention is impossible. Both HTTP callers answer 409. T2, T3. |
| **F3** | **CLOSED** | `POST /detention/start` checks ownership and returns 201/200. T3. |
| **F4** | **CLOSED** (worse than described) | The invented recipient is gone from all four sites — **two m03, two m05, none in m04**, which is not the distribution the finding gave. And the real cause is deeper: see §3.1. T4. |
| **F5** | **CLOSED** | "Sent" means the linked message row has `sent_at`. Five delivery states, derived and rendered. T4. |
| **F6** | **CLOSED** | Dunning is a scheduled job with three bounds; `escalate` keeps its `external_ref`. T5. |
| **F7** | **CLOSED** | The pre-detention warning is wired to the notice endpoint, phase-aware, once-only, with its own column and no evidence record. T6. |
| **F8** | **DID-NOT-REPRODUCE** | A dispatch site already exists and is better than the one specified. See §3.2. T7 skipped. |
| **F9** | **CLOSED** | The dead-letter queue has a driver-facing surface — the `retrying` and `failed` states on the claim and Load screens. T4. |
| **F10** | **CLOSED-AS-FOUND** | The badge already discloses its sample size via the `profile.stops_basis` pattern. No behaviour change; a test added because nothing pinned it. T8. |
| **F11** | **CLOSED** | Idle ticks no longer commit. T5, T8. |
| **N-04** | **CLOSED** (new, found by this session) | Dev's `migrate` service ran migrations from the baked image, not the mounted tree. See §3.3. T2. |

**Every finding is accounted for. Nothing is BLOCKED.**

### Gates, against the T1 baseline

| | Baseline | Final | |
|---|---|---|---|
| pytest | 1558 | **1620** | +62 |
| vitest | 746 (39 files) | **755 (41 files)** | +9, +2 files |
| layout | 283 | **286** | +3 (the notice observation) |
| ruff + import-linter | clean · 30/30 | **clean · 30/30** | |

All four gates are green: `1620 passed` · `755 passed (41)` · `286 passed` · `All checks passed!`

> **A pre-existing baseline flake, recorded because it was red before this session touched
> the tree:** the T1 layout sweep failed `sheet-facility · pa` — the voice chip intercepting
> a pointer event on a map pin under eight-worker contention. Re-run in isolation it passed
> 28/28, and the **final sweep passed it too** (286/286, exit 0). So it is a contention flake
> rather than a defect, it is not caused by anything here, and the "283 green" figure in
> HANDOFF-121 should be read as "283 green on a good run".

---

## 2. Revert-checks

Every fix was reverted locally and the named test confirmed red, then restored.
**Two of these failed to go red on the first attempt, and both were my tests being wrong
rather than the fixes being fine** — those two rows are the most useful in the table.

| # | Reverted | Went red |
|---|---|---|
| T2-a | Both partial unique indexes removed from the models | `test_the_database_refuses_a_second_open_claim_for_one_stop`, `..._second_receivable_for_one_external_ref` |
| T3-a | `generate_pack`'s state guard | `test_filing_a_company_drivers_pack_twice_is_refused` — **see below** |
| T3-b | The ownership check on `/detention/start` | `test_starting_a_claim_on_another_drivers_stop_is_refused` |
| T3-c | `external_ref=m03:<claim_id>` | `test_the_receivable_carries_the_claim_as_its_external_ref` |
| T3-d | Get-or-create → blind create | `test_starting_a_claim_twice_returns_the_same_claim`, `test_starting_twice_creates_one_claim_and_says_which_happened` |
| T4-a | `sent` back to `message is not None` | `test_a_failed_send_is_not_reported_as_sent` + 2 — **see below** |
| T4-b | Unconditional evidence append | `test_a_failed_send_puts_nothing_in_the_evidence_log` + 1 |
| T4-c | The fake recipient restored | `test_the_fake_recipient_does_not_exist_anywhere_in_the_tree` + 2 |
| T4-d | The re-tap guard removed | `test_tapping_send_again_while_retrying_does_not_queue_a_second_notice` + 1 |
| T5-a | The dunning job removed from the scheduler | `test_the_dunning_job_is_actually_scheduled` |
| T5-b | The 7-day stale window | `test_switching_this_on_over_a_backlog_does_not_spray_the_missed_ones` |
| T5-c | The `collection_partner_agreement` gate check | `test_the_escalation_offer_waits_on_the_collection_partner_gate`, `test_a_gate_row_that_does_not_exist_is_not_an_open_gate` |
| T5-d | The once-only column check | `test_a_nudge_goes_out_on_day_three_and_only_once` |
| T5-e | The 28-day scan bound | `test_a_receivable_older_than_the_scan_window_is_not_scanned_at_all` |
| T6-a | The two notices collapsed into one path | 4 tests in `test_pre_detention_notice_api.py` |
| T6-b | The pre-notice writing `start_notice_sent_at` | `test_twenty_nine_minutes_out_warns_the_broker` + 1 |
| T6-c | The once-only pre-notice guard | `test_the_warning_goes_out_once` |
| T8/F11 | `if commit:` restored | `test_an_idle_detention_clock_tick_does_not_commit` + 1 |

### The two that stayed green, and what they exposed

**T3-a.** Removing `generate_pack`'s state guard changed nothing — `uq_receivable_external_ref`
caught the second filing and produced the same `ClaimAlreadyFiled`. The layers are redundant
for an invoicing driver. They are **not** redundant for a company driver: evidence-only mode
opens no receivable, so there is no `external_ref` and the index cannot see it. The guard is
the only thing between one stop and an unbounded number of re-anchored evidence packs. The
test that now covers it is the company-driver one.

**T4-a and T4-b.** Restoring `message is not None` and the unconditional evidence append both
stayed green, because **every notice test in the project ran against the recording gateway,
where "an object came back" and "the mail went out" are the same thing.** That is precisely
how the defect shipped and survived. `tests/api/test_notice_delivery_api.py` exists because of
it: it makes the gateway fail, which is the only condition under which the two differ.

---

## 3. What was underneath the findings

### 3.1 F4 is structural, and much worse than "a bad fallback string"

The finding describes a fallback recipient. The reason that fallback was always taken is that
**nothing in this product has ever written `contact_email`.**

- `POST /load` is the only route that creates a broker, and it never set one.
- No screen anywhere collects it. `create_counterparty` has accepted the parameter since F5
  shipped; only tests have ever passed it.

So every counterparty row a driver has created carries NULL, and every M3 detention notice was
addressed to the invented literal. Under real SMTP that is `SMTPRecipientsRefused` — a
**permanent** failure `PERMANENT_FAILURES` correctly never retries — while the driver's screen
said "Broker notified — detention on record."

Combined with HANDOFF-121 §11.1 (production `SMTP_HOST` pointed at Mailpit on the VM), the
detention wedge has never delivered a notice to a human, by two independent mechanisms.

Measured on the dev database during T5: of 13 invoiced claims, **10 dunning actions were
skipped for `no_email`.** That is the same fact showing up from a different direction.

`POST /load` accepts `counterparty_email` now, so the address is recordable. **The
driver-facing input does not exist and is the highest-value follow-up in §5.** Until it does,
`no_email` is the normal state of every load, which is why its copy names the remedy rather
than only the failure.

### 3.2 F8 does not reproduce, and the shipped design is better than the specified one

T7 was skipped. The evidence:

- `m09_money.mark_receivable_paid` dispatches a P0 `claim_paid`, deep-linked via
  `m3.claim_for_receivable`, with a six-locale catalogue and a test file.
- There is **no `ReceivableState.paid`** — the terminal state is `recovered`. The finding's
  grep target does not exist.
- Once-only is enforced by F7's transition table (`recovered -> recovered` raises), which is
  stronger than the `driver_paid_alert_at` column T7 specified: a column can be cleared, a
  state machine cannot be talked around.
- It fires only when the actor is **not** the receivable's own account — a logged owner
  decision (§23 entry 108): a driver who just tapped "the broker paid this" is the last person
  who needs a push about it. Today the endpoint is driver-only, so the dispatch is correct and
  dormant by construction, ready for the moment a fleet manager or collection partner exists.

Implementing T7 as written would have contradicted a logged owner decision and pushed drivers
about facts they had just entered. **`driver_paid_alert_at` was therefore not added to the
migration** — a nullable column nothing writes is the built-and-inert shape this codebase keeps
finding.

### 3.3 N-04 — a new defect, found by writing the first migration since N-03 shipped

Dev's `migrate` service had **no source mount**, while `api` and `worker` both mount
`../api:/app`. So migrations ran from the image built at some earlier point while the
application ran from the working tree.

1. A migration written after the last image build was invisible to it and silently did not apply.
2. Worse on the second turn: once the database is stamped at a revision the image does not
   carry, `alembic upgrade head` fails with *"Can't locate revision"* — and because api and
   worker wait on `service_completed_successfully`, **neither can start.** One unbuilt
   migration takes the whole dev stack down. This happened, mid-session, and is how it was found.

121's N-03 proof could not have caught it: it downgraded and re-applied a migration **already
in the image**. Only a newly written one reaches the bug.

Fixed dev-only. `docker-compose.deploy.yml` mounts no source anywhere — the image *is* the code
there — so migrate reading the image is correct in production and would be wrong here.

---

## 4. Decisions taken under §3 authority

| Decision | Reasoning |
|---|---|
| **No `driver_paid_alert_at` column** | T7 does not reproduce (§3.2); a column nothing writes is inert weight. |
| **`escalation_ref` is a new column** | T2 said "reuse an existing field if one fits". None does: `receivable_ref` is ours, and the receivable's own `external_ref` is now M3's filing backstop. |
| **The fake-recipient grep matches the double-quoted form** | The first version failed on its own source and on the comments explaining the removal. Prose about the defect uses backticks and stays findable; what must never return is the literal as a **value**. The needle is assembled at runtime so the test file cannot match itself. |
| **`claim_for_stop` breaks ties on `id`** | `created_at` defaults to `now()`, which is *transaction* time — two claims written in one transaction share it exactly, and the order was ambiguous. |
| **`DUNNING_WINDOW` is computed as `max(DUNNING_DAYS) + DUNNING_GRACE`** | 28 = 21 + 7 is not a coincidence. A shorter window would let the escalation offer fall out of the scan set while still current — a follow-up that silently never sends, which is F6's own shape. Pinned by a test so editing either number forces a look at the other. |
| **m05's refusal raises `ValueError`** | §8 caps m05 at "the one-line recipient refusal". The route already catches `ValueError` → 503 with the draft preserved and nothing sent. 503 is not the ideal status for "no address on file" — a more precise code is m05's own follow-up, and the safety-critical half (never a fake recipient) is unaffected. |
| **`POST /load` accepts `counterparty_email`** | Two lines. Without it the `no_email` copy would name a remedy the product has no way to accept, which is the "action their mode does not have" lie §12.6 forbids. The UI input remains a follow-up. |
| **The Send CTA still shows in `no_email`** | Tapping it returns the `no_email` state and surfaces the remedy. Hiding the button would leave the driver with no explanation at all. |
| **`freeMinutesLeft` floors** | Matches the server's own `dispatch_free_time_warning`. Rounding up would tell a driver with 29:01 left that they have 30 — the one direction this figure must never err in. |
| **Two orphaned locale keys deleted** | `load.notice_sent`/`load.notice_sent_ok` are replaced by the five-state vocabulary. An unused string is six translations maintained for nothing. |
| **The five states share one key namespace** | `notice.delivery.*` is read by both the claim screen and the Load tab, so the two surfaces cannot drift into describing the same fact differently. |

### Divergences from the prompt, because the live code contradicted it

- **F4's distribution.** The prompt said two m03, one m04, one m05. It is **two m03, two m05,
  none in m04**.
- **F8/T7 skipped entirely** (§3.2).
- **F10 needed no fix** — closed as found, test added.
- **`driver_paid_alert_at` omitted** from T2's column list.
- **T6's "the response's `delivery` field applies to both"** required splitting `delivery_of`
  out of `notice_delivery`: the warning is a different message row, and the claim's
  `notice_delivery` tracks the start notice, which a warned stop has not sent yet.

---

## 5. Follow-ups, explicitly out of scope

1. **A driver-facing input for the broker's email — the highest-value item here.** The address
   is recordable via the API now and no screen collects it, so `no_email` remains the normal
   state of every load. Until this exists the detention wedge cannot deliver to anyone
   (§3.1), and F-01's `.env` fix on the VM does not change that.
2. **m04 adopting `external_ref`** on its receivables. The partial unique index is already
   there; only M3 populates it. M4's callers were deliberately left alone.
3. **Automating counterparty sends.** Deliberately not done — human-in-the-loop is kept for
   both the warning and the start notice.
4. **The `arrival or now` trigger fallback** in the clock math. Pre-existing, four callers,
   explicitly out of scope and untouched.
5. **Sample-bounding for facility stats.** `facility_detention_stats` is COUNT-bounded (the 50
   most recent claims), not time-bounded, so a busy dock's "recent" reaches back further than a
   quiet one's. The disclosure is honest either way; whether the bound should be a time window
   is a product question.
6. **m05's refusal status code** — 503 today, see §4.
7. **`SMTPRecipientsRefused` is treated as permanent**, which is right for a malformed address
   and wrong for a broker who changed theirs. Not touched; noted because §3.1 made it visible.

---

## 6. Manual verification

### 6.1 Migration 0067 — apply, downgrade, re-apply, and the pre-check

```
$ make migrate
INFO  [alembic.runtime.migration] Running upgrade 0066_f13_default_on -> 0067_m03_claim_hardening

$ psql -c "select indexname from pg_indexes where indexname in (...)"
 uq_detention_claim_open_stop | CREATE UNIQUE INDEX ... ON m03.detention_claim
                                USING btree (stop_ref) WHERE (state = 'open'::m03.claim_state)
 uq_receivable_external_ref   | CREATE UNIQUE INDEX ... ON f07.receivable
                                USING btree (external_ref) WHERE (external_ref IS NOT NULL)
(2 rows)
new columns present: 6

$ alembic downgrade 0066_f13_default_on
INFO  [alembic.runtime.migration] Running downgrade 0067_m03_claim_hardening -> 0066_f13_default_on
indexes: 0   columns: 0

# plant a violating row and prove the pre-check refuses rather than dying mid-apply
$ psql -c "insert into m03.detention_claim (...) select ... where state='open' limit 1;"
INSERT 0 1
$ alembic upgrade head
RuntimeError: 0067 cannot apply: 1 stops with more than one OPEN detention claim already
exist and would violate the new constraint. Reconcile them first — this migration will not
choose which row survives.
Offenders: (UUID('9109fd42-e47f-437b-b0af-f7c5178ad2da'), 2)

$ psql -c "delete from m03.detention_claim ..."   # the planted row only: 77 -> 76
DELETE 1
$ alembic upgrade head          # clean
$ alembic current
0067_m03_claim_hardening (head)
```

**Dev-data reconciliation: none was needed.** Before the migration the dev database held 76
claims with **0** duplicate open `stop_ref`s and 13 receivables with **0** non-null
`external_ref`s. The single row deleted above is the one this verification planted.

### 6.2 The dunning runner, against the real dev database

Recording gateway (`SMTP_HOST` blanked for that process only — §2.1), `commit=False`,
rolled back afterwards:

```
run 1: {'scanned': 13, 'nudged': 0, 'firmed': 0, 'offered': 0,
        'skipped_no_email': 10, 'skipped_stale': 15, 'skipped_ungated': 0}
run 2: {'scanned': 13, 'nudged': 0, 'firmed': 0, 'offered': 0,
        'skipped_no_email': 10, 'skipped_stale': 15, 'skipped_ungated': 0}
```

This is the bounds doing exactly what they are for: **switching dunning on over live data
sends nothing.** 15 actions are outside the grace window and 10 have no address (§3.1). The
second run is identical because nothing was dispatched, so no column was set.

### 6.3 The three notice states, observed rather than asserted

`ui/layout/observe-notice-delivery.spec.js`, 360 × 800 dp, dark. It runs inside
`make ui-layout` — an observation nobody re-runs decays into a screenshot in an old handoff —
with images opt-in behind `OBSERVE_SHOTS=1` so a sweep leaves the tree clean.

```
OBSERVED — retrying: the row names the failure, no delivery claimed
OBSERVED — no_email: the blocker and its remedy, no delivery claimed
OBSERVED — sent: the broker was notified, and the row may say it
3 passed
```

| State | Screenshot | What the driver reads |
|---|---|---|
| `retrying` | `docs/handoffs/assets/notice-retrying-360dp.png` | "Notice didn't send — retrying" |
| `no_email` | `docs/handoffs/assets/notice-no-email-360dp.png` | "No broker email — add one to notify" |
| `sent` | `docs/handoffs/assets/notice-sent-360dp.png` | "Broker notified" |

Against a failing gateway the API half was verified too: the message row keeps
`sent_at IS NULL` with an `smtp-failed-` ref, and **the evidence timeline gains nothing.**

### 6.4 N-04's failure mode, reproduced and fixed

Before the fix, `docker compose run --rm api alembic downgrade` aborted with
`service "migrate" didn't complete successfully: exit 255`, and the migrate log read
`Can't locate revision identified by '0067_m03_claim_hardening'`. After adding the mount the
same command ran the downgrade normally. §3.3.

---

## 7. Safety

No email left this machine. Every send path was exercised against either the recording gateway
(`SMTP_HOST` blanked for that process) or a `FailingGateway` test double. `infra/.env` was not
modified. Nothing was pushed and nothing was deployed. The evidence log was never rewritten —
only what gets appended going forward changed, and it changed in the direction of appending
less.
