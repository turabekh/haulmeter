# HANDOFF-132 — M15 Session A: the foundations, and a constraint that was wrong twice

**Autonomous run.** Plan approval was delegated to counsel for this session per the
kickoff; counsel returned **APPROVED AS WRITTEN**, no cuts, with four binding execution
notes, all four honoured. Nothing was pushed and nothing was deployed — rule 3 stands
even in autonomy.

**The gate cleared first.** `docs/prd-extension-e3-m15-roadside-readiness.md` line 3 reads
*APPROVED — D14 signed by the owner, 16 August 2026, scope (b): Session A only.* Had it
still said DRAFT this file would hold one sentence and nothing else.

---

## 1. What is true now

M15 exists as a module. It ships **OFF**, it cannot reach M14, its twelve tables are on the
dev box, F1 can verify a Telegram payload and issue a guest who can be claimed, F9 has a
speech seam that refuses rather than degrading, and two of E3's quality laws are enforced
in code and proven by sabotage.

**No driver has seen any of it, and no driver surface exists.** Session A is foundations by
E3 §E3.8's own definition, which is also why §22.3's DoD (four states, layout harness,
DRIVE.md) does not appear in this session — those land in Sessions B and C with the
surfaces they describe.

### Commits, in order

| | |
|---|---|
| `a1a01f1` | fold-in: E3 into `docs/`, D14–D20 into the v2.0 §6 registry, PRD §8 amended, decisions 174–177 |
| `619f0b5` | the module exists, ships off, cannot reach M14 (contract 31 → 32) |
| `21d4590` | the schema: 12 tables, migration 0084, and a constraint that was wrong twice |
| `596e8cc` | F1: telegram sign-in and a guest who can be claimed (migration 0085) |
| `cb2f250` | F9: the speech seam refuses when unset; audio spends the same budget |
| `b2ef2cc` | M15: Q-5 holdout integrity and Q-6 the publish path |

### Gates

| gate | at session start | now |
|---|---|---|
| pytest | 2130 | **2195 passed, 0 failed, 0 errors** (+65) |
| vitest | 1020 / 63 files | **1020 / 63 files** (no UI work this session) |
| import-linter | 31 kept, 0 broken | **32 kept, 0 broken** |
| ruff | clean | clean |
| alembic head (dev) | 0083_receivable_kind_fee | **0085_f01_tg_guest** |

All numbers from test-runner's raw report, not from memory.

Layout harness was **not run** — it needs the UI dev server and no UI file was touched.

**The vitest run reports one unhandled error, and it is NOT from this session.** It is
`FleetWorkspaceSurface.vue:266` — `Cannot read properties of undefined (reading 'length')`
on `holds.holds` — and it was present in the baseline measured at the start of this session,
before any M15 file existed. It is TRAPS §2 entry 16's fixture in a different costume: the
tests pass because none of them read the value. Left untouched deliberately, since editing a
surface outside the slice that exposed it makes a diff unreviewable — the same reasoning
HANDOFF-131 §6 applied to the food-decide test.

---

## 2. The thing worth reading if you read nothing else

E3 §E3.1.4 states a rule: *one entitlement per subject × kind × window*. Written literally
that is one `UniqueConstraint` over both subject columns, and **it enforces nothing.** A
subject is an account OR an org, so one of those columns is always NULL, Postgres treats
NULLs as distinct in a unique index, and two identical grants both insert. A red-first test
caught it.

The fix was still wrong. Splitting into two partial indexes by subject cured
`subject_org_id` and left `ends_at` doing the identical thing one column over — an
open-ended grant has no end date. **The suite went green and a live database still accepted
the duplicate**, because the test happened to set an end date. Probing the box is what
found it, which is this project's own rule about the exit line one layer further down.

Now `NULLS NOT DISTINCT` on both indexes plus a CHECK that a row has exactly one subject,
proven by inserting a duplicate on the box rather than by reading the index definition.

**TRAPS gains 4a**, and the general form is worth more than the instance: *every nullable
column in a unique index is a hole, and the test that finds it is the one using the
defaults a caller actually passes.*

Two smaller instances of the same discipline: counsel reported the E3 document was already
tracked (it was untracked — committing it was real work), and scout's contract advice named
the module `m15_recovery` and suggested the conventional pattern E3 explicitly overrides.
**Subagent reports were verified against the tree before being acted on, and two of three
needed correcting.**

---

## 3. Decisions logged (174–177)

- **174** — D14 SIGNED scope (b), with its one named reversal recorded as a reversal: v2.0
  §4 superseded **FOR M15 ONLY**, on arguments stated on their own terms rather than
  borrowed from D8. Every other module stays bound by §4.
- **175** — D16, D17, D20 confirmed at their E3 §E3.7 defaults.
- **176** — D15, D18, D19 remain OPEN; this session builds toward none of them. Records
  that `entitlement.source: admin | stripe` is a **label, not a code path**, so a later
  session does not mistake the enum member for authorization.
- **177** — **PROPOSED, NOT APPROVED.** P-1 `readiness_reminder` and P-2 `readiness_invite`
  logged with their full field-by-field specs and **registered nowhere in code**. A new
  notification class is a §22.2 never-improvise category; entry 118's delegation does not
  cover it and neither does counsel's. Entry 169 is the precedent — the owner signed that
  class before any code existed. P-3/P-4 deferred to their surfaces in Sessions B/C.

**PRD §9 is NOT amended.** The three-tier law drafted in E3 §E3.5 is D15, and D15 is open.

---

## 4. Named remainders — individually, because a generic list hides them

These are **not gaps**; Session A is key-tolerant by design (E3 §E3.8). Each is a live
action that could not be taken without a credential or a person.

1. **Live Telegram bot smoke.** The Login Widget and Mini App validators are proven against
   independently-constructed fixture vectors, including that a vector valid for one path is
   rejected by the other. **No payload from a real bot has ever been verified.** Needs
   `TELEGRAM_BOT_TOKEN`.
2. **Live Deepgram/STT smoke.** The adapter refuses without a key and names its own
   remainder when reached with one. **No audio has ever been transcribed.** Needs
   `DEEPGRAM_API_KEY`, and per E3 §E3.4.1 the vendor decision itself waits on an
   accented-English benchmark built from *pilot* sessions.
3. **Live TTS synthesis of scenario-1 audio.** No officer or coach line has ever been
   synthesized. Needs `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION`.
4. **Azure Uzbek-voice native spot-check.** E3 §E3.4.2 requires a native ear on
   `uz-UZ-SardorNeural` / `MadinaNeural` **before any driver hears them**. This is a person,
   not a key.

---

## 5. What Session A did NOT reach

Stated plainly rather than folded into the remainders above, because these are build items
that a Session-B kickoff must either carry or explicitly drop:

- **F6 audio support** — audio MIME types, HTTP Range serving, and the 30-day
  driver-deletable TTL class (E3 §E3.4.3). The census confirmed all three are net-new:
  `serve_media` returns full content unconditionally with no `Accept-Ranges`, and document
  expiry is credential-shaped with no general object TTL. The schema is ready for it —
  `turn.audio_ref` is the single column raw driver audio is reachable from, deliberately, so
  a deletion sweep has one place to look.
- **F9 classify prompt + eval fixtures** for M15.
- **The `tg` catalogue draft** (E3 §E3.3) — see the owner question below.
- **DEV_SEED scenario** as a committed fixture. The end-to-end path *was* observed (§6), but
  against rows a probe created rather than a seeded scenario.
- **Scenario engine beyond the holdout generators** — `scenario_version` hidden state and
  the holdout/teachable generators exist; deterministic slot validation and the rubric seam
  do not.

---

## 6. Observed on the dev box, not asserted from green

E3's Session-A DoD names one end-to-end observation. It was run and then **queried
independently of the code that wrote it**:

- a guest principal started a session, two turns were recorded against **draft** content
  (Q-6: draft has no path to a driver, and the engine is exercised anyway);
- the guest was claimed into an account;
- the query showed: session attached to the account, `guest_token` **deliberately kept** as
  the trail back (Q-10 — "where did my practice go?" is answerable from the rows), both
  transcripts intact, and the F1 principal claimed exactly once, within TTL.

Also proven by query rather than by an exit line: alembic head, 12 tables, 7 enum types,
both entitlement indexes carrying `NULLS NOT DISTINCT`, and **zero voiceprint columns** —
the single `%voice%` match is `phrase_variant.voice`, which names which of the two officer
voices synthesized *our* line. `turn`, which holds driver audio, has no such column.

**Every guard added this session was sabotaged and watched to fail**: the m14 import
contract (caught the `.public` edge specifically), the flag's `default_on`, the guest claim,
the two Telegram secret derivations, the speech fallback, and both quality laws — 11 tests
red across Q-5 and Q-6 alone.

---

## 7. Owner questions — nothing here may be answered by a session

1. **P-1 / P-2 notification classes.** Entry 177 carries the full specs. Nothing in M15
   sends a notification until these are signed, and the module is built so that costs
   nothing — no class registered, no call site.
2. **D15** (§9 three-tier amendment), **D18** (neutral-brand surface), **D19**
   (`m15_assessment` criteria) remain OPEN. D19's counsel criterion can share the D13
   engagement — one transportation-counsel touch scopes M14 carrier-name invoicing and M15
   assessment exposure together.
3. **Tajik native review — commissioning and budget, and it carries a schedule risk.** In
   E3 §E3.8's own words: *"a named schedule risk: the seven-locale gate blocks flag-ON if
   review lags."* The catalogue draft was not generated this session; when it is, it lands
   **outside** the CI-enforced locale path, because merging unreviewed machine translation
   is the audit's named anti-pattern.
4. **The band vocabulary.** `session.band` and `review_sample.ai_band/human_band` are
   **String, not an enum**, because E3 never enumerates the bands and what we tell a driver
   they *are* is a product judgment. Freezing an invented vocabulary into a Postgres type is
   how a later session inherits a set nobody chose. Name them and they become an enum.
5. **Should `m15_roadside` carry F13 validation gates?** E3 §E3.1.9 lists the conditions for
   turning it on — seven locales passing among them — but §E3.1.8 does not name them as
   gates. None were registered: inventing operator state a governing document did not ask
   for is a habit this codebase has paid for. M14 has gates for D13, so the precedent exists
   if you want it.
6. **Carried from earlier in this session, unrelated to M15:** Mailpit is still running on
   the **production** box (`Up 2 weeks`) and still defaulted in `config.py:78`, contradicting
   CLAUDE.md's LIVE-FIRE law; and a readiness check incremented `opened_count` 0→1 on a real
   share token (`-B714WbOv…`) — harmless by design (F4-1: a link open is not evidence of who
   opened it) but resettable on request.

---

## 8. What to do first on return

1. **The pilot day still outranks all of this.** `docs/validation/j1-journey.md` has seven
   open lines and M15 does not touch any of them.
2. If M15 continues: **Session B needs its own kickoff against D14** — scope (b) authorized
   Session A only. The honest first item is F6 audio, because the WS session loop cannot be
   built on a media layer that cannot serve a range request.
3. **Do not read §5 as a to-do list without re-grepping.** This session's own lesson is
   §2's: the document states a rule, and the database decides whether the rule is enforced.

---

## 9. Operating it

Unchanged from HANDOFF-131 §8. One addition: `m15` is in **both** `MODEL_MODULES`
(`api/db_registry.py`) and `SCHEMAS` (`api/tests/conftest.py`). They are siblings and both
are load-bearing — `create_all` will not invent a schema, so omitting the second fails at
`CREATE TYPE` before any table, and omitting the first fails remotely in unrelated suites
while hiding from m15's own.
