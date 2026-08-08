# OPEN-FINDINGS — the live defect queue

The 45 findings of AUDIT-2026-08-07, with status. **CLAUDE.md points every session here.**
Update the status column when you close one; the audit documents themselves are a dated
record and are never edited.

**Created 2026-08-08 (session 119).** It did not exist before then, though CLAUDE.md and
`AUDIT-INDEX.md` both referenced it.

Two other files the index lists as living in `docs/audits/` are real but elsewhere —
**`WATCH.md` is at `docs/WATCH.md`** and **`split_dump.py` is at the repo root.** The two
kickoff briefs in `docs/kickoffs/` do exist. `S23-PROPOSAL-loading-state.md` was missing
for most of session 119 and **now exists**, supplied by the owner and verified against the
tree — it is **PROPOSED, not approved**, so the three criticals it gates are still blocked.

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
| High | 2 | 0 | 0 | 15 | 0 | **17** |
| Medium | 3 | 0 | 2 | 7 | 0 | **12** |
| Low | 1 | 0 | 0 | 6 | 0 | **7** |
| Accepted | — | — | — | — | 1 | **1** |
| **Total** | **7** | **4** | **2** | **31** | **1** | **45** |

Findings opened *after* the audit are not in this scoreboard — they were never among the
45. See **Opened after the audit**, below.

**Session 119 closed nineteen** — F-03, F-04, F-05, F-06, F-07, F-13, F-14, F-17, F-18, F-21,
F-22, F-23, F-28, F-29, F-31, U-01, U-02, U-07, U-08 —
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
| F-03 | High | **CLOSED** | The ref is the message's real RFC 5322 Message-ID — unique, and findable in a mail provider's trace. Session 119. |
| F-04 | High | **CLOSED** | `_LazyCounterpartyGateway` is tested. Confirmed rather than asserted: against the restored F-03 defect the new test fails while the direct-construction one passes. Session 119. |
| F-05 | High | **CLOSED** | Ledger not idempotent → `uq_journal_entry_type_ref`, partial unique on `(entry_type, external_ref)`. Session 119. |
| F-06 | High | **CLOSED** | `sent_at` NULL means it did not go out; a 5-min worker sweep retries transient failures, bounded, and never retries auth errors. `to_ref` recorded — the DB had no record of the recipient at all. Session 119. |
| F-07 | High | **CLOSED** | Throttled per identifier (5) and per IP (20) in a sliding 15-min window, in Postgres so it fails closed, checked BEFORE the hash runs; `VERIFY_SLOTS` caps concurrent Argon2 so a flood cannot starve the threadpool. Session 119. |
| F-08 | — | **ACCEPTED** | Gmail as counterparty transport (owner decision, 2026-08-07). Two owner actions remain, neither a session: split dev from production, and Workspace on the domain for aligned SPF/DKIM/DMARC. |
| F-09 | Medium | **CLOSED** | A daily unflagged `location_retention` worker job calls the purge that already existed. **The window is an F13 key** (`f03.ping_retention_days`, declared at boot so `/admin/config` shows it), not a constant — how long the product keeps a driver's movements is policy, and PRD §7.3 says "configurable retention". Default **365 days**, conservative by default-choosing rather than by necessity — **checked before wiring: a purge here cannot destroy a claim's evidence.** `render.py` states the rule ("the trace is drawn from EVIDENCE, not from raw location pings"), so every plotted point is a hash-chained F4 record, and `build_trace` — the one function that reads raw pings — has no caller outside its own test. This is a privacy-and-growth control, not evidence retention, and shortening the window is safe. **0 or less means never purge** — this is the only job in the worker that destroys data and the plausible operator accident is typing 0 meaning "off", which read as a cutoff would delete the whole table. Verified on a real worker boot: `location_retention ok: {'deleted': 0, 'retention_days': 365, 'purged': True}`. Session 120. |
| F-10 | Medium | **CLOSED** | `f14.job_schedule` (migration **0065**) — the claim is an `UPDATE … WHERE due AND unleased`, so Postgres serialises the two racing workers and the loser's rowcount is 0. **Not an advisory lock, deliberately:** a session-level lock lives on a CONNECTION and every `db.commit()` in `_run_job` returns that connection to the pool, which would drop the lock mid-run. A **lease** (2× interval, floor 300 s) makes a crashed worker recoverable without a human; the floor exists because `detention_clock`'s interval is 60 s and a job slower than its own interval would otherwise be handed to a second worker. `next_run_at` and the failure streak persist, closing the second half — **verified on the box: the first boot ran all seven jobs (empty table, correct), the second restart ran only `detention_clock`, which was genuinely due.** Previously every restart refired everything. Session 120. |
| F-11 | Medium | **CLOSED** | `.sh` added to `EXTENSIONS`, plus a `FILENAMES` tuple for the extensionless ones (`Makefile`, `Dockerfile`, `Caddyfile`). **Measured: 11 infra files now collected** that never were — `deploy.sh`, `check_ports.sh`, `backup_db.sh`, `verify_restore.sh`, `ingest_remote.sh`, the `Makefile` and four Dockerfiles. No new secret exposure: `.env.example` matches, `.env` does not. 118 §4 ruled this file "not ours to commit or delete"; this edit is additive and was the owner's call. Session 120. |
| F-12 | Medium | OPEN | Module gate and worker disagree on flag polarity. Ships with F-02. |
| F-13 | Critical | **CLOSED** | Double-booking race posting money twice → `ex_booking_no_overlap` EXCLUDE constraint, and `book()` claims the row before any money moves. Session 119. |
| F-14 | High | **CLOSED** | Nights counted in the lot's local calendar. Session 119. |
| F-15 | Medium | **CLOSED** | Both are one `WHERE` clause from bounded and now are. `_overlaps` became a `SELECT … LIMIT 1` filtered on the time range and state — it was loading every booking a spot ever took, with `bookable_summary` calling it once per spot (an N+1 on a full scan). `visit_window`'s Python skip became the `WHERE`, with `LIMIT 1`. **The pre-check narrowing cannot reopen F-13's race** — `ex_booking_no_overlap` is what prevents a double booking, not this read. Tested by counting statements, not timing: a full scan is correctness-neutral, so the only thing that can fail is how much the database was asked for. Session 120. |
| F-16 | Low | **CLOSED** | `_content_disposition` with an **allowlist** ASCII fallback plus `filename*=UTF-8''`. Stripping `"` and `\` is the obvious fix and is **not enough** — `;` separates parameters, so `evil; attachment; filename=x.exe` survives quote-stripping and still injects; the first version of this fix shipped that hole and the test caught it. The extended form is what makes it a fix rather than an escape: RFC 6266 quoted-string is ASCII and this product ships in six locales, so a Cyrillic filename was already arriving mangled. Session 120. |
| F-17 | High | **CLOSED** | Every module seeded a cap at boot, and a module with no row falls back to the compiled default — there is no uncapped state, and no state where a missing row is an outage. `test_module_flags` asserts the invariant. Session 119. |
| F-18 | Medium | **CLOSED** | Calendar-month cap; the column is `monthly_budget_micros` so it cannot be misread. Had to ship WITH F-17 — seeding budgets against a lifetime sum would have made each module go permanently dark. Composite `(module, created_at)` index. Session 119. |
| F-19 | Medium | OPEN | No merge-review queue. Already known. |
| F-20 | Low | **CLOSED** | The amendment said "geohash-7 blocking"; the code has never done that — `find_duplicate_candidates` blocks on distance (`DEDUP_RADIUS_M = 60.0`) and `Facility.geohash` is stored, indexed and unread by it. Corrected in place with a dated note saying what it used to claim, because the governing document is what a future session plans against. The 0.4 similarity figure was right. Session 120. |
| F-21 | Critical | **CLOSED** | §23 entry 73's defect in M4 → `_arrival_departure` routed through `location.visit_window`, anchored on the stop's appointment. M4 was the last unscoped `list_events` caller, so the class is closed. Session 119. |
| F-22 | High | **CLOSED** | "Overnight" measured in the dock's local calendar — this was REFUSING real layover claims. Session 119. |
| F-23 | High | **CLOSED** | `owed` is scoped to the settlement's own pay period. **Named limitation:** it scopes by the receivable's creation date as a proxy, because there is no settlement→load link — work in the period whose receivable is filed later still falls outside. The link is the audit's own deeper fix and is a schema change. Session 119. |
| F-24 | Low | **CLOSED** | Migration downgrades — 57 of 59 real, 2 empty. Closed by F-31, which identified the two; not by session 119. |
| F-25 | Medium | OPEN | The profit model assumes the product does not work. |
| F-26 | Low | **CLOSED** | `rpm_after_cents` is `int | None`; no loaded miles yields `None` with `basis["rpm"] == "no_loaded_miles"` rather than a real-looking rate of $0.00/mi. Absence dressed as a result is the §11.7 failure this codebase treats as non-negotiable everywhere else. Session 120. |
| F-27 | Low | OPEN | Fleet rollups are N+1 per member. |
| F-28 | High | **CLOSED** | Points can be spent twice → `lock_account` row lock taken before the balance is read; `book_with_points` books before it redeems. Session 119. |
| F-29 | Medium | **CLOSED** | The daily cap could be turned off by a pricing knob → every contribution is logged, `points > 0` gates only the ledger issue. Session 119. |
| F-30 | High | **CLOSED** | Per-locale vocabulary for all six launch languages, English always in scope (M11-FR6 mixed-language; F15's glossary is the authority). **The root was deeper than the audit's "English-only":** matching was raw `term in utterance`, so `"I am in Las Vegas"` routed to fuel and `"my sleeper berth heater is broken"` to sleep — adding five languages on top of that would have multiplied the bug by six. Token-phrase matching with explicit `*` prefixes for Russian/Uzbek morphology, `casefold` + Latin-only diacritic folding (Gurmukhi vowel signs are meaning, not decoration), and specificity scoring replacing first-match-wins. `/voice/ask` accepted **no locale at all** and now resolves the driver's F15 locale. Accuracy is asserted **per language**, 16 fixtures × 6. Session 120. |
| F-31 | Low | **CLOSED** | The two empty downgrades identified — `0033_f01_vendor_role` and `0058_a01_checklist_doc_types`, both adding enum values Postgres cannot drop. Each now carries an AI-CONTEXT line saying the `pass` is deliberate, which was the finding's whole ask. Session 119. |
| F-32 | Medium | **CLOSED** | `_parse_ts` returns `None` instead of `now()`, and `has_usable_reading` drops a reading whose AGE is unknown — freshness is half of what §11.7 puts on the pin, so a known availability with an unknown age is not half a belief, it is a fabricated one. **Measured against the live feed before and after: 51 records, 0 without a timeStamp**, so it costs nothing today — which is the audit's own "narrow in practice", confirmed rather than assumed. It matters for A9's eight further publishers whose payload conformance is unknown. Session 120. |
| F-33 | Low | **CLOSED** | The "conservative" `return "some"` raises `ValueError` naming `has_usable_reading()`. "Some" is a positive claim that spots exist, derived from no reading; the honest answer is no belief, which the gate already produces, so the only route here is a caller that skipped the gate — a bug, and it fails loud (the `ChainLocatorAdapter` precedent). Closed **with F-32**: same file, same class, and the findings doc's own instruction is to grep for the rest of the class. Session 120. |

## UI — 12 findings

| ID | Severity | Status | One line |
|---|---|---|---|
| U-01 | High | **CLOSED** | Map drew outside the token system → `--on-accent` composition plus new `--shadow-pin`/`--scrim` (§23 entry 130), and a `token-discipline` sweep that keeps literals out. **Opened a new finding:** white on `--marker-500` is 2.04:1 in dark theme — see §Blockers. Session 119. |
| U-02 | High | **CLOSED** | Per-driver keys moved under `CACHE_PREFIX`, plus a third instance the audit missed (`vendor_appearances`) and the in-memory refs that outlived logout. Asserted on what driver B renders. Session 119. |
| U-03 | High | **CLOSED** | 119 made the fallback loud (counted, warned in dev, per-locale counts at `/dev`) and measured **0** — narrow, because mocked data left the ~45 dynamic families unrendered. 120 closed the other half with the audit's *stronger* fix: `test_dynamic_key_families.py` enumerates the vocabulary **in Python** and asserts a label exists in all six locales. **It found four families broken — 13 keys missing from ALL SIX, including every one of the nine `facility.type.*`.** `resolve()` returns the raw key when a string is missing everywhere, so `money.state.acknowledged` was rendering as literal text on the Money tab **for every driver, in every language** — the JS parity test cannot see this, because six identical holes are perfect parity. Session 120. |
| U-04 | Medium | **PARTIAL** | **Five of the seven registered** — ClaimSurface in three states (invoice / evidence-only / no-claim), AuditSurface, FuelSurface, BookingSurface, PublicScorecardSurface. Harness **229 → 257 checks**. **Registering them found three real defects on screens nothing had ever measured:** `ClaimSurface`'s back button was **40 dp — the ONLY one of the nine `.back` buttons in `surfaces/` that was**, and it is the screen every detention notification deep-links to; `FuelSurface`'s price row ran to **378 px at 200%**; the scorecard's search input to **468 px**, because a flex item's default `min-width: auto` will not let an `<input>` shrink. All three fixed with existing patterns. **The two remaining are BLOCKED, not skipped:** `FleetWorkspaceSurface` and `OwnerPortalSurface` carry the 40 dp controls that are §5.1 item 3's open owner decision — adding them would either fail CI or decide that question by writing CSS. Session 120. |
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

## Opened after the audit

Not part of the 45, and deliberately **not** folded into the finding that surfaced them.

| ID | Severity | Status | One line |
|---|---|---|---|
| N-01 | High | **CLOSED** | Every spoken string comes from F15's `MessageCatalog`, keyed by the driver's locale, with each handoff intent carrying its own key rather than interpolating an English slug into a Spanish sentence. **A missing ROW falls back to compiled English** (F-17's third option — a strict lookup would turn one missing row into a silent copilot at speed); a missing KEY raises and is gated in CI, so a new intent cannot reach a truck mute. Money stays `$` and units imperial in every locale per F15. **114 rows across 19 keys seeded at boot on the real box**, and verified over HTTP: Spanish in → Spanish out, Russian while driving → Russian deferred confirmation with `audio_ref: audio://ru/…`. Session 120. |
| N-02 | High | **CLOSED** | Nine of the ten `notify.dispatch` sites take their title and body from F15's catalogue, keyed by the driver's locale. **The lookup lives in F8** (`localized_text`) because F8 is what already knows the account — ten call sites resolving a locale ten times is ten chances to resolve it differently, and the one that forgot would be invisible. **366 catalogue rows across 61 keys seeded at boot** on the real box. The tenth site is deliberate: `promotions.py` sends the vendor's OWN words as the body, which is data, not product copy. Session 120. |

**N-01 in full.** `m11_voice/domain/service.py::_dispatch` returns hardcoded English:
`"You have {pts} points."`, `"You're all paid up — nothing owed right now."`, `"I didn't
catch that — try 'parking ahead' or 'what am I owed'."` So a Russian driver's utterance
now classifies correctly and is **answered in English** — and while driving that answer is
spoken aloud (`_maybe_tts`), which is the one moment the driver cannot fall back to reading
the screen. PRD §7.15's coverage rule names voice explicitly: *"every driver-facing surface
— UI, notifications (F8), voice (M11 via F9 STT/TTS), and help content — renders in the
user's language."*

**Why it was not fixed with F-30.** F-30 is the classifier; this is the response path, and
the two share nothing but a module. The fix needs F15 `MessageCatalog` rows for roughly ten
spoken strings across six locales — `register_message` / `get_message` / `is_complete`
already exist and `missing_locales` already gives it a CI gate, so the mechanism is built;
what is missing is the strings and the wiring. That is a session, not a patch, and folding
it into F-30 would have hidden a second defect inside the first one's commit.

**Closed in session 120.** It was also F15's message catalogue's **first producer in the
product** — `register_message` had been written, exported and called by nothing but F15's
own test, the same built-and-inert shape as F-09's purge and F9's budget cap.

**N-02 in full — the rest of the class, measured rather than assumed.** Closing N-01 meant
grepping for the pattern, and it was much wider than voice: **10 `notify.dispatch` sites
across 7 modules** (m01, m03 ×2, m05 ×2, m06, m09, m13 ×3) passed English literal titles and
bodies straight to a driver's push notification. M3's `detention_clock` P0 — *"Detention
started · $75/hr"*, *"Free time is used up at this stop. Notice ready to send."* — is the
product's most important driver-facing alert and it was English-only.

**Closed in session 120, and two things in it are worth carrying forward.**

**The interpolated LABELS were the real trap.** `Missing: {labels}` and `{label} expires in
{offset} days` splice an enumerable English noun into the sentence, so translating only the
sentence yields *"Falta: pickup photos"* — an English fragment inside a Spanish alert, the
same defect N-01 fixed in the voice handoffs. **The first sabotage pass did not catch it:**
replacing the localized labels with raw gap kinds passed all 135 tests, because
`notify_protection_gap` had no test at all. It has one now, and the "the facility" fallback
beside it needed a second one.

**What is NOT translated, deliberately.** `promotions.py`'s body is the vendor's own
promotional text and its title is the vendor's name — a person's words, not product copy,
and machine-translating what a cook wrote about their own food would be inventing speech on
their behalf. Facility and vendor names are left alone for the same reason. Money stays `$`
and units imperial in every locale (F15's `UNIT_SYSTEM`).

**Two residues, named rather than hidden:** the document-expiry date renders `%d %b` and the
vendor-published body renders `%a`, so month and weekday abbreviations are still English.
Localizing them needs a per-locale table or a dependency (babel), which is a decision rather
than a fix.

PRD §7.15's coverage rule names notifications in the same breath as voice: *"every
driver-facing surface — UI, notifications (F8), voice (M11 via F9 STT/TTS), and help
content — renders in the user's language."*

**Why it is filed rather than fixed here.** It is the same mechanism N-01 just built and
proved — register at boot, look up by locale, fall back to compiled English — so the
remaining work is roughly 20 strings × 6 locales plus the wiring, and it is mechanical.
Folding it into N-01's commit would have hidden a second, larger defect inside the first
one's fix, which is the thing this queue keeps catching. **Needs no owner decision:**
translations of existing copy are not new copy, so §22.2 is not engaged.

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
   pattern, so it cannot be improvised. The proposal now exists at
   `docs/audits/S23-PROPOSAL-loading-state.md` and is **awaiting the owner's decision on
   three items plus one open question**. Its measurable claims were verified in session
   119; one is materially understated — the fixture deletion is **16 exports across 10
   importers**, not "nine fixtures imported by five surfaces", and three of those
   importers are §18 portals rather than driver surfaces, which the proposal's wording
   does not settle. See the VERIFICATION section appended to it.
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
