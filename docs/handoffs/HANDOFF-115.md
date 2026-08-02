# HANDOFF-115 — the paperwork arrives on the Load tab, and the paperwork was empty

> **Stack UP · six commits UNPUSHED · nothing deployed.** haulmeter.online still serves
> 112's code.
>
> The session was scoped as a **surfacing rework**: the automation is built and correct,
> only the way its result reaches the driver is wrong. Re-grepping the seams before
> planning found that the first half of that sentence was false. **The Stop Packet a
> dispatcher received contained zero artifacts and one row** — the driver's BOL and cargo
> photos were in the database and not in the document. Measured on the running stack
> before a line was changed.
>
> Both halves shipped: the packet now contains the paperwork, and the paperwork now
> arrives as a card on the Load tab with one Send.

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **6 commits ahead of `origin/main`** |
| `origin/main` | `f81bdd6` — **verified with `git fetch`, not inherited.** 114 §1 recorded `76c44c6` and listed `f272c4a` as unpushed; both were pushed after that handoff was written, so the figure had rotted exactly the way §5's other findings did |
| Commits | `a4e282c` · `6d2d311` · `8d6af0a` · `93f872f` · `4266dc4` · `81bdd1a` — all six are this session's |
| Gates | **pytest 1381 · vitest 654 · layout 217 checks over 54 states · import-linter 30/30** |
| Migrations | none needed. dev and production both `0059_f13_config_decl` |
| Working tree | clean apart from untracked `collect_files.py` (pre-existing) |
| Local stack | **UP** |
| Deploy | **not run.** A6, 114's preset fix and all of this are absent from the box |

Owner decisions taken this session, all four as recommended: fix the packet before the
card · **no new notification class (Option A)** · the claim section shows an
**already-filed** claim only · **Send does not queue offline**, the card renders from
cache instead.

## 2. THE FINDING — the Stop Packet was a blank page

A1 is "photograph documents and send them to a dispatcher", named by drivers as the
highest-frequency unaddressed burden. This is what the dispatcher received, probed on
the running stack with a captured BOL and a cargo photo:

```
template      : PackTemplate.stop_record        ← not the stop_packet A1 specified
label         : stop-packet
artifacts     : 0  []
timeline rows : 1
   - SYSTEM {'event': 'stop_packet', 'stop_ref': '...'}
```

**Four independent mechanisms, each invisible to the suite.**

1. **`send_stop_packet` composed a brand-new empty log.** It called
   `evidence.create_log(...)`, appended one SYSTEM record, and composed the pack from
   *that*. `compose_pack` reads artifacts by `log_id`, and the driver's photos are on the
   stop's *other* logs. `compose_stop_pack` — "every log tied to a stop, as one document"
   — has existed since §23 entry 71 and was two lines away.
2. **A stop's DOCUMENTS reached no pack anywhere in the product.** A BOL is an **F6
   document** (`subject_kind="stop"`), and no composition path in the codebase calls
   `documents_for_subject`. So the packet, the detention claim pack and the load record
   all carried condition photos and never the paperwork. For A1 the paperwork is the
   entire payload.
3. **`PackTemplate.stop_packet` was dead.** It exists, is titled "Stop paperwork packet",
   nothing used it. The handoff announced itself as a "Stop record" — wrong on the one
   line whose whole job is to say what the document is, which is the exact defect the
   enum's own comment says `incident` was added to fix.
4. **`render_pack` was called with NO `PackContext`.** No parties, no load reference, no
   facility, no appointment. §17 says the PDF is a screen; this one was a hash block.

**Why the suite was green over it.** `test_stop_packet_send.py` asserts the subject line
and three *absences* — no receivable, no `record_claim`, no demanding words. Every one of
those passed over a blank page. Nothing asserted the document contained anything. This is
v2.0 §9's warning almost verbatim: *a suite proves the code does what it was written to
do; it cannot see the thing nobody built at all.*

**Fixed**, with the distinction that makes it safe: only **stop-scoped** documents join
the stop's hash chain. A CDL is filed against the ACCOUNT and must never be in a document
sent to a broker — asserted directly, with genuinely distinct bytes so the hash test
cannot pass for the wrong reason (it did, on the first run; the CDL and BOL were the same
PNG).

## 3. The second finding — the one-tap fallback produced nothing

Only the F3 geofence EXIT drafted a packet. `POST /load/{stop}/end` — the "Leave this
stop" control — did not.

§15.5 is **"build for auto, degrade to one-tap, never to nothing"**, and the sensor
everything here rides on is the single mechanism **v2.0 DoD #8 records as UNPROVEN on any
real handset**. So the fallback was the path that had to work, and it produced no
paperwork at all. It was also **unrecoverable afterwards**: `depart_stop` ends the stop's
armed life and `draft_stop_packet_on_exit` finds the driver's stop through
`active_stop_for_account`, so a later ping had nothing left to draft against.

Drafted before the departure now, and idempotent — one stop is one document, so a driver
whose EXIT already fired gets no second packet. Both assertions exist.

## 4. The rework itself

**The card** (`LoadSurface`, above the Meter). "You left [dock]. Your paperwork is
ready.", the load reference beneath, and **one** action — §8 gives a card one action max,
so the preview moved into the sheet where the driver is reviewing anyway (§23 entry 120,
a deliberate departure from the session brief's "Primary plus a quiet expand").

**It ARRIVES.** The tab read the queue once on mount, so a driver watching the Meter as
they pulled off the dock saw nothing until they left the tab and came back — the same
"it was done and I could not find it" failure the card exists to fix, one layer down. It
watches F3's own `lastEvents` seam for the EXIT now, and re-reads after a hand-leave.

**DRIVING (SM-3):** a line of text, no Send. **Offline (§15.1):** `fetchStopPackets` reads
through the F12 cache instead of a bare fetch — the packet is drafted server-side and a
dock is where signal dies.

**The sheet** (BottomSheet over the tab, NAV-3 — no navigation away). Two labelled
sections, one Send. The contents are NAMED from the same checklist the Load tab renders.
The recipient is pre-filled from F5 and **editable** (A1 req 6; the send route and
`send_drafted_packet` carry it now — the address on file used to be a verdict).

**The claim section reports; it never files.** Filing opens a receivable, increments the
broker's claim history and freezes the Meter — §12.2 forbids a button labelled about
paperwork doing that on the driver's behalf. Detention accruing with nothing filed shows
the packet alone, which is correct.

## 5. Two more defects found on the way

**`load.doc.cargo_condition` exists in none of the six locales**, while `cargo_condition`
is a checklist row for *every* stop type. `t()` falls back to the key, so **drivers have
been reading the literal string `load.doc.cargo_condition`** on the Load tab. Added in all
six.

**`locale-completeness.test.js` could not catch that class of defect** — it compares the
six catalogues *against each other*, so six identical gaps look complete. **Fixed after
the handoff was first written** (`81bdd1a`), in two halves: every static `t("literal")` in
`ui/src` is now checked against EN by scanning the source, and `t()` **throws on an
unknown key under test**, so every test that renders a surface is a detector for the
dynamic families whose vocabularies live in Python.

It found two on its first run, both mock drift of the §23 entry 84/85 kind, both rendering
a raw key into a screen a test was measuring: `level: "new"` (the server's `_REP_LEVELS`
can only answer rookie/regular/pro/elite) and a `/vendor/profile` mock missing
`verify_status`, which the portal shell renders in its header — "vendor.undefined", out
loud. Neither is a production defect; both were tests agreeing with themselves.

**`pseudoInflate` under-inflates any string with a placeholder** — it pads by 40% of the
*visible* text while the test measures 40% of the whole string, so a placeholder longer
than ~7 characters can never reach +40%. Every existing placeholder is ≤5; my
`{facility}` was 8 and failed the guard. Renamed to `{place}`, and the constraint is now
written down in `pseudo.js`, because the failure names the string and not the reason.

## 6. Every new assertion was proved RED

18 new tests (11 vitest, 7 pytest) plus the e2e leg, each run against reverted code
before being trusted — the mechanisms mutated one at a time: chaining disabled, the
private log restored, the old template, the empty context, the draft call removed, the
card removed, the EXIT watcher removed, the DRIVING guard removed, the recipient dropped,
the cache removed, the claim gate inverted in **both** directions.

Two were caught by this and are worth recording. The credential test **passed for the
wrong reason** first (CDL and BOL shared a hash — identical PNG bytes). The claim test
**did not bite at all** on its first mutation, because the fixture had no claim and both
branches returned `None`; it needed a genuinely filed claim and a genuinely *open* one.
A test that cannot fail is the thing this project keeps finding.

The **e2e full-platform day** never touched A1 — it calls `evaluate_ping` directly and the
EXIT carve-out lives in the HTTP layer. It now photographs a BOL, leaves, gets a DRAFT,
reads what the card reads, sends to an edited address, and asserts the BOL is in the
document the recipient receives.

## 7. Exact next task

1. **Push the four commits**, then decide on deploying. 114's own work (`f272c4a`,
   `f81bdd6`) **is already pushed** — 114 §9 item 1 is done to that extent. What remains
   is the deploy: the box still serves 112's code, so the production map renders a Food
   chip whose feature is dark, and A6 is still absent from it.
2. **The handset background-sensor test.** Everything in this session rides on
   `/location/ping` firing unprompted while the app is backgrounded. **No one has ever
   watched it do that.** v2.0 DoD #8. It is now also the gate on the notification
   decision (§23 entry 121) — a push class defined against a mechanism nobody has seen
   work is specifying interruption laws for an event we cannot cause.
3. **Run J7-AP in DRIVE.md**, and on step 7 **open the PDF**. The whole session is a bet
   that the document is now usable; nothing in CI can tell you whether an AP clerk agrees.
4. **Claim-on-EXIT one-tap and doc-expiry reminders** — the deferred half of this
   session's scope. Claim-on-EXIT needs an owner decision first: it is a money act behind
   a Send, and §12.2 governs.
5. **`register_flag`'s gate bypass is still OPEN** (114 §7) — F13's central promise going
   unenforced, untouched for three sessions now. **It needs an owner decision before it
   can be fixed, which is why it is still here:** the hole is that `register_flag(...,
   enabled=True)` creates the row ON and `add_gate` attaches the gate *afterwards*, so the
   gate is never consulted. Enforcing the invariant at `add_gate` would switch
   `a05_service_preset` OFF in production at the next boot — the Service chip disappears
   from a driver's map — because production's gate is unsatisfied as bookkeeping (111 did
   re-ingest nationally; nobody ticked the gate on the box). Raising instead would take
   the registry down at startup, which is the §23 entries 92/93/100 outage. So the fix is
   a real decision, not a refactor. *(`locale-completeness` — the other half of this item
   — is done, §5.)*

Then the v2.0 board, which has not moved: **A2←D5 · A4←D3 · A7←D1 · A8←D7 · A10←D4**, A11
gated on A2, all seven decisions D1–D7 open.

**Phase DoD: still 2 of 8.** Item 1 — "a driver who is not the owner has sent a Stop
Packet that a real recipient could use" — was **unreachable by construction** before this
session and is now merely *unmet*. That is the entire change in its status, and it is a
real one.

## 8. What I did NOT do

- **Nothing was deployed or pushed.**
- **No notification class** (owner's Option A, §23 entry 121). The full unapproved spec is
  in that entry for whoever revisits it.
- **No claim-on-EXIT.** Out of scope by decision, and it needs its own §12.2 argument.
- **No backfill.** Documents captured *before* this session are not in any stop's chain,
  so a packet for an old stop still carries only its condition photos. No production
  packets exist, so nothing real is affected — but a dev stop armed before today will look
  half-fixed.
- **`register_flag`'s gate bypass was not fixed** — it needs an owner decision, see §7
  item 5. Investigated to the point of knowing exactly what the decision is.
- **No human has seen any of this on a screen.** The harness measures it at 360 dp under
  `pa` and `xx-XL`, vitest asserts it, and a push on a real handset is now **nine**
  sessions old.

## 9. Restarting

```
make up          # already up; idempotent
make test        # 1381 pytest + 654 vitest — do NOT pipe it
make lint        # ruff + import-linter (30 contracts)
make ui-layout   # 217 checks over 54 states, ~3–4 min
```

To see the card without a phone: arm a stop, capture a BOL from the checklist, then
More → **Leave this stop**. That path drafts the packet as of this session, which is
precisely the thing worth checking.

Nothing is waiting on a background job, an ingest, or a queue.
