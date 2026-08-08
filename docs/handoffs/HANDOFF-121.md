# HANDOFF-121 — the loading state, the last critical, and two deploys

> **Stack DOWN · thirteen commits, five of them UNPUSHED · DEPLOYED TWICE.**
> `haulmeter.online` serves 121 at head `0066_f13_default_on`.
>
> Six instructions, each a word or two: *"approved, do the loading-state work"*,
> *"proceed with the portal touch targets"*, *"use your judgement and proceed"*, *"deploy
> it"*, *"fix N-03"*, *"deploy it"*.
>
> **The audit went 7 open → 3, and 41 of 45 are closed.** Every **High** and every
> **Medium** in both audits is now closed, and **nothing is PARTIAL**. Twelve findings closed
> this session: U-06, U-09, U-10, U-11, U-12 (§23 entry 131), U-04 and U-05 (entry 132),
> **F-02 and F-12 — the last open critical** — plus F-25 (entries 133/134), and **N-03**,
> which the deploy opened and the session closed. Migration **0066**.
>
> **F-01 is answered and it is the bad answer.** Production `SMTP_HOST='mailpit'` with
> `configured=True`, so the gateway never fell back to recording: **every counterparty email
> the deployed product has "sent" went into a container on the box, and F8 wrote `sent_at`
> over each one. No broker has ever received a detention notice from production.** M3 is the
> wedge. The code has been correct since entry 122 — the fix is one `.env` edit on the VM,
> which is the owner's under rule 9 and deliberately not done from here. §11.1.
>
> **What is left: three findings and one design decision.** F-01 (above, owner's),
> `--marker-500`'s 2.04:1 dark contrast (a §22.2 palette colour — stops for the owner
> whatever entry 118 delegates), and F-19/F-27, both Low and both waiting on work scoped
> elsewhere. §12.
>
> ---
>
> **Five things are worth reading over the rest, and all five are the same shape — a check
> that was green over the thing it existed to catch.**
>
> **§4** — the skeleton pins were invisible on a night basemap. Six pucks in the DOM,
> `visibility: visible`, counted by the layout harness, and unreadable to a human. 745 unit
> tests and 271 layout checks passed over it. Found by throttling the network and LOOKING.
> *A colour can be a legitimate token, correctly applied, and still be invisible where it is
> used.*
>
> **§5** — deleting the fixtures revealed that **thirteen checks had been measuring them**:
> nine unit tests, three of which stubbed an endpoint but never set a session so `apiGet`
> threw before the stub was reached, and four harness states whose own comment admitted it.
> The most useful is `facility`, which did **not** go red — it had no `ready` selector, so it
> kept passing while measuring the error line under the facility's name.
>
> **§8.2** — generalising the harness's scroller exemption found `overflow-x: auto` computed
> on `main.app-content`, above every element on every surface, because CSS promotes `visible`
> to `auto` when the other axis is not visible. **My change silently exempted the entire app
> from LAW 0's only mechanical check and the full sweep went green.** Caught by restoring a
> defect and watching the test pass when it should have failed.
>
> **§9** — F13's whole promise is that a flag cannot activate until its gates are satisfied,
> and **the gate had never once been consulted**: three modules, all six gates unsatisfied,
> all three live. The fix is the one that does **not** make the gates block anything.
>
> **§11.3** — N-03's first verification proved nothing, and noticing that was the fix's real
> content: a clean boot with the schema already at head runs the migration as a no-op, so the
> ordering is never exercised. The database had to be downgraded a revision to make the test
> mean something.

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **five commits ahead of `origin/main`** — the owner pushed mid-session at `1254d48`; the five since are the N-03 fix and the documentation of it |
| `origin/main` | **`1254d48`, OBSERVED — not arithmetic.** `git fetch` **worked this session**, which it had not since 117, so the four-session *"re-fetch before pushing"* caveat is **resolved**. Each pushed commit was verified present with `git merge-base --is-ancestor`. **Try the fetch before assuming it fails** — copying that caveat forward unexamined is how it survived four handoffs |
| Gates | **pytest 1558 · vitest 746 (39 files) · layout 283 · import-linter 30/30 · ruff clean** — all five measured on the final tree |
| Migrations | **`0066_f13_default_on` (head)**, local and production. New this session; applied, downgraded and re-applied locally, deployed, then downgraded and re-applied once more to prove N-03 (§11.3) |
| Working tree | clean |
| Local stack | **DOWN** — brought down deliberately at the owner's request at session end. It was UP and verified throughout |
| Dev data | Tampa `27.9506,-82.4572` intact, four DEV facilities at 89–125 m |
| Email | **dev still points at live Gmail.** A send from dev is a real send |
| Deploy | **RUN TWICE and verified, 2026-08-08** — 113→121, then N-03's ordering fix. `haulmeter.online` serves 121 at head `0066_f13_default_on`; `/api/health` 200 `environment=test`, UI 200, all seven containers up, all seven worker jobs green. Backup taken first: `haulmeter-20260808T132816Z.dump`, 9.2 MB, uploaded to `gs://haulmeter-backups` |

Baseline was vitest 714 / layout 257. **vitest +32, layout +22** — three skeleton states
and two portal states at four variants each, plus the two observation tests.

**The stack was DOWN at session start despite 120 signing off "UP"** — no containers at
all, not stopped, absent. Something removed them after 120 ended. The named volumes and
all four images survived, so nothing was lost, and `make up` came back first try with no
registry retry. Worth knowing only because 120's header says otherwise.

## 2. What was closed, and what the decision actually cost

**All five were one defect.** Every fetching surface had TWO states — data and no-data — so
a null response had to mean one of them, and the codebase chose *data*:

```js
const rawPins = computed(() => livePins.value ?? SAMPLE_PINS.filter(...));
```

That is U-10, and it fired on **every cold open**, not only offline: the first thing a
driver saw, every single time, was fabricated truck stops they could route to. Five other
surfaces did the same on failure — a CDL that is not theirs, Driver Dollars Delivered they
have not earned, a settlement discrepancy no carrier owes, lots to sleep in that are not
there.

**The primitive.** `SkeletonCard` / `SkeletonRow` / `SkeletonPin`, static, composed only
from existing tokens — `tokens.scss` is untouched. It does not animate: §6.4 forbids
looping ambient motion and a shimmer would compete with The Meter for the one living
element on a screen, so `prefers-reduced-motion` needs no branch because there is no
motion to reduce. Asserted at the source, because "add a subtle shimmer" is the likeliest
edit anyone will ever make to these files.

**The 200 ms delay and the DRIVING guard live in ONE shared gate** (`core/skeleton.js`),
not at each call site. Both are easy to state and easy to forget in a copy-paste, and a
surface cannot opt out of either.

**The Meter gains no loading state**, which was the entry's one hard prohibition (§9,
entry 52). Money replaces the **card** until `ddd_cents` is known, so The Meter renders
once, with a real number. Rendering it against `0` would put a confident **$0.00 in Mono**
over the driver's month, which is worse than either alternative.

**Ten importers, not seven.** The proposal's two open questions were settled in the entry
rather than deferred: **the §18 portals lose their fixtures too**, because entry 81's
argument is about the *drawer*, not the screen — and this file proved it, because
`SAMPLE_FUEL_ANALYTICS` was exported and imported by **nothing**, a fixture already
halfway back. **`/dev` keeps none.**

**`fixtures.js` is kept as a tombstone.** Deleting the file would have been tidier and
worse: the next person needing placeholder data reaches for that drawer, and the reasoning
has to be there when they open it. It now lists what it held, why it went, and the five
things to do instead.

## 3. Two decisions inside the work that are not obvious

**`serviceEmpty` and `foodEmpty` were NOT rewritten.** The kickoff forbade it and was
right: their expressions were always correct and merely unreachable, because `rawPins`
guaranteed pins. But `preset === 'service' && pins.length === 0` is *equally true while a
fetch is in flight*, and telling a driver "None mapped here yet" before their request
comes back is the same false assertion in the other direction. So they are gated by
**chain position** — wrapped in `v-if="overlay === LoadState.LOADED"` — and their own
conditions are untouched. What was wrong was the state, not the condition.

**offline vs failed needed TWO signals, and one of them would have been wrong.** The
kickoff asked for the split. `apiGet` flips the shared `online` ref on a transport throw
and rethrows a 4xx/5xx untouched, so reading `online` looks sufficient — **but
`fetchOverlay` does not go through `apiGet`.** It calls `fetch` directly, never touches
`online`, and a dead zone on the map would therefore have reported a server error and sent
a driver looking for the wrong fix. A transport failure is now also identified at the
source, as a `TypeError`. Measured, not assumed.

## 4. The defect that six checks passed over, and how it was found

**This is the section to read.**

The kickoff says *"Throttle the network and look at the screen"* twice, and it is the
only reason this was caught.

`SkeletonPin` first filled with `--line-1`, matching the other two shapes. That is correct
on a **card** and wrong on a **map**: dark `--line-1` is `#2A3644` against a night basemap
of about the same value. So the observation was written, it **passed**, and the screenshot
showed **an empty map**. Six pucks were in the DOM, `visibility: visible`, with a correct
bounding rect at (32,168), counted by the layout harness — and invisible to a human.
`--ink-1` would have been worse (`#151C24`).

Everything green over it: 745 unit tests, 271 layout checks including three states whose
`ready` selector is `.skel__pin`, `token-discipline` (no literal — it is a token), and the
new "references only tokens that exist" check (it exists). **A colour can be a legitimate
token, correctly applied, and still be invisible where it is used**, and nothing in this
project could see that.

The fix is `--on-accent`, theme-invariant white, with the precedent it belongs to: §23
entry 130 recorded that invariance as load-bearing **for pins specifically**, because *"a
fill that darkened with the theme would make a stale pin read as a filled one."* It does
not collide with `.pin--stale`, which is a white puck with a **coloured** ring and a glyph;
this is a white puck with a neutral ring and nothing inside it.

**Guarded three ways, since no existing check could have caught it:** the fill token is
asserted to be `--on-accent`, both theme declarations are asserted to name the same
colour, and no status token may appear in the file. My first version of the second
assertion was wrong — it checked that the light mixin does *not* redeclare `--on-accent`,
and it does, with the identical value. It failed correctly and was rewritten to compare
values instead of asserting absence.

## 5. Removing the fixtures showed that thirteen checks had been measuring them

None of this was the fixtures. It is what the fixtures were hiding.

**Nine unit tests asserted on fixture data while naming an endpoint.**

- **Three Docs deep-link tests called `stubWallet()` and never `setToken`.** `fetchWallet`
  goes through `apiGet`, which throws `"no session"` **before** it calls fetch — so the
  stub was never consulted and every assertion landed on `SAMPLE_WALLET`. They passed for
  the wrong reason for as long as the fixture existed, and the fixture's ids happened to
  match the stub's.
- **Four more said `(fixture)` in their own titles**, including one whose `.pill` assertion
  read the fixture's two expiring documents against a stub whose `expiring` is empty.
- **Two portal tests were named "falls back to the fixture demo when unauthenticated"** and
  asserted on `$1,840.00` and `$396.00` — invented revenue. They were tests *of* the defect.

**And four harness states had been measuring an invented facility.** `facility`,
`facility-prompt-mute`, `sheet-ask`, `sheet-review` all went red, and their own comment
said why: *"deliberately renders from fixtures … the surface falls back to its fixtures
exactly as it does today."*

**The most useful of the four is `facility`, because it did NOT go red.** It had no `ready`
selector, so it kept passing while measuring §15.4's one-line error under the facility's
name. **A state with no `ready` cannot tell a screen from its own error message.** It has
one now (`.dwell__figure`).

## 6. Verified against the running system, not the suite

- **The throttled cold open, 4 s overlay, 360×800 dark:** 6 skeleton pucks, **0** real
  pins, no facility named — and no *"None mapped here yet"* either, which would have been
  a different lie. `docs/handoffs/assets/loading-map-360dp.png`.
- **Then the pins land:** skeleton count 0, the real pin present by `data-facility`.
  Asserted by attribute, not by name, because a loaded pin is a puck and its name only
  becomes page text when the card opens. `loaded-map-360dp.png`.
- **The failed overlay:** *"Could not load the places on this map."* + **Try again**, 0
  pins. `failed-map-360dp.png`.
- **`money.empty` was translated into all six locales and rendered by NOTHING** — a driver
  owed nothing got a bare heading over an empty list. Found by applying the four-state
  rule, which is that rule earning its place on the DoD. `system.loading` is the same
  shape: six locales, zero consumers, still unused (the skeletons carry no text).
- **The harness's `hang` guard was proved able to fail**, not assumed: pointing it at a
  path that does not match turns all four `map-loading` variants red with the right
  diagnosis.

## 7. Sabotage — twenty-three restorations, and one that passed when it should not have

| Fix | Sabotage result |
|---|---|
| U-10 `livePins ?? SAMPLE_PINS` restored | **2 fail** |
| `AbortError` treated as a failure | 1 fail |
| empty lines speak before the overlay loaded | 2 fail |
| offline collapsed into server error | 1 fail |
| the 200 ms delay removed | 3 fail |
| the skeleton renders while DRIVING | 3 fail |
| `SkeletonPin` back to the invisible `--line-1` | 1 fail |
| harness `hang` pointed at a non-matching path | 4 fail (the layout states) |
| the burn-down, before any of it was true | 3 fail |
| portal scroller switched off, BEFORE the shell fix | **0 fail — see below** |
| portal scroller switched off, after it | 4 fail |
| `.app-content`'s `overflow-x` declaration removed | 1 fail *(0 before the test stopped matching its own comment)* |
| `.cluster` back to 36 dp, after the §11.2 floor check existed | 3 fail |
| F-02: `register_all` force-assigns `enabled` again | 1 fail |
| F-02: `register_flag` writes the operator's column | 2 fail |
| F-12: `is_enabled` computes the state itself again | 3 fail |
| the gate report goes quiet | 1 fail |
| a kill switch stops beating the default | 2 fail |
| the code default outranks the operator's decision | 5 fail |
| `enable()` stops reading its gates | 1 fail |
| N-03: the worker's wait on `migrate` removed | 1 fail |
| N-03: `alembic upgrade` back inside the api's command | 1 fail |
| N-03: `migrate` given a restart policy | 1 fail |
| N-03: the wait weakened to `service_started` | 1 fail |

**One row came back green, and it was the most valuable result of the session.** Switching
off the owner table's scroller left the state passing, because the ancestor walk had found
a computed `overflow-x: auto` on the app shell and exempted everything — §8.2. The two
`0 fail` results here are both the same lesson 120 §5 drew: *a sabotage that comes back
green is not a fix that is safe, it is a check that does not exist.*

The burn-down was written first and watched failing, and its third assertion named all ten
importers on the way down.

## 8. The portals — and the near-miss that matters more than the finding

### 8.1 The decision, and what the audit had wrong

The owner applied §6.5's floor to the §18 portals. **The documents settle it once read
together:** §6.5 says *"Minimum target 48 × 48 dp"* with no qualification; §18 exempts
portals from LAW 0, which is about mobile-**first** ORDER; and §18's only exemption
sentence points the other way — *"Nothing in Section 18 ever justifies desktop-first
thinking in the driver app"* protects the driver app FROM §18, not the portals from §6.
§18 also says portals are *"responsive down to tablet/phone"*, so an owner on a phone is a
case §18 **specifies**.

**The audit said "two portal controls at 40 dp". There were seven, and the worst was 20.**

| Control | Was | What it does |
|---|---|---|
| `.switch` (Fleet) | **233 × 20**, no height declared at all | changes which fleet the whole screen is about |
| `.cta--sm` (Fleet) | 40 | opens a fleet from the picker |
| `.spot__price-in` | 40 | **re-prices a spot** — the owner types into it |
| `.pause` | 40, and **43 × 48 in Punjabi** | pause/resume a spot, and cancel a booking, which refunds money |
| `.in` | 44 | the add-property fields |
| `.add` / `.add--sm` | 44 / 40 | submit a property / a spot |

Two failed on **width**, which is the half a short label breaks — "Pause" is ਰੋਕੋ. §6.5 is
48 × 48 and `min-width` was missing. Not raised to §6.5's 56 dp primary height: that is a
screen's one primary action, and these sit inside tables and lists.

**Registering the portals found three reflow defects nothing had ever measured.** The
bookings ledger ran to **437 px** at 360 dp and dragged the whole page sideways — fixed
with an `overflow-x` container, not a new pattern, because the harness's own overflow rule
already names *"the preset chip row, the portal rail"* as approved scrollers. At 200% text
`.prop__head` did not wrap, and `.in--name` ran to **451 px**: a flex item defaults to
`min-width: auto` and an `<input>`'s intrinsic ~20-character width **scales with the font
size**. That is the **third session running** in which that exact defect has been found
(U-04's scorecard search input, then twice here), and its grid form followed immediately —
`.kpis` used `repeat(2, 1fr)`, and a grid TRACK has the same min-content floor, so the KPI
row ran to 488 px. `minmax(0, 1fr)`.

### 8.2 The near-miss: I switched off LAW 0 for the whole app and the sweep went green

**Read this one.**

The harness exempts elements inside a deliberate horizontal scroller from its 360 dp rule.
That lookup checked only the **immediate parent**, which cannot work for a table — a table
is `table > thead > tr > th`, so wrapping it in a scroller exempted the table and still
reported every cell inside it. So I generalised the lookup to walk ancestors, which the
rule's own comment already describes as its intent.

Walking ancestors found `overflow-x: auto` computed on **`main.app-content`** — above every
element on every surface. Nobody asked for it: **CSS promotes `visible` to `auto` on one
axis when the other is not `visible`**, and the shell sets `overflow-y: auto`.

So the generalisation silently exempted **the entire application** from the only mechanical
check LAW 0 has ever had, and **the full 279-check sweep passed.** Nothing failed. The
harness would have gone on reporting green over any horizontal overflow anywhere, for as
long as anyone cared to look.

It was caught by **restoring the defect and watching the test pass when it should have
failed** — the scroller was switched off on the owner table, and the state stayed green.
That is the whole value of the sabotage discipline in one instance: the fix was green, the
sweep was green, and the check was dead.

`.app-content` now declares `overflow-x: hidden`, which states what MF-2 always intended,
and a **unit** test pins it so the computed-to-`auto` surprise cannot return inside a
browser-only suite.

**That test was also wrong first.** It matched the AI-CONTEXT comment above the
declaration, which quotes `overflow-x: hidden` in prose — so removing the real declaration
left it green. It strips comments now. Same shape as 120 §4's accent test that routed on a
word other than the one it claimed to check: *a test that matches its own documentation
asserts nothing about the code.*

## 9. F-02 + F-12 — the flag mechanism that had never gated anything

**This closed the last open critical, and the interesting part is what the fix declines to
do.**

### 9.1 One column doing two jobs

`enabled` carried both *"this capability ships on"* — a fact about the code — and *"an
operator switched this"* — a fact about this box. `register_all` wrote it by assignment to
express the first, so `enable()`, the only function in F13 that reads a validation gate,
was never on the path. **Measured on the running box before touching anything:**

```
m03_detention   collection_partner_agreement=false, legal_signoff=false   enabled=true
m06_parking     damage_liability_posture=false,     refund_policy=false   enabled=true
m07_fuel        merchant_agreement=false,           payment_partner=false enabled=true
```

Three modules carry gates. All six were unsatisfied. All three were live. M3 is the wedge —
it has been sending broker notices and generating claims with no legal sign-off recorded.

They are separate columns now: `default_on`, declared per module and refreshed at boot like
`description`, and a nullable `enabled` where NULL means nobody has decided.
`enable()`/`disable()` are its only writers and `enable()` still refuses on an unsatisfied
gate.

### 9.2 What the fix deliberately does NOT do

**It does not make gates block the default.** That is the obvious reading of "make the
gates real", and it would have taken M3 dark on the next boot. A stopped detention clock is
far worse than an unverified one, and satisfying one of those gates is an assertion that a
legal review or a commercial agreement actually happened — not something a deploy may
decide. The 29 July owner decision stands.

So the gate does the one honest thing left to it: **it says so.** `running_ahead_of_gates`
reports at every boot and on `/admin/flags`. Verified live:

```
WARNING: m03_detention is ON with unsatisfied validation gates:
         collection_partner_agreement, legal_signoff — the capability is live and its
         preconditions are not recorded as met
```

That turns "the gate silently does nothing" into "M3, M6 and M7 are live ahead of their
preconditions, and here they are" — §11.7 aimed at the operator instead of the driver.

**F-12 closes by construction.** Both predicates defer to one `_effective`, so they cannot
disagree about a registered flag; the audit's complaint was that they "only agree because
F-02 force-enables everything". They still diverge on an ABSENT flag, deliberately, and
both entry 105 rationales survive.

### 9.3 The backfill, and two things a tidier one would have broken

`default_on := enabled`, `enabled` untouched. Every one of the 22 rows keeps its effective
state. Applied, downgraded and re-applied on the running stack.

- **Nulling `enabled` everywhere** would have handed every flag back to its code default —
  and turned session 114's food half back ON, since m13's declared default is a shipped
  capability. "A redeploy must never silently flip a flag back" is the rule that column
  already obeyed.
- **Gating the default** would have stopped the clock. §9.2.

Stated plainly rather than hidden: on an already-booted box every flag now has a non-NULL
`enabled`, so `default_on` governs nothing *there* until somebody calls `clear_decision`.
That is correct and is the point — what changes is the mechanism, and it governs every
future flag, every future activation, and A7's inventory gate, which v2.0 §3 specifies and
which would have done nothing under the old assignment.

### 9.4 Two mistakes of mine that the tests caught

**I declared four flags on that ship off** — m13's two halves, F1 authority verification,
the weigh-station layer. Their own tests said so and failed. Their production rows say
`enabled=false`/`true` as operator decisions, which the migration preserves either way.

**`register_flag`'s refresh was an `elif` chain**, so a flag whose default AND description
both changed refreshed only the default — which is precisely the m13 rename that motivated
the description refresh in the first place. Caught by the test I wrote for the refresh, one
minute after writing it.

## 10. The three judgement calls

**F-25 — closed by disclosure, not by arithmetic.** `true_profit` subtracts the full
expected detention cost, which models a driver who recovers nothing inside the app whose
thesis is recovering it. Two loads with identical revenue — one dock detains you three
hours and pays, one detains you three hours and does not — scored identically. **The
arithmetic is unchanged deliberately:** netting in an expected recovery would make the
figure optimistic about money M3 has not collected, on the screen a driver uses to accept
or refuse a load. `basis["detention_recovery"] = "assumed_none"` now sits beside the sample
size and confidence — those describe the ESTIMATE, this describes the MODEL.

**F-19 — the audit's premise does not reproduce.** It says `upsert_record` → dedupe →
`merge_facilities` runs with no human in the loop. **The ingest pipeline never calls
`merge_facilities`.** A cross-source match calls `add_source`: a source row attached to an
existing facility, non-destructive, reversible by detaching. `merge_facilities` has two
callers — the human admin endpoint, which records an F14 `AdminAction`, and three
operator-run repair scripts. Severity corrected Medium → Low. What remains real is that a
`"matched"` outcome is a machine decision that two records are one place with nothing
queued for review; that is A9 requirement 5, a new admin surface, and the A9 session's
work. **Deliberately not half-built** — moderation rows nothing renders would be the sixth
built-and-inert engine this codebase has paid for.

**F-27 — deferred on a dependency, not on effort.** Latent, M12 is dark. The queries
compute `owed`, and F-23 closed with a named limitation: `owed` is scoped by the
receivable's creation date as a proxy because there is no settlement→load link, and the
real fix is a schema change. Optimising now would bake the proxy into a second place.

## 11. The deploy — 113→121, and what it turned up

Seven migrations onto a box that had been at `0059_f13_config_decl` since session 112.
**A backup was taken first** (`haulmeter-20260808T132816Z.dump`, 9.2 MB, offsite to
`gs://haulmeter-backups`) because migration **0060** is written to refuse rather than fail
half-way if production data already violates the money constraints it adds. It did not
refuse — production data satisfied all four.

```
0059_f13_config_decl -> 0060_money_race_constraints   (F-05/F-13/F-28/F-29)
                     -> 0061_f01_login_attempt        (F-07)
                     -> 0062_f09_monthly_budget       (F-17/F-18)
                     -> 0063_f02_facility_timezone    (F-14/F-22)
                     -> 0064_f08_outbound_delivery    (F-06)
                     -> 0065_f14_job_schedule         (F-10)
                     -> 0066_f13_default_on           (F-02/F-12)
```

Verified: `/api/health` 200 `{"status":"ok","environment":"test"}`, UI 200, a gated
endpoint 401 (so the routers are mounted), head `0066`, and **every flag's effective state
unchanged — including `m13_vendor` and `m13_service_center` still off**, which is the
specific thing 0066's backfill was written to protect (session 114's food decision).

**`/api/health`, not `/health`.** Caddy serves the SPA at the root and proxies the API under
`/api/*`, so `curl https://haulmeter.online/health` returns **200 and the index.html** — a
health check that passes without touching the API at all. Worth knowing before someone
builds a monitor on it.

### 11.1 F-01, answered — and it is the bad answer

```
SMTP_HOST='mailpit'   SMTP_PORT=1038   configured=True
```

The last blocked critical, answered by one command now that `gcloud` is authenticated here.
`configured` is True, so **the gateway never falls back to the recording gateway** — it
delivers to the Mailpit container running on the box. Every counterparty email the deployed
product has "sent" went into a local inbox, and F8 wrote `sent_at` for each one.

**No broker has ever received a detention notice from production.** M3 is the wedge.

This is worse than the audit's "probably" and it is exactly what 119 predicted: falling back
to recording requires `SMTP_HOST` to be **blank**, not un-overridden, and `.env.example`
ships `mailpit`. The deploy neither caused nor worsened it — `infra/.env` is never shipped —
and the code half has been correct since §23 entry 122.

**The remaining fix is one `.env` edit on the VM plus an api restart**, per §23 entry 126's
recorded shape. **Deliberately not done here: it writes a credential onto a production box,
which is the owner's action under rule 9.**

### 11.2 N-03 — the worker races the migration

The worker came up on schema 0059 while the api was still migrating, and every one of its
seven jobs failed:

```
worker: detention_clock failed (1x): column feature_flag.default_on does not exist
worker: outbound_retry  failed (1x): relation "f14.job_schedule" does not exist
```

`docker-compose.deploy.yml` gives the worker `depends_on: postgres (healthy)`; the
migrations run inside the **api's** command (`alembic upgrade head && uvicorn`). Nothing
makes the worker wait for them.

It self-heals — the failure backoff retries and the retry finds the new schema — but the
backoff is **up to 3600 s** for four jobs and 120 s for `detention_clock`, so every
migration-carrying deploy silently costs the wedge feature its clock for a couple of minutes
and the ingest jobs an hour. Cleared by restarting the worker once the api had finished;
**all seven jobs then ran clean**, including `location_retention` on production for the first
time (`{'deleted': 0, 'retention_days': 365}`).

**The fix is ordering, not retry** — and it was made and deployed later the same session, on
the owner's instruction, once the first deploy had settled. §11.3.

### 11.3 N-03, fixed and deployed

The migration is its own one-shot `migrate` service, and **both** the api and the worker wait
on `service_completed_successfully`. A dedicated step rather than a healthcheck on the api,
because the dependency is on the SCHEMA — *"wait until the api answers /health and know that
its command happens to migrate first"* is the implicit coupling that caused this, and with two
consumers declaring the same wait, a third cannot be added that forgets it. **Both compose
files**, because the local stack had the identical race and dev = CI parity means the ordering
a deploy relies on has to be the one `make up` exercises.

**The first verification proved nothing and saying so is the point.** A clean boot with the
schema already at head runs the migration as a no-op, so the ordering is never tested. The
local database was downgraded one revision to make `0066` genuinely pending, and on that boot
`migrate` applied it and the worker logged **zero** schema errors where it had previously
failed all seven jobs.

Deployed and observed on production, which is where the ordering actually matters:

```
Container haulmeter-migrate-1  Waiting
Container haulmeter-postgres-1 Healthy
Container haulmeter-migrate-1  Exited
Container haulmeter-worker-1   Starting     <- after, not alongside
Container haulmeter-api-1      Starting
```

`migrate` Exited (0), head `0066`, **worker schema errors: 0**, `/api/health` 200, UI 200.

**One consequence, stated rather than left to be discovered: a FAILED migration now stops the
api and the worker together** instead of leaving the worker up and erroring. That is the
honest outcome — a half-applied schema is not a state either should serve from — and the
driver-visible result is unchanged, because a failed migration already meant the API was down.

Held by `test_compose_migration_order.py`: exactly one service may run `alembic upgrade`,
every database consumer must wait for it to COMPLETE, and the one-shot must not restart (under
`unless-stopped` it would re-run alembic forever and the loop would look healthy). Four
sabotages, each caught.

## 12. Exact next task

**Nothing in the audit queue is both unblocked and worth a session.** That is a genuinely new
state for this project, and it changes what the next session should be: 41 of 45 are closed,
the two remaining Lows wait on work scoped elsewhere, and the two highest-value items are the
owner's rather than an agent's.

**So the recommended first move is not the audit — it is v2.0 DoD #8, the handset
background-sensor test.** It has been the named next task since session 115 and has been
deferred six times. It is now the oldest unmet thing on the board and it is load-bearing:
the whole A1 stop auto-pilot — geofence arrival, the detention clock, the packet, ON_SITE —
rides on a background sensor that nobody has ever watched work on a real phone. Sessions 115
and 116 built and walked everything downstream of it in a browser; the sensor itself is still
unproven, and no test in this repo can prove it. **It needs a human, a handset and a drive.**

Second, and cheap, is **walking ON_SITE in a browser** (117 §7) — the fifth built-and-inert
engine was found there, and the walk has still not happened.

Two things the owner may want to clear first, both minutes rather than sessions: **F-01's
`.env` edit** (§11.1 — the product's core promise does not currently leave the building) and
the **`--marker-500`** decision below.

### 12.1 The owner decision — ONE left, down from eight

119 §5.1's list is **half cleared**: items 5–8 were the loading-state proposal and are
done. What remains:

| | |
|---|---|
| **`--marker-500` at 2.04:1 in dark** | against a 3:1 floor. The "Some" parking pin and the **OPEN** weigh-station pin. Pinned in `contrast.test.js` so it cannot drift; a palette colour is §22.2 never-improvise. **§4 above is an argument for taking this seriously** — that was also a token that was legitimate and still wrong on this exact surface |
| ~~`.cluster` hit area 36 dp~~ | **CLOSED** — §9/§23 entry 133 |

### 12.2 What is left in the queue

| | |
|---|---|
| ~~F-02 + F-12~~ | **CLOSED** — §9. Migration 0066 |
| **F-01** | **ANSWERED — §11.1.** Production email goes to Mailpit on the VM. The fix is a credential on the box, so it is the owner's, not a session's |
| ~~N-03~~ | **CLOSED and DEPLOYED** — §11.3 |
| **F-19** | Low now, and the audit's premise is corrected — §10. Waits on the A9 session |
| ~~F-25~~ | **CLOSED** — §10 |
| **F-27** | Low. Waits on F-23's schema change — §10 |
| ~~U-04, U-05~~ | **CLOSED** — §8. Nothing in the queue is PARTIAL any more |

### 12.3 Still open and untouched

The **handset background-sensor test** (v2.0 DoD #8) and **ON_SITE has still not been walked
in a browser** (117 §7). Push and deploy are both **done** — §11. The `SMTP_*` question that
gated the deploy is answered and is now an owner action rather than a blocker (§11.1).

## 13. Things a later session will trip over

1. **`ui/src/core/fixtures.js` is deliberately empty and says so.** Do not add to it. The
   five alternatives are listed in the file.
2. **A new fetching surface must declare all four states** — it is on the §22.3 DoD now.
   `core/load-state.js` has `LoadState`, `Failure` and `failureOf(err)`.
3. **`failureOf` reads two signals** and the reason is in its own comment: `apiGet` callers
   flip `online`, direct-`fetch` callers (like `fetchOverlay`) do not.
4. **Never put a skeleton on The Meter** (§9, entry 52, entry 131). Replace the card.
5. **A layout state that holds a request open sets `hang: [fragments]`** and gets no
   networkidle wait. It MUST carry a `ready` selector naming the skeleton class.
6. **A layout state without `ready` cannot distinguish a screen from its error message.**
   `facility` proved it by passing.
7. **A stub returning `{}` where the endpoint returns `null` can crash a render.**
   `/vendors/service-center/{id}` returns null for an unclaimed facility;
   `serviceCenter.services.length` on a truthy `{}` throws and collapses every branch
   below it. It cost a debugging round here and is written into both the unit stub and the
   harness mock.
8. **`observe-loading.spec.js` runs inside `make ui-layout`** — deliberately, because an
   observation nobody re-runs decays into a screenshot in an old handoff. Its screenshots
   are opt-in behind `OBSERVE_SHOTS=1` so a sweep leaves the tree clean.
9. **`--on-accent` is the only fill that works over a basemap in both themes.** §4.
10. **`money.empty` is rendered now**; `system.loading` is still used by nothing, correctly
    — the skeletons are `aria-hidden` and carry no text.
11. **`.app-content` declares `overflow-x: hidden` and must keep declaring it.** §8.2.
    `overflow-y: auto` alone makes the other axis compute to `auto`, and the harness reads
    that as a deliberate scroller. Pinned by a unit test.
12. **A grid track needs `minmax(0, 1fr)`, not `1fr`,** for the same reason a flex item
    needs `min-width: 0`. Both forms of one defect are now in three surfaces' history;
    expect a fourth.
13. **The §18 portals ARE in the layout harness.** They are exempt from LAW 0's ORDER, not
    from §6's floors. `fleet-portal` needs the active fleet planted in
    `longhaul.cache.active_fleet` or it measures the picker instead of the workspace.
14. **`register_flag` takes `default_on`, not `enabled`.** Nothing but `enable()`/
    `disable()`/`clear_decision()` may write `enabled`, and a new module MUST choose its
    `default_on` — a capability that has never shipped should declare nothing and let its
    gates govern activation. §9.
15. **`enabled` is nullable and NULL means "no operator decision".** Any new read must go
    through `is_enabled`/`is_switched_off`, never the column, or NULL will be read as off.
16. **Adding a class to the harness's `TARGET_EXEMPT` regex removes it from the 48 dp
    check.** If it is a map marker, add it to `MAP_TARGET` too, or it becomes unmeasured —
    which is exactly how `.cluster` shipped at 36 dp. §8.1.

## 14. Restarting

**`make ui-layout` is now 283 checks and ~3 min.** It runs ALONE.
`make ui-layout-only STATE=map-loading` measures one state in ~45 s.

```
make up                              # preflight, then the full stack
make seed-where                      # the Tampa origin — paste into Sensors
make test                            # 1558 pytest + 746 vitest — do NOT pipe it
make lint                            # ruff + import-linter (30 contracts)
make ui-layout                       # 283 checks, ~3 min, runs ALONE
make down
```

To refresh the observation screenshots:

```
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm \
  --entrypoint sh -v "$PWD/docs/handoffs:/repo-docs" ui \
  -c "npx --yes playwright install --with-deps chromium; \
      OBSERVE_SHOTS=1 npx playwright test layout/observe-loading.spec.js --workers=1"
```

**Do not run pytest while `make test` is running** — same database, phantom failures.

**`git fetch` works again.** It had failed with *"could not read Username for
'https://github.com'"* in 118, 119, 120 and the first part of 121, and every one of those
handoffs carried an ahead-count that was arithmetic rather than an observation. It resolved
by the end of this session with no action from here, so a future session should **try the
fetch before assuming it cannot** — and should not re-copy the caveat forward unexamined,
which is how it survived four sessions.

`infra/.env` carries the live Gmail block and is gitignored. **A send from dev is a real
send.**

**Migration 0066 is new this session** and is applied on both the local stack and
production. It changes no box's behaviour — the backfill preserves every effective flag state
— but it is a foundation schema change, so read §9.3 before touching it.

**`make up` now starts a `migrate` service, and that is expected.** It is a one-shot: it runs
`alembic upgrade head`, exits 0, and the api and worker wait for that before starting (N-03,
§11.3). So `docker compose ps` shows `migrate  Exited (0)` on a healthy stack — that is
success, not a crashed container, and `ps -a` is needed to see it at all. If the api and
worker never start, read `docker compose logs migrate` FIRST: a failed migration now stops
both of them deliberately, rather than leaving the worker up and erroring against a schema
that has moved.

**Both compose files are mounted read-only into the api container** (`/repo/infra/*.yml`) so
`test_compose_migration_order.py` can assert that ordering. The files are mounted
individually rather than the `infra/` directory, because `infra/.env` lives there and carries
the live Gmail credential.

Nothing is waiting on a background job, an ingest, or a queue. **The local stack is DOWN**;
`make up` is all it needs.
