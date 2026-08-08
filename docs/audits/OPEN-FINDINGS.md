# OPEN-FINDINGS — the live defect queue

The 45 findings of AUDIT-2026-08-07, with status. **CLAUDE.md points every session here.**
Update the status column when you close one; the audit documents themselves are a dated
record and are never edited.

**Created 2026-08-08 (session 119).** It did not exist before then, though CLAUDE.md and
`AUDIT-INDEX.md` both referenced it.

Two other files the index lists as living in `docs/audits/` are real but elsewhere —
**`WATCH.md` is at `docs/WATCH.md`** and **`split_dump.py` is at the repo root.** One is
genuinely absent: **`S23-PROPOSAL-loading-state.md` does not exist anywhere in the tree**,
and it is what three of the four blocked criticals are waiting on. The two kickoff briefs
in `docs/kickoffs/` do exist.

## Status vocabulary

| Status | Means |
|---|---|
| **OPEN** | Not started. |
| **CLOSED** | Fixed, with a test that fails without the fix, and the gates green. |
| **ACCEPTED** | The owner decided to live with it. Not a defect any more. |
| **BLOCKED** | Needs an owner decision or a fact nobody has yet. The blocker is named. |
| **PARTIAL** | The measurable half is done and the remainder is named. Never "mostly closed". |

The audit's own evidence tags still apply and are not status: **OBSERVED** was read from a
dump, **INFERRED** needs a command on the box, **ABSENT** means the thing is missing rather
than wrong. *Re-grep before acting on any of them — the dump is dated.*

## Scoreboard

| Severity | Open | Blocked | Partial | Closed | Accepted | Total |
|---|---|---|---|---|---|---|
| Critical | 1 | 4 | 0 | 3 | 0 | **8** |
| High | 6 | 0 | 1 | 10 | 0 | **17** |
| Medium | 9 | 0 | 1 | 2 | 0 | **12** |
| Low | 5 | 0 | 0 | 2 | 0 | **7** |
| Accepted | — | — | — | — | 1 | **1** |
| **Total** | **21** | **4** | **2** | **17** | **1** | **45** |

**Session 119 closed sixteen** — F-05, F-07, F-13, F-14, F-17, F-18, F-21, F-22, F-23, F-28,
F-29, F-31, U-01, U-02, U-07, U-08 —
and left **two partial** (U-03, U-05) with the remainder named. F-24 was already closed by
F-31 inside the audit itself; it is counted here for completeness and is not this session's
work.

**Three of the eight criticals are closed (F-13, F-21, U-07). Four are blocked on the
missing §23 loading-state proposal or on a command nobody can run from here. One is open:
F-02**, and it needs the `default_on` versus `enabled` decision before anyone starts.

Every critical that could be closed without an owner decision now is.

**Closing findings opened one.** U-01's fix made the map pin's foreground expressible in
CI, and the first thing CI said was that white on `--marker-500` is **2.04:1** in dark
theme against a 3:1 floor. That is not a regression — it shipped that way — but it was
unobservable until the literal became a token. See §Blockers.

---

## Backend — 33 findings

| ID | Severity | Status | One line |
|---|---|---|---|
| F-01 | Critical | **BLOCKED** | Production email probably delivers to Mailpit on the VM. Blocked on one command on the box — no box credential in the dev environment. See §Blockers. |
| F-02 | Critical | OPEN | Validation gates have never governed a flag. Needs the `default_on` vs `enabled` decision; must ship with F-12 or M3's detention clock goes silent. |
| F-03 | High | OPEN | Every send returns the same provider ref. |
| F-04 | High | OPEN | The gateway production uses is untested. |
| F-05 | High | **CLOSED** | Ledger not idempotent → `uq_journal_entry_type_ref`, partial unique on `(entry_type, external_ref)`. Session 119. |
| F-06 | High | OPEN | No retry, no dead letter on SMTP failure. |
| F-07 | High | **CLOSED** | Throttled per identifier (5) and per IP (20) in a sliding 15-min window, in Postgres so it fails closed, checked BEFORE the hash runs; `VERIFY_SLOTS` caps concurrent Argon2 so a flood cannot starve the threadpool. Session 119. |
| F-08 | — | **ACCEPTED** | Gmail as counterparty transport (owner decision, 2026-08-07). Two owner actions remain, neither a session: split dev from production, and Workspace on the domain for aligned SPF/DKIM/DMARC. |
| F-09 | Medium | OPEN | Location pings are never purged. |
| F-10 | Medium | OPEN | Worker scheduling is in-process only. |
| F-11 | Medium | OPEN | The deploy path is outside every review — `deploy.sh`, `Makefile`, `check_ports.sh` are not in the dump. Adding `.sh` to `collect_files.py`'s `EXTENSIONS` is the cheapest fix in either audit. |
| F-12 | Medium | OPEN | Module gate and worker disagree on flag polarity. Ships with F-02. |
| F-13 | Critical | **CLOSED** | Double-booking race posting money twice → `ex_booking_no_overlap` EXCLUDE constraint, and `book()` claims the row before any money moves. Session 119. |
| F-14 | High | **CLOSED** | Nights counted in the lot's local calendar. Session 119. |
| F-15 | Medium | OPEN | Unbounded history scans in two hot paths. |
| F-16 | Low | OPEN | Filename interpolated into a response header. |
| F-17 | High | **CLOSED** | Every module seeded a cap at boot, and a module with no row falls back to the compiled default — there is no uncapped state, and no state where a missing row is an outage. `test_module_flags` asserts the invariant. Session 119. |
| F-18 | Medium | **CLOSED** | Calendar-month cap; the column is `monthly_budget_micros` so it cannot be misread. Had to ship WITH F-17 — seeding budgets against a lifetime sum would have made each module go permanently dark. Composite `(module, created_at)` index. Session 119. |
| F-19 | Medium | OPEN | No merge-review queue. Already known. |
| F-20 | Low | OPEN | The amendment describes a mechanism the code does not implement. |
| F-21 | Critical | **CLOSED** | §23 entry 73's defect in M4 → `_arrival_departure` routed through `location.visit_window`, anchored on the stop's appointment. M4 was the last unscoped `list_events` caller, so the class is closed. Session 119. |
| F-22 | High | **CLOSED** | "Overnight" measured in the dock's local calendar — this was REFUSING real layover claims. Session 119. |
| F-23 | High | **CLOSED** | `owed` is scoped to the settlement's own pay period. **Named limitation:** it scopes by the receivable's creation date as a proxy, because there is no settlement→load link — work in the period whose receivable is filed later still falls outside. The link is the audit's own deeper fix and is a schema change. Session 119. |
| F-24 | Low | **CLOSED** | Migration downgrades — 57 of 59 real, 2 empty. Closed by F-31, which identified the two; not by session 119. |
| F-25 | Medium | OPEN | The profit model assumes the product does not work. |
| F-26 | Low | OPEN | Zero standing in for undefined. |
| F-27 | Low | OPEN | Fleet rollups are N+1 per member. |
| F-28 | High | **CLOSED** | Points can be spent twice → `lock_account` row lock taken before the balance is read; `book_with_points` books before it redeems. Session 119. |
| F-29 | Medium | **CLOSED** | The daily cap could be turned off by a pricing knob → every contribution is logged, `points > 0` gates only the ledger issue. Session 119. |
| F-30 | High | OPEN | Voice understands one of six languages. |
| F-31 | Low | **CLOSED** | The two empty downgrades identified — `0033_f01_vendor_role` and `0058_a01_checklist_doc_types`, both adding enum values Postgres cannot drop. Each now carries an AI-CONTEXT line saying the `pass` is deliberate, which was the finding's whole ask. Session 119. |
| F-32 | Medium | OPEN | A missing feed timestamp becomes a fresh reading. |
| F-33 | Low | OPEN | A defensive branch that asserts. |

## UI — 12 findings

| ID | Severity | Status | One line |
|---|---|---|---|
| U-01 | High | **CLOSED** | Map drew outside the token system → `--on-accent` composition plus new `--shadow-pin`/`--scrim` (§23 entry 130), and a `token-discipline` sweep that keeps literals out. **Opened a new finding:** white on `--marker-500` is 2.04:1 in dark theme — see §Blockers. Session 119. |
| U-02 | High | **CLOSED** | Per-driver keys moved under `CACHE_PREFIX`, plus a third instance the audit missed (`vendor_appearances`) and the in-memory refs that outlived logout. Asserted on what driver B renders. Session 119. |
| U-03 | High | **PARTIAL** | The fallback is now counted and warned in dev, with per-locale counts at `/dev` — kickoff steps 1–2 done. Measured **0** across es/pa/ru/uz/so on the five tab roots + Load-live, and the detector was proved by planting two missing keys. **The zero is narrow:** mocked/empty API data left most of the ~45 dynamic `t(\`ns.${...}\`)` families unrendered. Session 119. |
| U-04 | Medium | OPEN | Seven surfaces not in the layout harness. `load-worst-case` added (the U-04-adjacent item); the other six remain. |
| U-05 | Medium | **PARTIAL** | `.filters-chip` 40→48 dp. `.cluster` measured at 36 dp with NO expanded hit area — below even §11.2's 44 dp map exemption; reported, not changed. Two portal controls untouched pending an owner call. Session 119. |
| U-06 | Critical | **BLOCKED** | Money tab shows fabricated earnings on fetch failure. Blocked on the §23 loading-state entry — and the proposal file itself is missing. |
| U-07 | Critical | **CLOSED** | Rejected writes are dead-lettered whole (path, body, opId) and counted on the status strip. Session 119. **Remaining, by design:** the strip says how many, not which — naming them needs a surface, which is a design question. |
| U-08 | High | **CLOSED** | 429/5xx now retry on the next flush with a bounded attempt cap (head-of-line protection); only non-429 4xx dead-letters. Session 119. |
| U-09 | Critical | **BLOCKED** | Six surfaces substitute invented data — including a CDL and truck stops. Same §23 blocker as U-06. |
| U-10 | Critical | **BLOCKED** | Map renders fixture pins on every cold start, not only offline. Same §23 blocker. |
| U-11 | High | OPEN | There is no loading state. The §23 proposal is about this. |
| U-12 | High | OPEN | The ban, the test, and the nine fixtures it does not cover. |

The five UI law violations in `KICKOFF-ui-comprehension-fixes.md` need no research and no
decision — the index puts that kickoff fourth, ahead of everything blocked.

---

## Blockers, named

1. **F-01 — what is `SMTP_HOST` on the box?** One command:
   `docker compose exec api python -c "from app.core.config import get_settings as g; s=g(); print(repr(s.smtp_host), s.smtp_port)"`
   The code half is confirmed locally and is worse than the audit's "probably": `config.py`
   defaults to `mailpit`, `.env.example` ships `SMTP_HOST=mailpit`,
   `docker-compose.deploy.yml` runs a mailpit service on the box, and `configured` is
   `bool(host and port)`. Falling back to the recording gateway requires `SMTP_HOST` to be
   **blank**, not un-overridden. HANDOFF-118 §5.2 says the opposite; the handoff is wrong.
2. **U-06, U-09, U-10 — the §23 loading-state entry.** A skeleton is a §22.2 component
   pattern, so it cannot be improvised. `AUDIT-INDEX.md` says the proposal blocks three
   criticals and tells you to read it "now" — but **`S23-PROPOSAL-loading-state.md` is not
   in the tree.** It has to be written before it can be approved, so the blocker is one
   step further back than the index thinks.
3. **F-02 + F-12 — the `default_on` versus `enabled` decision.** Must not be split.
4. **NEW (session 119) — `--marker-500` fails the non-text contrast floor in dark theme.**
   A white pin glyph on it measures **2.04:1**; WCAG 1.4.11 and §16 require 3:1. That is
   the "Some" parking pin and, by E3.1's inverted valence, the **OPEN** weigh-station pin
   — the one a driver is meant to act on. Dark `--ledger-500` is 3.12:1, a hair over;
   every light-theme fill passes (4.33–5.35:1). **Changing a palette colour is a §22.2
   never-improvise category**, so it is pinned in `contrast.test.js` at its measured value
   with a roster check: the ratio cannot drift down silently, and a repair fails the test
   until the exception row is deleted. Needs an owner decision. §23 entry 130.
5. **Two portal touch targets** (`FleetWorkspaceSurface`, `OwnerPortalSurface`, both 40 dp).
   §6.5 grants no portal exemption in writing, but applying the glove floor to a desktop
   form is a design decision rather than a fix. Untouched, deliberately.
6. **`.cluster`'s hit area is 36 dp** — measured, and it does **not** exceed its visual
   size the way `.pin` does (a 44 dp button around a 28 dp puck). It is below §6.5's 48
   and below §11.2's deliberate 44 dp map-pin exemption too. Reported, not changed.

## Questions the audit could not answer

1. What is `SMTP_HOST` on the box? (F-01, above.)
2. ~~Does `F2.Facility` carry a timezone column?~~ **ANSWERED, session 119: no, it did
   not** — and neither did anything else. `DriverProfile.home_timezone` exists but is
   written by nothing outside the tests, so the product had no working notion of local
   time anywhere. `facility.timezone` now exists, resolved from coordinates and stored on
   first use. F-14 and F-22 are closed.
3. Does the Makefile invoke `osm_filter_args.py`? (F-11.)

## The pattern behind six of the eight criticals

> **The product asserts something it does not know.**

F-01 says a notice was sent. F-21 files a claim for a stop that was never overnight. U-06
shows money not earned. U-07 says synced after dropping a write. U-09 shows a CDL that is
not theirs. U-10 shows a truck stop that does not exist. §11.7 is the law all six break,
and every one of them sits beside an AI-CONTEXT or §23 entry arguing the honesty case
correctly for an adjacent case. The gap is never understanding — it is that a fix lands
where it was found and not where the pattern lives.

**So when you close one of these, grep for the rest of its class before writing the
handoff.** That is what session 119 did with `external_ref`: F-05 was filed against the
ledger, and the same missing ref turned up in M6's `book()`, which is why the two were
closed together.
