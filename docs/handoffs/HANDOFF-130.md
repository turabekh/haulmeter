# HANDOFF-130 — Journey 1 has no code left

**Session B complete and deployed.** B0, B3, B1, R2, R1 and the paid moment are on
production. Journey 1 — rate con to paid — has nothing further to build. What remains is
the world, and it is written down in `docs/validation/j1-journey.md` as seven lines only a
driver, a dispatcher or a broker can fill.

**The shape this session found**, continuing the series: **a brief describes what should be
built; the codebase decides what is left to build.** Four times in Session B a grep found a
slice smaller than its brief — B0's window was already presence-based, B1's in-app half was
already written, B3 was two divergences rather than one, and R2's defect was silence rather
than an ungated render. Twice a step-0 check found something the brief did not mention at
all, and one of those would have shipped a wrong number to a driver.

---

## 1. On production, verified by query

| | |
|---|---|
| `origin/main` | **`5fd791e`** (eight Session-B commits) |
| alembic head | **0083_receivable_kind_fee** |
| `receivable_kind` | `detention, tonu, layover, lumper, **fee**` ✅ |
| 0082 rename | `dunning_final_notice_sent_at` present, `dunning_escalation_offer_sent_at` gone ✅ |
| `arrival_reminder` class | registered ✅ |
| gates at push | pytest **2130** · vitest **1020** · layout **365** · import-linter **31/31** |

**Flags on the box:**

| flag | state | why |
|---|---|---|
| `j1_contact_parse` | **ON** | prefill; the driver's confirm is the safety |
| `j1_fee_disclosure` | **ON** | disclosure-only; the fee moment existing before the first real recovery is the point |
| `j1_arrival_nudge` | **OFF** | gated on validation line 5 — a push class nobody has watched arrive is one nobody has validated |
| `j1_preaccept_intel` | **row deleted** | retired in entry 168; the row was operator state describing nothing |
| `m14_overlay` | untouched, `NULL` | as instructed |

Contingency rate in force: **1500 bp (15%)**, PRD §242/§414's own number, at
`m09.contingency_fee_basis_points`.

**Behavioural proof, run on the box and rolled back so production gained no fixture rows:**
the pack states a 4-hour window on a disarm-closed visit and attributes the departure to
the **driver**; the PDF renders; the three dunning rungs render with **no** banned wording
and day 21 cites the rate confirmation; the fee posts at 5100 with `entry_id` NULL; the
full cadence walked at a fee receivable **sends nothing**; the claim scan never returns
one; the fee is absent from the owed list; and the year figure equals the rows beneath it.
The facility page was eyeballed on production rendering **"Ran past 120 free minutes · 0 / 6
· tracked stops"** — the raw pair, no percentage, same component as the confirm step.

---

## 2. The two findings that mattered most

**A fee would have inflated the figure it must never touch.** `m04.money_owed` returns
every receivable with no kind filter, and the Money tab sums the non-settled ones into
"what you are owed". A fee receivable is `invoiced` and never leaves it, so switching
`j1_fee_disclosure` on would have added **our own fee** to the number telling a driver what
BROKERS are sitting on — the biggest figure on the screen, wrong, in the direction that
flatters us, and the exact class of error entry 142 was written to eliminate. Caught in step
0, before any code. TRAPS 40a.

**Day 21 was silence, not a bad offer.** The rung was gated on
`collection_partner_agreement`, unsatisfied since the migration that added it, so every
claim reaching day 21 was counted `skipped_ungated` and the column was NULL on every row in
the database. A broker who ignored day 3 and day 10 heard nothing further, ever. The gate
was right and the rung it guarded was never built; the fix was to say the firmest TRUE
thing — what the rate confirmation already obliges — rather than to build a collection
partner nobody signed. TRAPS 40b.

The wording sweep that followed asserted the banned words absent against **rendered
output** at all three rungs, and that is what caught a driver-facing string nobody had
connected to it: the Money timeline rendered *"Collection offered"* in six locales for a
step that had never once occurred. A source grep would have missed it. TRAPS 40c.

---

## 3. Judgment calls worth contesting

1. **The year figure is a secondary line, not a second Meter** (owner-decided when I
   raised it). Entry 142 made this screen's one hero "what you are owed"; a rival figure of
   similar weight would leave two large numbers and no answer to which one the tab is about.
2. **No EXIT event is ever synthesised** — not for the dwell reader, not for the pack.
   Filling either gap from the event end would write history that never happened into the
   chain a claim is argued from. The pack says the **driver** stated the departure, which
   reads weaker to an AP clerk and is what actually happened.
3. **`money.kind.fee` is translated** where detention/TONU/lumper stay English. Those are
   trucking jargon (§12.3); this is our own charge and a driver must be able to read who is
   charging. `Haulmeter` stays as the proper noun.
4. **The fee's direction lives in the kind, not a sign on the amount.** A negative
   receivable would have made every existing sum quietly wrong.
5. **`j1_preaccept_intel`'s row was deleted, not left.** It was read by no code after entry
   168 deployed, and a flag row describing nothing is operator state that misleads.

---

## 4. Exact next task

**There is no Journey 1 code left.** The next step is the **pilot day**: put the app in
front of one real driver and one real broker, and fill lines 1–7 of
`docs/validation/j1-journey.md`. Line 5 is the one that unblocks a flag.

Owner-track, unchanged: **D13** · the collection partner (§17.2) · **Stripe activation and
fee collection rails** — R1 deliberately built the fee as an amount owed with **no way to
charge it**, and the Money row says so in six languages.

---

## 5. Known gaps this session left

- **`food-decide.test.js` is timing-flaky** — "sends the origin once the driver has
  actually been located" waits on a real 350 ms debounce and fails in isolation with or
  without any of this session's changes. Not touched: editing a test outside the slice that
  exposed it is how a session's diff stops being reviewable. Follow-on.
- **The claim-paid P0 has never run.** Built to spec, pinned by a test, dormant by design.
- **`make ratecon-eval` still has no corpus.** Everything asserted about extraction quality
  uses documents I wrote.
- **Four production facilities clear the n≥5 floor** and all carry walkthrough traffic
  (median completed visit 0.9 min). The intel renders honestly and says almost nothing until
  real stops happen.
- Carried: More's 291 px jump (§10.5 IA question), `--marker-500` at 2.04:1, 140 evidence
  records with no bytes.

---

## 6. Restarting

```
make up          # preflight, then the full stack
make test        # pytest + vitest in compose
make ui-layout   # the 365-check LAW 0 harness (needs the ui dev server up)
make lint        # ruff + import-linter
```

`./scripts/deploy.sh` is the documented deploy. **Check the outbound queue before any
container recreate** — the sweep drains every unsent message under whatever SMTP identity
is live (TRAPS §10). Playwright needs `--with-deps` on **every** invocation (TRAPS 69).
