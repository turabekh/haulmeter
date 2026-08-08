# HANDOFF-120 — twelve findings closed, and every one that needed no decision from the owner now is

> **Stack UP · thirty-one commits UNPUSHED · nothing deployed.** haulmeter.online still
> serves 112's code.
>
> Session 120 was one instruction — *"read the latest handoff and restart the app"*, then
> *"proceed using your best judgement"* five times over. It restarted the stack and worked
> the audit queue: **twelve findings closed** — the audit's F-30, F-32, F-33, F-09, F-10,
> F-15, F-16, F-20, F-26, F-11, plus **N-01 and N-02**, which this session opened and closed
> itself — and **migration 0065** added.
>
> **Open findings 18 → 8.** What remains is four blocked on facts or decisions nobody here
> can supply, and four that need the owner's judgement about intended behaviour rather than
> code. §5.1 of HANDOFF-119 is still the highest-value thing on the board and is unchanged.
>
> **Three times this session a fix of mine was wrong and the process caught it**, which is
> the part worth reading: §4.

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **thirty-one** commits ahead of `origin/main` — 119's twenty-four plus this session's seven |
| `origin/main` | `113327e`, still **not re-verified**. `git fetch` fails here: *"could not read Username for 'https://github.com'"*. The ahead-count is arithmetic. **Re-fetch before pushing** |
| Gates | **pytest 1523 · vitest 714 (38 files) · layout 229 checks · import-linter 30/30 · ruff clean** — all five measured, layout re-run rather than carried forward |
| Migrations | **`0065_f14_job_schedule` (head)** — new this session, applied AND downgraded AND re-applied on the running stack |
| Working tree | clean |
| Local stack | **UP.** Verified from outside the containers: `/health` 200, UI 200, seven containers, worker booting clean |
| Dev data | Tampa `27.9506,-82.4572` intact, four DEV facilities at 88–125 m |
| Email | **dev still points at live Gmail** (`smtp.gmail.com:587`, `companyhaulmeter@gmail.com`). A send from dev is a real send |
| Deploy | **not run.** The box has none of 113–120 |

**Restarting cost one retry.** The first `make up` failed on a Docker registry timeout
fetching `node:22-slim` metadata (`DeadlineExceeded`) — the api and worker images had
already built and were cancelled only because the ui target failed. Pulling the base image
separately, then re-running, worked first time. Not a code problem; worth knowing because
the error names the Dockerfile and reads like one.

## 2. What was closed

**F-30 — voice understood one of six languages.** The audit filed it as "English-only
substring matching". Both halves were true and **the second was the root**: matching asked
`term in utterance`, so `"I am in Las Vegas"` routed to fuel and `"my sleeper berth heater
is broken"` routed to sleep. Neither is in the audit. Adding five languages on top of
substring matching would have multiplied that bug by six.

`m11_voice/domain/lexicon.py` is new and holds all vocabulary and matching. Token-phrase
matching with explicit `*` prefixes where morphology needs them; `casefold` plus
Latin-**only** diacritic folding; specificity scoring instead of first-match-wins; English
active in every locale per M11-FR6 and F15's glossary. `/voice/ask` accepted **no locale at
all** and resolves the driver's F15 profile locale now.

Accuracy is asserted **per language** — 16 fixtures × 6 locales, all 15 intents in each —
which is what the DoD says and what nothing measured before.

**F-32 + F-33 — the product stating what it does not know.** `_parse_ts` returned
`datetime.now(UTC)` for a missing feed timestamp, so ingest time stood in for reading time
and a driver saw `0m · IDOT` on a reading of unknown age. Under A3 the feed badge makes
that *more* trusted. Returns `None` now and `has_usable_reading` drops it. F-33's
"conservative" `return "some"` — a positive claim that spots exist, derived from no reading
— raises instead. Closed together because OPEN-FINDINGS' own instruction is to grep for the
rest of the class.

**F-09 — pings were never purged.** `purge_pings_older_than` had been written, exported and
tested since F3 and its only caller in the tree was that one test. A daily unflagged
`location_retention` job calls it; the window is an F13 key declared at boot. **0 or less
means never purge** — the only job in the worker that destroys data, and the plausible
operator accident is typing 0 to mean "off".

**F-10 — the worker's schedule was in-process only.** `f14.job_schedule` (0065). The claim
is the `UPDATE` itself, so Postgres serialises the racing workers and the loser's rowcount
is 0. **Not an advisory lock**, and the reason is specific: a session-level advisory lock
lives on a CONNECTION, and every `db.commit()` already inside `_run_job` returns that
connection to the pool — the lock would have been dropped silently mid-run, and a
single-connection test would have passed.

**F-15, F-16, F-20, F-26, F-11** — see the commit `5f781aa` message, and §3 below for the
two that are more interesting than their severity.

**N-01 — the copilot answered in one language whatever it understood.** Opened while
closing F-30 and closed later the same session. Every spoken string comes from F15's
`MessageCatalog` now, keyed by the driver's locale. **It is that catalogue's first producer
in the product**: `register_message` had been written, exported, and called by nothing but
F15's own test — the same built-and-inert shape as F-09's purge and F9's budget cap.

Two fallbacks, deliberately different because the failures are: a missing ROW falls back to
compiled English (F-17's third option — a strict lookup would turn one missing row into a
*silent* copilot at speed), and a missing KEY raises, gated by a test asserting every intent
the router can return has one. A new intent with no message would otherwise be a 500 in a
moving truck.

## 3. Two things that were smaller than their fix

**F-16's obvious fix was wrong.** Stripping `"` and `\` from the filename is what the audit
suggests and what I wrote first, and it **shipped the hole**: `;` separates header
parameters, so `evil"; attachment; filename="pwned.exe` still injected after
quote-stripping. It is an allowlist now.

The test caught it because of how it asserts. It checks the header **parses to three
parts**, not that the hostile text is absent — an absent-substring assertion would have
passed against the broken version, because the text is harmless *inside* the quoted value
and the entire defect is whether it can escape it.

**F-15 is tested by counting statements, not by timing.** A full table scan is
correctness-neutral: every assertion about the ANSWER passes against the defect. The only
thing that can fail is how much the database was asked for, so the tests count the
statements issued and assert `LIMIT` is in them.

Also worth stating because it looks like it might be untrue: narrowing `_overlaps` **cannot
reopen F-13's double-booking race.** `ex_booking_no_overlap` is what prevents it. No Python
read, narrow or wide, can see a row a concurrent transaction has not committed — which is
why the constraint exists.

## 4. Three times a fix of mine was wrong, and what caught it

This is the section to read. None of these were caught by the suite going green.

**1. I built an inert mechanism and removed it.** My first `classify` fell back to scanning
all six locales on a miss. It reads as generous, and it is not: no cross-locale collision
exists in those tables, so the fallback made `locale` **unobservable** — threaded through
the endpoint, the service and the classifier, provable by nothing. Two API tests I had
written to "prove locale threading" passed without the endpoint change at all. That is the
shape of the five built-and-inert engines this codebase keeps paying for, and I was adding
the sixth. Removed; the locale SCOPES, and the tests discriminate.

**2. A sabotage pass exposed a hole in the F-09 fix itself.** Removing the worker job
failed **no test** — F-09's own shape (a purge nothing calls), reproduced inside the fix for
F-09. Session 119 had already written exactly that test for `outbound_retry`; this now
follows it, and both "job removed" and "job flag-gated" fail.

**3. A sabotage pass revealed a test of mine that proved nothing.** Restoring `.lower()` in
place of the fold passed 28 of 28, because my accent test — `"inicia mi reloj de
detención"` — routes on `inicia` and `reloj` and never needed the accent folded. Rewritten
so the accented word is the only signal.

**And a fourth, which was mine and not the code's.** My sabotage script backed up three
different `service.py` files to one path, and the restore wrote M8's code into
`m06_parking/domain/service.py`. The next test run collapsed loudly, git had the committed
state, the change was re-applied and all four sabotages re-run with unique paths. Nothing
was lost — but a quieter collision would have been committed. **Give backup files the
module's name, not the file's.**

## 5. What sabotage said, fix by fix

Every fix was checked by restoring the defect and watching the new test fail.

| Fix | Sabotage result |
|---|---|
| F-30 substring matching | **exactly 1 fails** — all 96 accuracy fixtures pass against the defect |
| F-30 locale ignored | 9 fail |
| F-30 naive `\w` tokenizer | 2 fail |
| F-30 first-match-wins | **exactly 1 fails** |
| F-30 endpoint drops the locale | 2 fail |
| F-30 `.lower()` for casefold | 1 fail *(0 before the test was rewritten — §4)* |
| F-32 `_parse_ts` returns now() | 2 fail |
| F-32 gate ignores age | 2 fail |
| F-33 the conservative "some" | 1 fail |
| F-09 zero-means-delete-everything | 1 fail |
| F-09 job removed from the worker | 1 fail *(0 before the wiring test — §4)* |
| F-09 job present but flag-gated | 1 fail |
| F-10 claim ignores an existing lease | 2 fail, including the two-connection race |
| F-10 lease floor removed | 1 fail |
| F-10 `ensure` rewinds an existing row | 1 fail |
| F-15 `_overlaps` rescans | 1 fail |
| F-15 `visit_window` unbounded | 1 fail |
| F-16 filename interpolated raw | 2 fail |
| F-26 rpm falls back to 0 | 1 fail |
| N-01 `_dispatch` ignores the locale | 2 fail |
| N-01 deferred string back to a literal | 1 fail |
| N-01 one locale dropped from a message | 1 fail |
| N-01 handoff slug interpolation restored | 1 fail |

**The two "exactly 1" rows carry the same lesson as 119's throttle row.** Substring matching
and rule-order-dependence both pass the entire 96-fixture accuracy set. The accuracy metric
does not prove the matcher; the false-positive tests are the only guard.

## 6. Verified against the running system, not the suite

- **The live TPIMS feed before changing it: 51 records, 0 without a `timeStamp`.** So F-32
  costs nothing today — the audit's own "narrow in practice", confirmed rather than trusted.
  It matters for A9's eight further publishers whose payload conformance is unknown.
- **`location_retention` on a real worker boot:** `{'deleted': 0, 'retention_days': 365,
  'purged': True}` — 0 because the oldest ping on this box is 19 days old.
- **F-10's restart half is only observable on the box.** The first boot ran all seven jobs
  (empty table — correct). The **second restart ran only `detention_clock`**, whose 60 s
  interval was genuinely due; `tpims_static`, `eia_regional`, `document_expiry` and
  `location_retention` stayed put. Before this, all seven fired on every restart.
- **F-11 measured: 11 infra files now enter the dump** that never did — `deploy.sh`,
  `check_ports.sh`, `backup_db.sh`, `verify_restore.sh`, `ingest_remote.sh`, the `Makefile`
  and four Dockerfiles. `.env.example` matches; `.env` does not.
- **N-01 end to end over HTTP**, because boot registration is only observable on the box:
  114 catalogue rows across 19 keys seeded at boot; `es` *"cuanto me deben"* →
  *"Estás al día — no te deben nada ahora."*; `ru` while DRIVING → the deferred confirmation
  in Russian with `audio_ref: audio://ru/…`, which is the case that matters (spoken aloud,
  and the TTS is now asked for Russian audio); English unchanged.
- **F-09's risk was checked before wiring, and it is lower than it looks.** The F4 evidence
  pack does **not** read `location_ping` — `render.py` states the rule and the reason ("the
  trace is drawn from EVIDENCE, not from raw location pings … the map cannot show a position
  the verification block does not cover"), and `build_trace`, the one function that reads
  raw pings, has no caller outside its own test. So a purge cannot destroy a claim's proof:
  this is a privacy-and-growth control, and **365 days is a safe default choice rather than
  a necessity — shortening it is cheap.** An earlier draft of that commit claimed the
  opposite and would have left a later session defending a long window for a false reason.

## 7. Exact next task

### 7.1 The owner decisions — unchanged, and now the whole queue

HANDOFF-119 §5.1's eight decisions are **untouched and still blocking**, and they are now
most of what is left. Nothing in them changed this session. Two of them are §22.2
never-improvise categories and were confirmed against §23 entry 118's carve-outs as **not
delegable** — a new palette colour and a new component pattern still stop and ask, whatever
rule 6 delegates.

**Item 5 is still the best thing to read first**: approving the loading-state proposal
(`docs/audits/S23-PROPOSAL-loading-state.md`, claims already verified) unblocks **U-06,
U-09, U-10, U-11 and U-12 — four criticals and a High — in one session.**

### 7.2 What is left, and why each one stopped

| | |
|---|---|
| **F-02 + F-12** | the `default_on` vs `enabled` decision. Must not be split, or M3's detention clock goes silent |
| **F-19** | no merge-review queue — needs a judgement about intended behaviour, not code |
| **F-25** | the profit model assumes the product does not work — same |
| **F-27** | fleet N+1. Latent (M12 not activated) and it **inherits F-23's `owed` definition**, so fixing the queries without settling that would bake in the wrong number |
| **F-01** | one command on the box. No box credential here |
| **U-04** | six surfaces not in the layout harness — real work, no decision needed |
| **U-06, U-09, U-10, U-11, U-12** | all wait on §7.1 item 5 |


**Nothing un-blocked is left that does not need you.** N-02 was the last of it and closed
the same session it was opened: nine of the ten `notify.dispatch` sites take their text from
F15's catalogue now, and **366 rows across 61 keys** seed at boot. The tenth is deliberate —
`promotions.py` sends a vendor's own words, which are data rather than product copy.

**The remaining engineering that needs no decision is U-04** (six surfaces outside the
layout harness) and **U-03's narrow half** (the i18n sweep never exercised the ~45 dynamic
`t()` key families, which are the strings a non-English driver meets on Map and Money).
Everything else on the board wants an owner decision or a command on the box — §7.1.

### 7.3 Still open and untouched from 118 and 119

The **handset background-sensor test** (v2.0 DoD #8), **ON_SITE has still not been walked in
a browser** (117 §7), and **push, then decide on deploying**. A deploy needs production
`SMTP_*` on the VM.

## 8. Things a later session will trip over

1. **`m11_voice/domain/service.py` no longer classifies anything.** All vocabulary and
   matching live in `lexicon.py`; the service only dispatches. A term added to a group is
   available to every rule referencing that group.
2. **The M11 vocabulary wants a native-speaker pass before M11 activates.** Terms are
   grounded in `ui/src/core/i18n/*` where the catalogues carry the domain noun; verb and
   question forms were authored. The architecture is right and measured per language — the
   BREADTH in es/pa/ru/uz/so is the limitation, it is stated in the file's own docstring,
   and adding a phrase costs no code change.
3. **`derive_parking_status` now RAISES** for a status with no usable reading. Any new
   caller must gate on `has_usable_reading` first, which the one existing caller does.
4. **`DynamicStatus.reported_at` is `datetime | None`.** A test constructing one directly
   must set it, or the record is correctly dropped as unusable.
5. **`ProfitResult.rpm_after_cents` is `int | None`.** A consumer formatting it must handle
   None; `basis["rpm"]` says which case it is.
6. **The worker's schedule is in Postgres.** A new job needs no migration — `_seed_schedule`
   writes its row on first boot — but a job that is renamed leaves its old row behind and
   starts due immediately.
7. **Backup files in a sabotage script must be named for the MODULE, not the file.** §4.

## 9. Restarting

```
make up                              # preflight, then the full stack
make seed-where                      # the Tampa origin — paste into Sensors
make test                            # 1494 pytest + 714 vitest — do NOT pipe it
make lint                            # ruff + import-linter (30 contracts)
make ui-layout                       # 229 checks, ~2.6 min, runs ALONE
make down
```

**Do not run pytest while `make test` is running.** Both use the same database; a
concurrent run produced five phantom failures in `m13_vendor` and `test_impersonation` this
session that all passed in isolation. If the full suite reports failures in files you did
not touch, re-run them alone before believing it.

`infra/.env` carries the live Gmail block and is gitignored. **A send from dev is a real
send** — seeded `@bolt.example` counterparties are safe, that TLD does not resolve. To read
bodies locally: `SMTP_HOST=mailpit`, `SMTP_PORT=1038`, `SMTP_STARTTLS=false`, then recreate
the api container.

**Migration 0065 is new this session** and was applied, downgraded and re-applied on the
running stack. It creates `f14.job_schedule` and **deliberately backfills nothing**: an
empty table means every job is claimable on the next tick, which is exactly today's
behaviour, so the deploy that applies it changes nothing about when jobs run.

Nothing is waiting on a background job, an ingest, or a queue.
