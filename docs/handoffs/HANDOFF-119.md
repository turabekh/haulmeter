# HANDOFF-119 — the audit queue, worked: every critical that could be closed without an owner decision is closed

> **Stack UP · twenty-two commits UNPUSHED · nothing deployed.** haulmeter.online still
> serves 112's code.
>
> Session 119 read the 2026-08-07 audit and worked it: **nineteen findings closed, two
> partial**, and one of the audit's three unanswered questions answered. Three of the eight criticals are closed (F-13, F-21, U-07); four are blocked
> on things nobody in this environment can supply, and the last one (F-02) needs a
> decision before anyone starts.
>
> **Closing a finding opened one.** Tokenising the map pin made its contrast checkable in
> CI for the first time, and CI immediately said white on `--marker-500` is **2.04:1** in
> dark theme against a 3:1 floor. It shipped that way; it was simply unobservable while
> the colour was a literal inside a component. **Owner decision needed** (§5.1).
>
> **Two of the audit's own claims did not survive contact with the code**, and both are
> recorded rather than quietly absorbed (§6).

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **twenty-two** commits ahead of `origin/main` — 118's six plus this session's sixteen |
| `origin/main` | `113327e` — still **not re-verified**; `git fetch` has no credential here. **Re-fetch before pushing** |
| Gates | **pytest 1456 · vitest 714 (38 files) · layout 229 checks · import-linter 30/30 · ruff clean** |
| Migrations | **`0064_f08_outbound_delivery` (head)** — 0060–0064 are all new this session, each applied and round-tripped on the running stack |
| Working tree | clean; `longhaul.txt` and `split_dump.py` now **gitignored** at the owner's instruction |
| Local stack | **UP** |
| Dev data | Tampa `27.9506,-82.4572` intact, four DEV facilities at 88–125 m |
| Email | **dev still points at live Gmail.** A send from dev is a real send |
| Deploy | **not run.** The box has none of 113–119 |

## 2. What was closed

**The four money races (F-05, F-13, F-28, F-29)** — one defect wearing four hats:
check-then-act, with nothing between the read and the write. All four fixes are in
Postgres, because an application check reads rows a concurrent transaction has not
committed yet and does not survive a second API replica.

- **F-05** `uq_journal_entry_type_ref`, partial unique on `(entry_type, external_ref)`.
  `post_entry` raises `DuplicateEntry` from inside a SAVEPOINT so a caller can catch it
  without the request dying.
- **F-13** `ex_booking_no_overlap` EXCLUDE constraint on `m06.booking`. **`book()` now
  claims the row before any money moves** — posting the entry first meant the loser of the
  race had already credited the owner. The entry finally carries
  `external_ref=booking:<id>`, without which F-05's constraint could not have caught the
  double credit anyway.
- **F-28** `lock_account` takes the row lock **before** the balance is read; the ordering
  is the fix. `book_with_points` books then redeems, so correctness no longer depends on
  `get_session()` happening to roll the request back.
- **F-29** every contribution is logged; `points > 0` gates only the ledger issue. Setting
  an earn rate to 0 in the admin console used to remove the daily cap for that kind
  rather than merely stop paying for it.

**F-21 — the layover that was never overnight.** §23 entry 73 was cured in M3; M4 kept the
original bug and never received the fix. It took the earliest ENTER ever recorded at a
facility and the latest EXIT, so a second load to the same dock read the first visit's
arrival — and because M4 uses that pair to decide *whether a claim exists*, the dates
differed, `NoLayover` was not raised, and **a layover invoice was filed for a stop that was
never overnight, then sent to a broker under the driver's name.** Now routed through
`location.visit_window`, anchored on the stop's appointment. M4 was the last unscoped
`list_events` caller; M3's `accrue_events` is bounded and was re-verified. The class is
closed.

**U-07 / U-08 — the offline queue lost writes and said "synced".** `resp.ok` was never
consulted, so a 401, a 422 and a 500 were indistinguishable from success: the item left the
queue, `pendingWrites` fell to zero, and the status strip went quiet. Three outcomes now —
a network throw keeps the queue, 429/5xx retry with a bounded attempt cap, other 4xx
dead-letter. The dead-letter keeps the write **whole**, including the opId that is F12's
idempotency key, so a future retry surface can replay one exactly once.

**U-01, U-02 and the rest of the UI kickoff** — see §4.

**F-07 — authentication had no throttle of any kind.** No limiter, no lockout, no attempt
counter, on a live product with real driver accounts. Bounded per identifier (5) and per
IP (20) in a sliding 15-minute window — sliding, because a lockout hands an attacker a
denial-of-service against a driver. It lives in Postgres, not Redis: `core/events.py`
establishes that Redis here degrades silently, which is right for a live channel and wrong
for a security control that would then fail open.

**The throttle runs before the hash, and that ordering is the fix.** Checked afterwards it
would count correctly and still pay for Argon2 on every rejected attempt — stopping the
stuffing while leaving the CPU-exhaustion vector the finding actually names exactly as it
was. `VERIFY_SLOTS` caps concurrent verifications so a flood cannot put every threadpool
worker inside a hash and stop the endpoints that have nothing to do with logging in.

Two details decide whether it works at all. The client IP is the **last** `X-Forwarded-For`
entry, not the first — Caddy appends the peer it saw, so taking `[0]` would let an attacker
rotate a header and evade the IP limit; trusting the header is safe only because the
deployed API publishes no port. And attempts are recorded against the **submitted** address
whether or not an account exists, or the throttle becomes an account-existence oracle
answering what the 401 is careful not to.

**F-17 + F-18 — the AI cost control had never governed a call, and had no period.**
`_check_budget` returned silently for a module with no budget row and nothing in the
product ever wrote one. The two had to ship together: seeding budgets while `budget_used`
still summed *every call ever made* would have turned an inert guard into a time bomb, each
module going permanently dark the first time it crossed its number.

**The third option is the part worth remembering.** Refusing an unbudgeted module was the
obvious counter to fail-open and it is worse — `main.py` only *warns* if boot registration
fails, so one bad startup would take every AI feature dark on a box with no monitoring. A
missing row now falls back to the compiled default: no uncapped state, and no state where a
missing row is an outage. Seeded for all thirteen modules, not the four that call F9 today,
because a per-module opt-in is a list someone must remember to extend.

**F-23 — the settlement audit compared scoped against unscoped.** `paid` was one document;
`owed` was every unsettled receivable ever. It told drivers their broker underpaid on money
that broker had never been billed for, and re-flagged the same balance on every later
settlement into a number adjacent to the North Star. Scoped to the settlement's own pay
period. **The limitation is in the code, not hidden:** it scopes by the receivable's
creation date as a proxy, because there is no settlement→load link.

**F-14 + F-22 — a facility now knows what calendar it keeps.** The audit named this its
own prerequisite and could not answer it from a dump. The answer was **no** — F2 carried no
timezone, and `DriverProfile.home_timezone` is written by nothing outside the tests, so the
product's only notion of local time was itself inert. Both money questions were being asked
of UTC instants: an 11pm→5am Dallas stay billed one night instead of two, and an 8pm→4am
Dallas layover — one UTC day — was **refused outright**. F-21 filed claims that should not
exist; F-22 refused claims that should.

`facility.timezone` resolves from coordinates and stores on first use, so the ~4,800
existing rows heal as they are used and a dock a driver creates takes the same path. **It
cost a dependency** — `timezonefinder`, offline because the lookup must work in a dead
zone — and the codebase's own "keep the image light" argument was *measured* rather than
assumed: the API image was already 4.61 GB and is now 4.83 GB. 119 §5.4 has the reasoning.

**F-03 + F-04 + F-06 — one send path, three ways it was not telling the truth.** The
provider ref was an instance counter and `_pick()` builds a fresh instance per send, so
**every successful send in the product's life returned `smtp-1`**; it is the message's
real Message-ID now, which is what a mail provider logs and therefore searchable when a
broker says the notice never came. `_LazyCounterpartyGateway` — the object every real
send goes through — was tested by nothing, and that is *confirmed*: against the restored
F-03 defect the new test fails while the direct-construction test passes. And a failed
send wrote `sent_at` anyway, so the row claimed a delivery it never got; NULL now means it
did not go, and a five-minute worker sweep retries the transient ones.

**F-31** — the two empty migration downgrades now say why they are empty.

## 3. Everything was proved by sabotage, not by going green

This project has been taught five times that a green suite proves nothing about
correctness. So every fix here was checked by restoring the defect and watching the new
test fail:

| Fix | Sabotage result |
|---|---|
| F-28's row lock | stubbed `lock_account` → the two-connection test fails |
| U-07 | restored `resp.ok`-blind drop → **8 of 9 fail**; the 9th is the dead-zone test, the one path that was already correct |
| U-02 | restored the un-prefixed key → all 4 fail |
| U-01's guard | reintroduced one literal → caught, with file and line |
| F-21 | restored the unscoped resolver → the 2 new tests fail and **all 7 pre-existing m04 tests still pass** |
| F-07, no throttle at all | 9 of 12 fail |
| F-07, throttle present but AFTER the hash | **exactly 1 fails** — the plausible-but-wrong version, caught only by the test written for it |
| F-23 | restored the unscoped comparison → both new tests fail |
| F-14 + F-22 | restored the UTC calendar day → exactly the 3 tests written for it fail |
| F-03 + F-06 | restored the counter and the unconditional `sent_at` → 5 fail, and the one that does NOT is the direct-construction test the audit says was hiding F-03 |

**The F-21 row is the audit's own prediction, confirmed:** *"a fixture with one visit
cannot distinguish the two implementations."* It is why nine sessions of green walked past
a fabricated invoice.

**The last row is the same lesson in the other direction.** A throttle that counts
correctly but runs after the hash is the version a reviewer would nod at: it stops
credential stuffing, every obvious test passes, and the denial-of-service the finding
actually names is untouched. Eleven of twelve tests agreed with it.

**F-21's fixture had to become realistic before it could fail at all.** It planted geofence
events three weeks *before* the load was created — a sequence the product cannot produce.
That unreality is part of what hid the defect.

## 4. The UI comprehension kickoff, item by item

- **U-02 session hygiene — CLOSED.** Keys under `CACHE_PREFIX`, plus **a third instance the
  audit missed** (`vendor_appearances`) and the in-memory refs that outlive logout because
  `signOut()` routes without reloading. Only a test asserting what driver B *renders* could
  see that second half.
- **U-01 tokens — CLOSED.** Eight literals gone. Six compose from the existing
  `--on-accent`; `--shadow-pin` and `--scrim` are new and were the owner's call, both
  holding values already shipping. §23 entry 130. `token-discipline.test.js` sweeps the
  whole tree so the guarantee is a test rather than a sentence at the top of tokens.scss.
- **U-05 targets — PARTIAL.** `.filters-chip` 40 → 48 dp, converging on the pattern it
  already claimed to use. **The harness could not have caught it:** the button renders only
  under `preset === 'food'`, dark since 114 — a state that never renders is a state nothing
  measures. Three cases left as questions (§5).
- **U-03 English fallback — PARTIAL.** Counted always, warned in dev, per-locale counts at
  `/dev`. Swept es/pa/ru/uz/so across the five tab roots plus Load-live: **0**. The detector
  was proved by planting two missing Spanish keys and watching it name both. **The zero is
  narrow** — mocked API data left most of the ~45 dynamic `t(\`ns.${...}\`)` families
  unrendered, and those are the strings a non-English driver meets on Map and Money.
- **Item 1 `load-worst-case` — added and measured** (§6.2).

## 5. Exact next task

### 5.1 Four owner decisions, all cheap, all blocking

1. **`--marker-500` fails the non-text contrast floor in dark theme — 2.04:1 against 3:1.**
   The "Some" parking pin, and by E3.1's inverted valence the **OPEN** weigh-station pin,
   the one a driver must act on. Dark `--ledger-500` is 3.12:1, a hair over; every
   light-theme fill passes (4.33–5.35). A palette colour is a §22.2 never-improvise
   category, so it is **pinned in `contrast.test.js` at its measured value with a roster
   check** — it cannot drift down silently, and a repair fails the test until the exception
   row is deleted.
2. **F-02 + F-12, the flag gate bypass** — `default_on` versus `enabled`. Must not be
   split, or M3's detention clock goes silent.
3. **The two portal touch targets** (40 dp). §6.5 grants no portal exemption in writing,
   but applying the glove floor to a desktop form is a design decision, not a fix.
4. **`.cluster`'s hit area is 36 dp** and, unlike `.pin`, does **not** exceed its visual
   size — below §6.5's 48 and below §11.2's deliberate 44 dp map exemption too.

### 5.2 Blocked on facts nobody here can get

- **F-01 — what is `SMTP_HOST` on the box?** One command. The code half is confirmed and is
  worse than the audit's "probably": falling back to the recording gateway requires
  `SMTP_HOST` to be **blank**, not un-overridden. **HANDOFF-118 §5.2 says the opposite and
  is wrong.**
- **U-06, U-09, U-10** wait on the §23 loading-state entry — and
  `S23-PROPOSAL-loading-state.md` **does not exist in the tree**, so the blocker is one step
  further back than `AUDIT-INDEX.md` thinks. It has to be written before it can be approved.

### 5.3 Then

Three High findings remain, and they are the ones a single session cannot finish:
**F-30** (voice understands one of six languages — six locales of speech handling),
**U-11** (there is no loading state, which is the §23 proposal's own subject), and
**U-12** (the fixture ban and the nine fixtures it does not cover, which the loading-state
entry also gates). After those it is Medium and Low: **F-09** (location pings never
purged), **F-10** (worker scheduling is in-process only), **F-11** (the deploy path is
outside every review), **F-15**, **F-19**, **F-25**, **F-32**, and **U-04**'s six
remaining surfaces.

### 5.4 The dependency this session added, and why

`timezonefinder`, for F-14 and F-22. Offline because the lookup has to work in a dead zone;
a longitude approximation was rejected because DST and the Arizona exception are exactly
where a US-only product breaks. The image cost was measured before the decision, not after:
**4.61 GB → 4.83 GB (+4.8%)**. The "keep the image light" reasoning in `pyproject.toml` —
the argument that chose reportlab over WeasyPrint — was written when that was still true of
this image. It is not, and a 4.6 GB API image on a single VM deployed by tarball (A12) is
worth someone's attention on its own.

Still open and untouched from 118: the **handset background-sensor test** (v2.0 DoD #8),
and **push, then decide on deploying**. A deploy needs production `SMTP_*` on the VM.

## 6. What I did NOT do, and two things the audit got wrong

**Two audit claims did not reproduce.** Both were checked before acting, not after.

1. **U-01 says `.pin--stale` renders as "a white puck with a white border"** in light theme,
   calling it §11.7 failing silently. It does not: `border-color: var(--pin-color)`
   overrides the white border. Verified by computed style in **both** themes and by
   screenshot (`docs/handoffs/assets/`). Stale is a white puck with a **coloured** ring and
   a coloured glyph, and the affordance works. The literals were real and the contrast
   finding underneath them is real; the specific harm claimed was not.
2. **Item 1 says the worst-case Load stack puts "three cards above the Meter."** Measured at
   360 × 800: packet card top 16, **Meter top 230**, degraded 348, context 478, checklist
   699. One card sits above the Meter, not three, and the Meter clears the fold by 570 px
   at baseline and 498 px at +40%. The harness passes the new state at both.

   A better finding replaced it: **that combination was already being rendered by
   `load-packet-ready` — accidentally.** Playwright denies geolocation, so `locationDenied`
   is true in every Load state, and nothing in that state's name or `ready` selector said
   so. The day someone grants geolocation in a context option, the stack silently loses a
   card and every assertion still passes. `load-worst-case`'s `ready` proves all three
   cards with one `:has()` chain for exactly that reason.

**Also not done:**

- **Nothing pushed, nothing deployed. `git fetch` still cannot run** (no credential), so the
  ahead-count is arithmetic. The box was never contacted.
- **The screenshots are committed but only one is useful.** The dark capture caught the live
  basemap at continental zoom, so the light one is the one that shows the affordance; the
  computed styles are the both-theme proof.
- **U-07 says how many writes failed, not which.** The data to name them is stored whole.
  A surface for it is a design question and was not improvised.
- **The i18n sweep did not exercise the dynamic key families** (§4).
- `StubNotificationGateway` (SMS) and `StubPaymentGateway` (F7) are still untouched. After
  five inert engines the prior is inert-until-observed.
- **ON_SITE still has not been walked in a browser** (117 §7, 118 §6).

## 7. Restarting

```
make up                              # preflight, then the full stack
make seed-where                      # the Tampa origin — paste into Sensors
make test                            # 1411 pytest + 714 vitest — do NOT pipe it
make lint                            # ruff + import-linter (30 contracts)
make ui-layout                       # 229 checks, ~3 min, runs ALONE
make down
```

`infra/.env` carries the live Gmail block and is gitignored. **A send from dev is a real
send** — seeded `@bolt.example` counterparties are safe, that TLD does not resolve. To read
bodies locally: `SMTP_HOST=mailpit`, `SMTP_PORT=1038`, `SMTP_STARTTLS=false`, then recreate
the api container.

Migration 0060 **refuses to run against data that already violates either new constraint**,
naming the offending rows, rather than failing with a raw Postgres error mid-deploy. Local
data was clean and the constraints applied on the first attempt.

Nothing is waiting on a background job, an ingest, or a queue.
