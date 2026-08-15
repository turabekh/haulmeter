# HANDOFF-127 — built became ready to be used by a stranger

> **Stack UP · everything PUSHED · production CURRENT at `0080` · slice 1 is LIVE AND INERT.**
> Two sessions in one document: M14 slice 1 built (steps 0–6), then deployed and staged for
> the pilot. **§23 entries 155–156.** Supersedes `HANDOFF-126.md`, which stays readable for
> the PWA/facility/audit detail.
>
> **AUTONOMOUS SESSION.** The owner waived plan approval for the deploy-and-stage half, so
> **§3 of this document is the accountability record that replaces it** — every judgment
> call with its reasoning. Read that section before trusting anything else here.
>
> ---
>
> **THE PATTERN, and it is the sixth face of the coin.** 122: *built, correct, reached by
> nothing.* 123: *specified, shipped as done, never built.* 124: *correct in one process,
> wrong in another.* 125: *renders in every case except the one it exists for.* 126: *a
> substitute that agrees with another substitute rather than the system.* **127's is the
> one that only appears when you run the thing: A CHECK THAT LOOKS LIKE THE STRONGEST
> AVAILABLE, AND ISN'T.**
>
> | The check | What it looked like | What it was |
> |---|---|---|
> | `make m14-prove`, first run | six pings ingested, sources right, idempotence right | **zero geofence events** — coordinates swapped, truck in the Southern Ocean |
> | M3's evidence-class derivation | wording tested, derivation tested | **the wire between them was not** — a sabotage made every pack `phone_verified` and the suite stayed green |
> | `make m14-onboard`, first run | a clean 401 against a fake key | **"connector marked active"** printed straight after the provider refused us |
> | the parser's position guard | a fixture full of malformed rows | **no row was dropped for a missing position alone** |
>
> **Every one was found by running something, not by reading it.** The kickoff insisted on
> step 4 being an observation rather than a test and was right the first time it ran.
>
> ---
>
> **AND THE THING THAT IS TRUE OF THIS WHOLE MODULE: it is on production and it does
> nothing.** `m14_overlay` has no operator decision, both gates are unsatisfied, `can_send`
> refuses, and the routes 404. That is not an unfinished state — it is the finished state
> of slice 1. What comes next is a fleet, a counsel answer, and evidence-class results.

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **0 ahead / 0 behind `origin/main`** at `3b17a3f` (OBSERVED, fetched) |
| Gates | **pytest 1991 · vitest 962 (57 files) · layout 353 · `make ui-image` · `make ui-pwa` · import-linter 31/31 · ruff clean** |
| Migrations | local **and production** at **`0080_m14_held_claim`** (0078/0079/0080 added) |
| Working tree | clean |
| Stack | **UP** |
| Deploy | **slice 1 LIVE and INERT.** Backup `haulmeter-20260815T054650Z.dump`, offsite, taken first |
| Email | **Gmail in EVERY environment — owner decision, see §2** |

**Session-126 baseline: pytest 1942 / vitest 962 / layout 349.**
Net: **+49 pytest, +4 layout, 3 migrations, +1 import-linter contract.**

### The deploy, verified by querying — never by an exit line

```
alembic_head                      0080_m14_held_claim
f03.source col                    1        f04.evidence_class col   1
m14 tables                        4
pings backfilled 'device'         476 / 476
packs backfilled 'phone_verified'  51 / 51
m14_overlay enabled               NULL — no decision
m14_overlay default_on            false
m14 gates                         legal_signoff=false, carrier_invoicing_counsel=false
held_claim rows                   0        connector rows           0
```

And the refusal itself, run **on the box**:

```
m14_overlay is_enabled : False
can_activate           : False
can_send               : False | blocked by: legal_signoff
```

**Nothing regressed:** 96 detention claims, 15 receivables, 2 settlements, 18,333
facilities, 181 accounts. `/`, `/map`, `/money`, `/load`, `/docs` all 200; manifest and
health fine. The gated `/fleet/{id}/holds` returns **404** — correct, the module is off.

`M14_CONNECTOR_KEY` is on the VM in the `0600 root:root` `.env`, **distinct from dev**
(compared by SHA-256 prefix, never by value: prod `5b2046de…`, dev `982eef1f…`), and
proved by encrypting and decrypting a throwaway connector row that was then deleted.

---

## 2. THE OWNER DECISION THAT MUST NOT BE REVERSED AS A DRIFT

**2026-08-15 — Gmail stays the SMTP target in every environment.** The owner has weighed
this and accepted it. **No session may restore Mailpit, add an environment guard, or change
SMTP configuration as a tidy-up.** A future session finding dev pointed at live Gmail will
be tempted to "fix" it; that would be reversing a decision, not removing a defect.

The corollary is behavioural and binds every session from here:

> **Every environment is live-fire for email.** Any action that could trigger a send —
> approving a claim, exercising a notification path, running a demo — is production-grade
> wherever it runs. Nothing is ever addressed to an inbox the owner does not control.

The slice-1 kickoff's Precondition 3 says production email goes to Mailpit. **That is stale
— F-01 closed in session 124.** The correction is written into
`docs/kickoffs/KICKOFF-m14-slice1-eld-claim.md`.

---

## 3. Judgment calls — the record that replaces plan approval

Six calls, each with the reasoning that produced it.

**1 — The pilot path is a CLI, not a Fleet Workspace surface.** A mapping screen needs a
two-column picker (provider vehicles against driver accounts, bound in pairs) and no such
component exists. §22.2 does not let a session invent a component pattern, and the kickoff
named the tell: *"If the surface would need a pattern that doesn't exist, that's the signal
to ship the CLI instead."* The operational argument agrees — on a call the owner is already
on the box, and a portal flow stalling on a 403 mid-call is the worst outcome available.

**2 — The provider key is encrypted at rest (AES-GCM), not stored in the clear.** The
kickoff put it in a column and said a better home is a handoff note rather than an
improvisation, so it was asked and the owner chose encryption. What settled it was not the
public repo — a key was never going to be committed — it was `scripts/backup_db.sh`: this
database is dumped nightly offsite and A12 made that upload REQUIRED, so a plaintext column
ships a working credential to somebody else's telematics into a bucket every night.
**An unset secret REFUSES rather than falling back to plaintext**, because a silent fallback
is how a security control becomes decorative (audit F-02's shape).

**3 — `httpx` moved from `[dev]` to runtime dependencies.** Found while building the
poller: the worker schedules `tpims_dynamic` every 180 s and it does `import httpx` inside
the function, so **scheduled production jobs already depended on a dev-only declaration**
and worked only because the Dockerfile installs `.[dev]`. An ordinary hardening step —
stop shipping dev extras — would have silently killed the parking feed. Zero image change.

**4 — `approved` and `sent` are separate hold states.** Collapsing them is F-01 exactly:
F8 wrote `sent_at` for notices that reached a container and everything downstream believed
them. A fleet admin approving while D13 is unanswered has genuinely approved, and the claim
has genuinely not gone anywhere; `send_blocked_by` names the gate so the screen can say why.

**5 — The validation refuses circularity in code, not in a comment.** E2-FR2 asks for
agreement with *the facility's gate reality*. A ground truth sourced from the provider
proves only that the poller copies faithfully — which unit tests already cover — so a
`source` naming Motive/ELD/telematics **raises**. A rule left in a docstring is forgotten
at 11pm on a pilot call.

**6 — `/v1/vehicles` ships with a fallback rather than a guess.** Its 200 response shape is
the one thing in the module never exercised against the real provider. The onboarding
script falls back to `/v3/vehicle_locations` — the endpoint the poller is known to work
against — if it fails or returns nothing, and the validation log records the gap.

**Deliberately NOT done** (hard stops respected): no gate satisfied, altered or worked
around; no D-series decision written; nothing sent anywhere; no slice-2 work; no new
tokens, components, navigation or notification classes; no secret in the tree; no
destructive operation on production data.

---

## 4. The pilot, in the owner's hands

### `make m14-onboard FLEET=<uuid>` — five steps, ≤15 minutes

Walkthrough against a deliberately **fake** key, which is what a fumbled call looks like:

```
STEP 1 of 5 — paste the fleet's Motive API key
  stored, encrypted. Key is ****0000 from here on.

STEP 2 of 5 — ask Motive which vehicles this key can see
  /v1/vehicles failed: 401 Unauthorized for https://api.gomotive.com/v1/vehicles
  falling back to the endpoint the POLLER is known to work against
  REFUSED by the provider: 401 Unauthorized for .../v3/vehicle_locations
  connector marked failing; the key (****0000) may be wrong, revoked, or lack
  the fleet scope. Nothing else to do here.
```

**First contact with the real provider, and it is good news:** `api.gomotive.com` answered
both paths with a genuine 401, so base URL, paths, TLS and the auth header all work.

The happy path, proved with a fake provider (steps 3–5 the 401 never reaches):

```
STEP 1  connector stored, key ****7788
STEP 2  vehicles: ['veh-77']
STEP 3  veh-77 -> pilot@example.com
STEP 4  imported 3, events ['ENTER', 'DWELL_TICK']
        drafted 1 HELD claim(s), class=eld_derived
STEP 5  overlay ON: False | may send: False (blocked: legal_signoff)
```

### `make m14-validate FLEET=<uuid> [FILE=gt.csv]` — the ±3 min check

```
| stop | source | arrival Δ | departure Δ | within ±3 min |
|---|---|---|---|---|
| `a1b2c3d4` | facility gate log | 1.0 min | 2.0 min | yes |
| `a1b2c3d4` | receiver's signed sheet | 3.0 min | 1.0 min | yes |
| `a1b2c3d4` | driver's own word (weakest) | 4.0 min | 0.0 min | **NO** |
| `a1b2c3d4` | facility gate log | — | — | unmeasurable |

**3 of 4 measured stops within ±3 min** · 1 unmeasurable · 3/10 toward the target.
> 1 stop(s) produced no ELD arrival at all. That is usually an unmapped vehicle
  rather than a bad geofence — check the mapping before reading anything into it.
> 1 stop(s) rest on the driver's own word, which is the weakest of the three
  sources. Named here rather than averaged in silently.
```

And the refusal that is the point of the `source` field:

```
source='motive'  -> REFUSED: source 'motive' is the provider being validated —
                    Motive validating Motive proves only that the poller copies…
source='the ELD' -> REFUSED: …
```

---

## 5. Exact next task

### Three things need the owner and none is code

**1. D13 — the counsel touch.** Fleet-originated claims invoice in the **carrier's** name,
a different posture from v1.0 §13's driver-name billing agent. `carrier_invoicing_counsel`
is unsatisfied and so is M3's inherited `legal_signoff`; `can_send` refuses on both. **One
engagement clears both**, and until then a fleet admin's approval records a decision and
sends nothing. This is the only thing between slice 1 and its headline validation.

**2. A pilot fleet.** A community carrier on Motive whose admin will paste a key on a call.
Everything else is ready: `make m14-onboard`, then `make m14-validate` once they have run
stops. Concierge by design — build nothing you can fake with a pasted key.

**3. The handset background-sensor test — deferred TWELVE times now.** v2.0 DoD #8, named
as next since session 115. **It rides along on the pilot visit**: the same trip that proves
the ELD path can watch the phone path, and entry 138's arrival record — device fix,
accuracy, distance — has still never been produced by a real phone. M14 routes *around*
this rather than closing it, which was the right call for a paying outcome and leaves the
sensor exactly as unproven as it was.

### Then, what the evidence chooses

**Slice 2 is not chosen by momentum.** E2's whole bet is recovery rate *by evidence class*:
if brokers pay `eld_derived` claims nearly as often as `phone_verified` ones, the fleet tier
scales without the sensor; where they dispute, phone capture is the documented answer. That
answer comes from claims flowing, not from a plan. `docs/validation/m14-slice1.md` is the
living record.

Also open and unrelated: **`--marker-500` at 2.04:1 in dark** (a §22.2 palette colour,
needs the owner's replacement value, open since **119**), and the **140 production records
with no bytes** (leave / purge / tell the drivers, open since **124**).

---

## 6. Things a later session will trip over

1. **`m14_overlay` IS OFF ON PRODUCTION AND THAT IS THE FINISHED STATE.** No `default_on`,
   NULL decision, both gates unsatisfied. Do not "finish" it by enabling it — that is an
   operator decision gated on D13.
2. **THE PROVIDER'S 200 RESPONSE SHAPE IS UNVERIFIED.** 401s prove reachability, nothing
   more. `/v1/vehicles` especially: it has never seen a real success. `make m14-poll-once`
   and `make m14-onboard` are where a human proves it.
3. **A GROUND TRUTH NAMING THE PROVIDER IS REFUSED.** Not a lint, an exception. If a
   validation run will not accept a source, that is the check working.
4. **`m14` MUST BE IN `MODEL_MODULES`** (`api/db_registry.py`). It is what `Base.metadata`
   is built from, so alembic autogenerate and the test harness both read it. Omitting it
   fails REMOTELY: `cannot drop table f01.account`, every test in unrelated suites erroring
   at fixture setup. It hid because collecting m14's own test file imports the models.
5. **A BARE `sa.Enum` INSIDE `create_table` EMITS ITS OWN CREATE TYPE.** Create it
   explicitly, then reference with `postgresql.ENUM(..., create_type=False)` — migration
   0057 wrote this down and 0079 re-learned it. **How it fails is the lesson:** alembic
   printed "Running upgrade" for BOTH 0078 and 0079 and rolled the whole transaction back,
   so the log said two migrations ran and the database had neither.
6. **`f02.coordinates` RETURNS `(lat, lon)`** despite unpacking ST_X/ST_Y — it swaps them
   back. Getting it wrong put a probe's truck at latitude −82 and produced zero events with
   no error anywhere.
7. **`m3.clock` DERIVES ARRIVAL FROM GEOFENCE PRESENCE**, not from `claim.clock_since`. A
   test that sets the column and expects the clock to run is arranging the appearance of
   the condition rather than the condition.
8. **`start_claim` DEFAULTS `clock_since` TO `now()`.** Pass `started_at` when drafting
   from a historical arrival, or the detention clock records as starting when the poller ran
   — and the evidence window, anchored on it, finds no pings and mislabels the pack.
9. **`Settlement`'s RELATIONSHIP COLLECTIONS ARE NOT TRUSTWORTHY** (126 §4.5) — the same
   caution applies to `HeldClaim`: `draft_holds_for_events` adds with `db.add`.
10. **`timeout` IS NOT ON macOS.** `timeout 300 docker compose …` fails with "command not
    found" and a wrapper's `echo` can make that look like success. Cost a false "migration
    re-applied" this session.
11. **AN AD-HOC PLAYWRIGHT PROBE NEEDS `playwright install --with-deps`** (126 §4.8), and a
    probe hitting the real API needs `page.route` to rewrite `localhost:8008` → `api:8008`.
12. **`infra/.env` ON THE VM IS `0600 root:root`** — `sudo` the `grep` too, not just the
    `docker compose`. A bare grep fails and psql then eats the flags as a port number.
13. **DEBUG FILES COPIED INTO THE API CONTAINER LAND IN THE REPO** — `/app` is the mounted
    tree in dev. `ruff` caught two this session.
14. **THE EDGE IS INVISIBLE TO EVERY TEST** (125 §4.7) and **a single-file bind mount goes
    stale on deploy** (125 §4.6) — both still true.

---

## 7. Known gaps this session left

- **None of E2's four validation lines is met.** `docs/validation/m14-slice1.md` is the
  living record and every line is open. The suite is green and proves nothing there.
- **`/v1/vehicles` has never returned a 200 to us** — see §6.2.
- **The onboarding CLI's interactive path was exercised non-interactively.** `KEY=` and
  `FLEET=` cover step 1 and the mapping loop falls through when stdin is not a tty; the
  step-3 prompts themselves have not been typed at by a human. First real use is the call.
- **`make m14-validate` has never run against real ELD-backed stops.** Its report and its
  refusal are unit-tested; the query path against `visit_window` is exercised only by the
  shapes in those tests.
- **The slice-1 kickoff in `docs/kickoffs/` is a STUB and says so** — the original was
  delivered in-prompt and never written to the tree. It carries the F-01 correction rather
  than a paraphrase of the owner's document.
- **Push delivery has never run against a real subscription**; production has VAPID and
  zero subscriptions — though the app is installable now, which is what would produce one.
- **`SESSION-REPORT*.md` still live at the repo root** (six, from 122).

---

## 8. Restarting

```
make up                              # preflight, then the full stack
make seed-where                      # the Tampa origin — paste into Sensors
make test                            # 1991 pytest + 962 vitest — do NOT pipe it
make lint                            # ruff + import-linter (31 contracts)
make ui-layout                        # 353 checks, ~3.5 min, runs ALONE
make ui-image                        # 3 checks, real browser, needs the DEV server
make ui-pwa                          # builds, previews, drives a browser offline
make m14-prove                        # ELD pings -> ENTER/DWELL/EXIT, rolls back
make down
```

`make ui-layout-only STATE=<name>` measures one state in ~45 s — use it while building.

**Do not run pytest while `make test` is running** — same database, phantom failures.

`infra/.env` carries the live Gmail block and `M14_CONNECTOR_KEY`, and is gitignored.
**A send from dev is a real send — and so is a send from production.**

---

Each session ends by writing the next `HANDOFF-<n>.md` here and updating `HANDOFF.md` to
point at it.
