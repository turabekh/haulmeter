# HANDOFF-131 — the state of the platform at the break

**This is a BREAK handoff, not a session handoff.** HANDOFF-128, 129 and 130 each close a
piece of work; this one exists so that someone — the owner after a week away, or a session
with none of this context — can pick the platform up cold and know what is true, what is
running, what is waiting on a person, and what to do first.

Nothing here needs reading in order. §1 is what is true right now. §7 is what to do next.

---

## 1. Where the product actually is

Journey 1 — **rate con → paid** — is built end to end and deployed. A driver can
photograph a rate confirmation, have its terms and the broker's address read off the paper,
see what the dock has done to other drivers before accepting, run the detention clock, have
the packet drafted when they leave, send a claim, watch it chased on a cadence, and see the
money and our fee when it lands.

**None of that has been done by a real driver yet**, and that is the honest headline.
`docs/validation/j1-journey.md` holds seven lines only the world can fill; on 2026-08-16
all seven are open.

The suite is green — **pytest 2130 · vitest 1020 · layout 365 · import-linter 31/31** — and
that page is where this project has learned to say out loud that green proves nothing about
any of it.

---

## 2. Production, verified by query on 2026-08-16

`origin/main` = **`3d4c3fb`**. The deployed box is `haulmeter-test` (`uzimiz-prod`,
`us-central1-a`), serving `https://haulmeter.online`.

| | |
|---|---|
| alembic head | **0083_receivable_kind_fee** |
| `receivable_kind` | `detention, tonu, layover, lumper, fee` |
| rate-con prompt | **v2 active**, v1 preserved on its own row |
| SMTP | `claims@haulmeter.online`, Workspace mailbox, SPF/DKIM(`d=haulmeter.online`)/DMARC all confirmed PASS by the owner |
| dwell samples | 60 usable across 4 facilities clearing the n≥5 floor (was 22 across 1) |

**Flags:**

| flag | state | meaning |
|---|---|---|
| `j1_contact_parse` | **ON** | broker contact prefilled from the parse |
| `j1_fee_disclosure` | **ON** | fee posts on recovery; gross·fee·net disclosed |
| `j1_arrival_nudge` | **OFF** | waits on validation line 5 — a handset observation |
| `m14_overlay` | `NULL` | untouched all session, as instructed |
| `j1_preaccept_intel` | **row deleted** | retired; it was operator state describing nothing |

Contingency rate in force: **1500 bp (15%)** — PRD §242/§414's own number — tunable at
`m09.contingency_fee_basis_points` without a deploy.

---

## 3. What is uncommitted in the working tree, and why I left it

```
 M CLAUDE.md
?? .claude/agents/I18n-auditor.md
?? .claude/agents/gate-verifier.md
?? .claude/agents/reviewer.md
```

**These are not mine.** `CLAUDE.md` gains the Haulmeter brand line and a pointer to
`docs/trucker-platform-prd-v2-amendment.md`; the three agent definitions are new. They
appeared in the tree during the session. I deliberately did not stage them — folding
someone else's in-progress work into a commit whose message describes something else is how
a diff stops being reviewable. **They are yours to commit when ready**, and nothing in the
deployed system depends on them.

---

## 4. What this session did, in one pass

17 commits. In order of what they were about rather than when:

**Journey 1, Session A** — the rate con becomes a load a driver can read
- `224e1d5` broker contact parsed off the paper (flag `j1_contact_parse`)
- `32a63e4` pre-acceptance intel + driver-reported MPG (migration 0081)
- `6c3506f` the money terms stated in the driver's language

**Journey 1, Session B** — the pack, the nudge, the money moment
- `acfb1a3` the pack states the visit and who reported the departure
- `f7ed632` one dock, one figure, one format (`DwellIntel`)
- `f11155a` the pre-acceptance flag retired, kill switch kept
- `cb20e4c` + `616420d` the arrival reminder and the on-time check-in
- `c5f62de` day 21 says the firmest true thing (migration 0082)
- `6c61457` the contingency fee as a receivable (migration 0083)
- `5fd791e` the paid moment and the year figure

**Infrastructure and correctness**
- `9695a0a` the skeleton reserves its box
- `5e6b241` a visit is a row, not a pair of edges
- `6506eff` the SMTP identity cutover

**Records** — `3212609`, `5da63a1`, `3d4c3fb` (handoffs 128–130), decision entries **161
through 173**, and three new TRAPS sections.

---

## 5. The pattern this session established

Every earlier handoff named a face of *a check can pass while asserting nothing about the
thing it is named for*. This session named the next one, and it is about **briefs** rather
than tests:

> **A brief describes what should be built; the codebase decides what is left to build.**

Six times a step-0 grep found the work smaller or different than described:

| brief said | codebase said |
|---|---|
| `contact_email` is never written | it is — only the PARSE never filled it |
| the evidence log replays events for its window | it has read presence since entry 73 |
| build an in-app arrival card | it exists, and nothing asserted it |
| escalation renders while ungated | it never rendered at all — day 21 was silence |
| the facility page shows a percentage | that, **and** a second sample floor in JS |
| — (unmentioned) | a fee receivable would have inflated the "what you are owed" hero |

The last one is the one that matters: it would have shipped a wrong number to a driver,
and no test would have caught it, because the test would have been written to the brief.
**Step 0 is not a formality before the work. On this codebase it is a chunk of the work.**

The corollary is now in TRAPS: *"build X" is more often "assert X" than a brief expects*,
and building it twice produces two competing implementations.

---

## 6. Open threads, all of them

### Waiting on the world (nothing to build)
`docs/validation/j1-journey.md` — seven lines. Line 5 (the arrival path on a real handset)
is the only one that unblocks a flag.

### Waiting on the owner
| item | what it blocks |
|---|---|
| **D13** | any counterparty send type beyond what exists |
| **Collection partner** (§17.2) | the escalation rung day 21 deliberately does not offer |
| **Stripe activation / fee rails** | R1 built the fee as an amount owed with **no way to charge it**; the Money row says so in six languages |
| **Pilot fleet** | M14 slice 1 sits inert and validated only by fixtures |

### Known gaps, none blocking
- **`food-decide.test.js` is timing-flaky** — "sends the origin once the driver has actually
  been located" waits on a real 350 ms debounce; fails in isolation with or without any of
  this session's changes. Untouched deliberately: editing a test outside the slice that
  exposed it makes a diff unreviewable.
- **The claim-paid P0 has never run.** Correct, pinned by a test, dormant by design — it
  fires only when someone other than the driver records payment.
- **`make ratecon-eval` has no corpus.** Everything asserted about extraction quality uses
  documents I wrote. ≥10 anonymized real rate cons is an owner input; the corpus must stay
  outside this public repo.
- **The four facilities over the dwell floor carry walkthrough traffic** — median completed
  visit **0.9 minutes**, 3 of 58 exceeding a 120-minute free time. The intel renders
  honestly and says almost nothing until real stops happen.
- Carried from before: More's 291 px jump (a §10.5 IA question), `--marker-500` at 2.04:1,
  140 evidence records with no bytes, the handset background-sensor test (deferred 12×).

---

## 7. What to do first on return

1. **Read `docs/validation/j1-journey.md`.** It is the only page that says what is
   genuinely unfinished.
2. **The pilot day.** One real driver, one real broker. That fills lines 1–7 and is worth
   more than any further building.
3. If code is wanted before the pilot: the honest candidates are the **ratecon eval corpus**
   (needs your rate cons), the **flaky food-decide test**, or **Journey 2** — but Journey 1
   itself has nothing left.

**Do not** start by building something because a brief describes it. Grep first. This
session's whole lesson is in §5.

---

## 8. Operating it

```
make up          # preflight, then the full stack
make test        # pytest + vitest in compose
make ui-layout   # the 365-check LAW 0 harness (needs the ui dev server up)
make lint        # ruff + import-linter
./scripts/deploy.sh
```

Three things that have each cost this project time and are now in `docs/TRAPS.md`:

- **Check the outbound queue BEFORE any container recreate.** The sweep drains every unsent
  message under whatever SMTP identity is live. Caught once by luck, now a rule (§10).
- **Playwright needs `--with-deps` on every invocation**, not just the first — `run --rm`
  gives a fresh container. It reports the failure as *"Target page, context or browser has
  been closed"*, which reads like a page bug (entry 69).
- **A credential change has no deploy path.** `deploy.sh` excludes `infra/.env` by design,
  so a local edit never reaches the box. It is placed there or it has not happened.

Where things live: `docs/handoffs/HANDOFF.md` points at the latest · `docs/decisions/` is
the append-only log (161–173 are this session) · `docs/TRAPS.md` is what has already cost
time · `docs/DRIVE.md` is the manual test journeys · `docs/validation/` is what the world
still has to prove.
