# AUDIT-2026-08-07 — index

Full backend and UI audit of Haulmeter, plus the artefacts it produced.
**Tree state:** HANDOFF-118 · `longhaul_latest.txt`, 721 files · read as a static dump, no running
system observed.

---

## The documents

| File | What it is | Read it when |
|---|---|---|
| `BACKEND-AUDIT-2026-08-07.md` | 33 findings, 7 parts. Every backend package read. | Planning any backend session |
| `UI-AUDIT-2026-08-07.md` | 12 findings, 4 parts. Structural laws, errors/offline, fixtures, tests. | Planning any UI session |
| `S23-PROPOSAL-loading-state.md` | **Owner decision required.** Skeleton primitive + four-state rule. | Now — it blocks three criticals |
| `KICKOFF-loading-state-and-fixtures.md` | Session brief. Closes U-06, U-09, U-10, U-11. | After the §23 entry is approved |
| `KICKOFF-ui-comprehension-fixes.md` | Session brief. Five UI law violations, no research needed. | Any time |
| `WATCH.md` | Driver observation protocol. Companion to DRIVE.md. | **After** the fixtures are gone |
| `split_dump.py` | Regenerates the project-knowledge split from a fresh dump. | Whenever the dump is refreshed |

---

## Totals

| Severity | Backend | UI | Total |
|---|---|---|---|
| **Critical** | 4 | 4 | **8** |
| High | 11 | 6 | 17 |
| Medium | 10 | 2 | 12 |
| Low | 7 | 0 | 7 |
| Accepted | 1 | 0 | 1 |
| **Total** | **33** | **12** | **45** |

### The eight criticals

| ID | One line | Where |
|---|---|---|
| F-01 | Production email probably delivers to Mailpit on the VM | backend |
| F-02 | Validation gates have never governed a flag | backend |
| F-13 | Booking race posts money twice | backend |
| F-21 | §23 entry 73 still live in M4 — files layover claims that should not exist | backend |
| U-06 | Money tab shows fabricated earnings on fetch failure | UI |
| U-07 | Offline queue silently discards server-rejected writes | UI |
| U-09 | Six surfaces substitute invented data — including a CDL and truck stops | UI |
| U-10 | Map renders fixture pins on **every cold start**, not only offline | UI |

---

## The one finding behind six of the eight

> **The product asserts something it does not know.**

F-01 says a notice was sent. F-21 files a claim for a stop that was never overnight. U-06 shows money
not earned. U-07 says synced after dropping a write. U-09 shows a CDL that is not theirs. U-10 shows
a truck stop that does not exist.

§11.7 is the law all six break — and the project already knows it. **Every one of these sits beside
an AI-CONTEXT or §23 entry arguing the honesty case correctly for an adjacent case.** The gap is never
understanding. It is that a fix lands where it was found and not where the pattern lives.

### Three structural patterns worth more than the individual findings

1. **Built, tested, never registered.** F-02 (validation gates) and F-17 (AI budgets): well-designed
   guards whose precondition the product never creates, with tests that construct the precondition
   themselves. One countermeasure covers both — a startup assertion that every module has a flag row
   *and* a budget row, or the app refuses to boot.
2. **Fixed in the module, not in the class.** F-21, F-14/F-22, U-06/U-09, U-12. When a defect earns a
   §23 entry, the entry should name **every** call site of the pattern and the session should grep
   for them. Four of the eight criticals would not exist.
3. **Check-then-act on money.** F-05, F-13, F-28, F-29 — four races in four modules. All take the
   same fix (a constraint or a row lock), F12 already demonstrates it correctly with
   `uq_sync_account_idempotency`, and **none of it needs an owner decision.**

---

## Suggested order

**Now, no decision required:**

1. **F-01** — one command on the box:
   `docker compose exec api python -c "from app.core.config import get_settings as g; print(repr(g().smtp_host))"`
   Everything about DoD #3 turns on the answer.
2. **F-05, F-13, F-28, F-29** — the four races. One session, one pattern, database-level fixes.
3. **F-07** — a login throttle. Live product, real accounts, single VM, Argon2 as a DoS vector.
4. `KICKOFF-ui-comprehension-fixes.md` — five law violations, none contentious.

**Needs a decision first:**

5. **`S23-PROPOSAL-loading-state.md`** → then `KICKOFF-loading-state-and-fixtures.md`. Closes three
   criticals. Blocked only on the §23 entry, because a skeleton is a §22.2 component pattern.
6. **F-02 + F-12 together** — the gate bypass. Needs the `default_on` versus `enabled` decision, and
   must not be split or M3's detention clock goes silent.

**After the fixtures are gone:**

7. **`WATCH.md`** — three drivers, five tasks. Running it earlier measures a driver's reaction to
   invented data and the stop-point log is unusable.

**Not a session:**

8. **F-08** — Gmail is accepted. Two owner actions remain: separate the dev and production accounts
   (free), and Workspace on `haulmeter.online` for domain-aligned SPF/DKIM/DMARC — which is what
   actually gates A1's validation criterion.

---

## Three questions this audit could not answer

Each is cheap and each blocks something:

1. **What is `SMTP_HOST` on the box?** (F-01) One command.
2. **Does `F2.Facility` carry a timezone column?** (F-14, F-22) If not, that column is the
   prerequisite for both — nights are counted in UTC and "overnight" is measured in UTC, in a US-only
   product spanning four time zones.
3. **Does the Makefile invoke `osm_filter_args.py`?** (F-11) The single-source-of-truth for OSM tags
   exists in Python; the invocation lives in a file no review has ever seen.

---

## Two caveats on the whole thing

**No running system was observed.** Everything marked INFERRED needs one command to settle. Findings
marked OBSERVED are read directly from the dump and should still be re-grepped before a session acts
on them — the standing rule that codebase memory is stale applies to this document too.

**`deploy.sh`, the `Makefile` and `check_ports.sh` are not in the dump** (F-11). `collect_files.py`'s
`EXTENSIONS` tuple has no `.sh` and no extensionless entry, so the script that puts code on the box
and the one enforcing the locked ports have never been reviewed by anyone. **Adding `.sh` to that
tuple is the cheapest fix in either document.**

---

## What was not read

**Backend:** nothing. Every package was read.

**UI:** 200% font-scaling reflow · Android back behaviour (NAV-4) · §20 performance budgets on a
baseline device · focus order and aria labelling · per-surface empty states swept rather than
sampled.

All five are the **physical device pass** — Phase DoD #4, and the oldest open item in the handoff
series. None of them can be done from a dump.

*Absence from these documents is absence of review, not evidence of correctness.*
