# HANDOFF-128 — the premise that was true when it was written

**Session A of Journey 1 (rate con → paid).** Three slices shipped: A1 broker contact from
the parse, A3 pre-acceptance intelligence + MPG, A2 the money terms in the driver's
language. All committed, none pushed.

**The shape this session found.** Every earlier handoff names a face of *a check can pass
while asserting nothing about the thing it is named for* (122 built-and-inert; 123
specified-never-built; 124 correct-in-one-process; 125 renders-everywhere-but-where-needed;
126 substitute-agrees-with-substitute; 127 check-that-looks-strongest-and-isn't). This one
is different and quieter: **a brief can be wrong because it was right when it was written.**

Step 0 of the kickoff — "re-grep before planning, measure, never trust this document" — was
the highest-value hour of the session. Three of its seven checks came back different from
the kickoff's premise, and two of those changed what got built:

- **A1 was a quarter of the slice it described.** Its premise cited HANDOFF-122 §3:
  `contact_email` is never written, so the packet and notice dead-end on a recipient that
  does not exist. That was true in HANDOFF-122. It was fixed in a later session, and the
  kickoff inherited a stale sentence. The field, the shared client/server rule, the registry
  write and the honest silent state all existed. Only the **parse** never filled them in.
- **J1-D2's gating was already done**, in the direction the owner signed, since migration
  0066 — and the claim-sheet rung it also names *does not exist to gate*.
- **J1-D3.1 contradicts a logged rationale** and is not mine to resolve. See §3.

Nothing here is a criticism of the kickoff. It is the reason its own Step 0 exists, and the
lesson is that Step 0 is not a formality to work through before the real work: **on this
codebase it IS a chunk of the work, and skipping it would have had me build a recipient
field beside the recipient field that was already there.**

---

## 1. Current state

| | |
|---|---|
| pytest | **2076** (was 1991) |
| vitest | **999** (was 972) |
| layout harness | **365** (was 357) |
| import-linter | 31/31 |
| migrations | head **0081_driver_profile_mpg**, applied and the column verified on the box |
| commits | `224e1d5` A1 · `32a63e4` A3 · `6c3506f` A2 — **local only, nothing pushed** |

Also unpushed from the previous session: `9695a0a` (skeleton flicker fix).

New flags, both registered **OFF**, both needing an operator decision in `/admin/flags`:

| flag | what it turns on | why it ships off |
|---|---|---|
| `j1_contact_parse` | prefill the broker email/phone on the confirm step | the eval that says how often the parse is right on real paper needs rate cons this project does not have yet |
| `j1_preaccept_intel` | the dock's risk pair + best hour on the confirm step | the reads are old; the moment is new |

`j1_contact_parse` gates the **draft**, not the prompt — the extra keys are extracted either
way and simply not handed to the screen. Switching it on therefore exercises a path that has
been running all along rather than one nobody has ever executed, which is the failure mode a
flag is supposed to prevent rather than create.

---

## 2. What shipped, and the one live defect found on the way

**A1 — the address that was printed on the paper all along.** `counterparty_email` and
`counterparty_phone` join the rate-con schema and prompt. The parse is held to the **same**
rule the typed path is held to, and a value that fails it becomes **absence, not an error**:
a photographed footer that ran off the edge yields nothing rather than `dispatch@`. Phone is
ten digits or nothing — last-ten truncation is for numbers a *human* typed, and applied to a
printed cell it turns `555-0134 x229` into a number that dials someone else. Prefill, never
send: `POST /load` still takes the address from the confirmed form.

**The live defect.** `register_rate_con_prompt` read `if get_active_prompt(...) is None`. But
`parse_structured` runs the template stored in the **database**, not the constant in the
source — so on any box that had ever parsed a rate con, editing `PROMPT_TEMPLATE` shipped
green and changed the live parse not at all. This session's own schema edit would have
inherited it exactly: a schema demanding `counterparty_email` against a prompt that never
mentioned it, **on production only, where no test looks**. A changed template is now a new
version; the earlier wording stays on the row that produced its calls. The dev box went 1 → 2
on the next parse, which is the fix visible in the wild. TRAPS §1, and it is now tested both
ways.

**A3 — the dock's history where the driver decides, and whose MPG that was.** `f01.driver_
profile.mpg`, nullable, and the null is the load-bearing half: NULL means *this driver has
not told us*, which is a different statement from any number, 6.0 included. The 6.0 default
is gone from the wire and the response names which of three the arithmetic used; only
`default` puts a line on screen, because a driver who reported 5.2 does not need telling we
used 5.2. `GET /intel/pre-acceptance/{facility_id}` composes M8's two existing public reads —
**no new computation**, so there is no second answer to drift from the first — and the
`MIN_SAMPLE = 5` floor **moved out of the facility surface onto the server**: there are two
clients now, and a floor enforced twice is a floor that will one day be enforced once.

**A2 — the money terms in the language the driver reads.** A reading block composed from the
parsed slots, in the driver's language, each figure carrying its own absence. The contract's
own wording stays verbatim and English beside it, with the note saying why, and `lang="en"`
so a Punjabi screen reader switches voice instead of reading English through Punjabi
phonology.

---

## 3. Owner decisions this session did NOT take

**J1-D3.1 — the platform fee as its own ledger row — contradicts a logged rationale, and I
left it alone.** `m09_money/domain/service.py:415-442` argues at length that **no** ledger
entry is posted on `recovered`, because F7's `record_recovery` posts cash_clearing →
driver_payable with a contingency split — correct for the M3-FR7 collection partner, where
money passes through us — while a driver who invoices a broker in their own name is paid into
their **own** bank. No cash crosses this platform, and posting an entry saying it did would
invent a movement we never handled. J1-D3 says the fee posts as its own row. Both cannot
hold. This is Session B, so it blocked nothing here, but **it needs the owner's ruling, not
my interpretation.**

Related, and worth knowing before that ruling: `mark_receivable_paid` fires the P0 only when
someone **else** marks the receivable paid, and the endpoint is driver-only today. So the
three-figure "gross · fee · net" notification J1-D3.2 describes is correct-and-dormant by
construction until a second actor exists.

**J1-D2 needs restating.** Day-21 dunning is already gated on
`collection_partner_agreement` (`ESCALATION_GATE`, `m03_detention/domain/service.py:1243`),
the gate reads unsatisfied, and there is no escalate control in the claim sheet to gate. The
remaining gap is not the gating — it is that while ungated day 21 currently sends **nothing**
(`skipped_ungated`), where D2 says it should send the firm contract-citing follow-up. Silence
is not the offer-nothing-can-honor defect, but it is a lost pressure rung.

**`FacilityProfileSurface` still renders a percentage above the n≥5 floor**, while the
confirm step renders the raw pair. Entry 153's comment argues the raw-pair shape and the code
beneath it applies the floor instead. The unsafe precision that entry was written about is
gone either way, and above n≥5 on a facility page a percentage is defensible — so making the
two agree is a **presentation question for the owner**, not a defect to fix inside a slice
that was scoped to the confirm step.

---

## 4. Judgment calls worth contesting

1. **A phone field was added to the confirm sheet**, not just parsed. Parsing it and storing
   it without rendering it would have been built-and-inert; rendering it costs one row on a
   form that already has six, and it is the number a driver calls when the dock will not
   answer the buzzer. Contest this if More's equipment card was the better home.
2. **MPG lives in More's equipment card, not on the calculator.** Truck facts live together,
   and the calculator reads rather than owning a second copy — but it does mean a driver on
   the calculator who wants to change it has a walk. The alternative was a new surface, which
   is §22.2 never-improvise territory.
3. **The A2 collapse was built and reverted.** The kickoff permits the verbatim clause text
   "behind/beside" a one-tap disclosure. Behind-a-tap was implemented first and
   `ui-components.test.js` went red — correctly: M4-FR4's terms block exists *because* "a
   driver was asked to accept a load on the strength of terms they could not read", so moving
   it a tap away **reverses a recorded decision** rather than implementing this one. It
   renders beside; the reading leads by order. The two dead toggle strings were removed from
   all six catalogues rather than left behind.
4. **`make ratecon-eval` is deliberately not a pytest.** It calls the live model, costs money
   per run, and answers a question with no fixed answer. Pinning that in CI makes the suite
   flaky or makes the number meaningless the first time somebody relaxes it for green.

---

## 5. Exact next task

**Session B of the Journey-1 kickoff — B1 then B2 — but B2 cannot start until §3's ruling.**

B1 (arrival nudge + on-time proof) is unblocked and Step 0 already confirmed its premise
exactly: `PUT /on-time/consent` and `GET /on-time/consent/{load_id}` exist at
`api/app/api/m05_protection.py:1039,1059` and **nothing in the UI calls them** — the
entry-122 shape the kickoff predicted. The fix is the toggle, not new machinery. J1-D1's
`arrival_reminder` notification class must be logged as an approved entry **before** the code
that depends on it (a new notification class is §22.2 never-improvise; entry 118's delegation
does not cover it, and the kickoff carries the owner's signature for it).

Before any of that, if the owner wants it: **the ≥10 anonymized rate cons.** `make
ratecon-eval DIR=…` is built and smoke-tested end to end, and its corpus is the one thing
this session could not manufacture — fabricating rate cons would have made the eval agree
with my own fiction, which is entry 126's failure wearing a lab coat. `j1_contact_parse`
stays off until that corpus exists.

---

## 6. Known gaps this session left

- **No real-paper measurement of the contact parse.** The runner exists; the corpus does not.
  Everything asserted about extraction quality today is asserted against fixtures I wrote.
- **`more` measures the MPG field only in its blank state.** `/auth/me` 404s in that harness
  state, which is a real state and the honest default, but a filled field at 360 dp in `pa`
  is unmeasured.
- **The offline branch of the calculator carries no `mpg_basis`**, so the disclosure line does
  not render offline. Defensible (that branch already says `needs_session` and nulls the fuel
  cost) but it means the one place the number is *most* ours is the one place we do not say
  so.
- **No plural forms anywhere.** `fill()` in `core/i18n.js` is `{name}` substitution, not ICU
  plurals, so "9 of 21 tracked stops" agrees with whatever the catalogue author guessed. It
  is pre-existing and it is why the raw-pair phrasing was chosen over a counted noun.
- Carried from before: More's 291 px jump (a §10.5 IA question), `--marker-500` at 2.04:1,
  140 evidence records with no bytes, the handset background-sensor test (deferred 12×), D13.

---

## 7. Two traps this session earned

Both belong in `docs/TRAPS.md` and are stated here so the next session meets them:

1. **A fixture that omits a key measures a screen your change never reached.** Two harness
   states passed green while rendering nothing new: `sheet-confirm` stops before a dock is
   chosen, so the pre-acceptance lines never existed; and `load-calc-result`'s mock carried no
   `mpg_basis`, so the MPG disclosure never rendered. Both were found by asking "would this
   have gone red?" rather than by the harness. The `rate_cents` note two fixtures away in the
   same file records the identical failure from an earlier session.
2. **A throwaway check written to audit other checks is not exempt from being wrong.** My
   one-off i18n audit reported a key missing from all six catalogues; it was a false positive
   from a regex matching the `t(` inside `emi**t(**"created")`. The standing test's regex
   requires a dotted key and never had the bug. If a quick script disagrees with a
   long-standing test, suspect the script.

---

## 8. Restarting

```
make up          # preflight, then the full stack
make test        # pytest + vitest in compose
make ui-layout   # the 365-check LAW 0 harness (needs the ui dev server up)
make lint        # ruff + import-linter
```

`make ratecon-eval DIR=/path/to/corpus` measures the parse against real paper. The corpus
lives **outside this repository** — a rate con is a counterparty's document carrying a
broker's terms and staff names, and this repository is public.
