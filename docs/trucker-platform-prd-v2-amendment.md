# PRD v2.0 — Driver-Validated Amendment

**Project:** Haulmeter — Consolidated Trucker Platform
**Document status:** Amendment to `docs/trucker-platform-prd.md` v1.0. **Build law.**
**Date:** August 2026
**Owner:** Turaboy
**Supersedes:** v1.0 §6 (build strategy), §8.13/E1 scope, and the acceptance criteria in §14.
**Leaves standing:** v1.0 §1–§5 (thesis, market, vision, personas, principles), §7 (Common Ground
F1–F15), and every module specification in §8 except where named below.

**Read order (unchanged, with this document inserted):**
1. `docs/handoffs/HANDOFF.md` → latest handoff
2. `docs/trucker-platform-prd.md` (v1.0 — still law)
3. **this document** (v2.0 — where the two disagree, this wins)
4. `docs/design-prd.md` (design constitution)

---

## 1. Why this amendment exists

v1.0 §6 governed a build. **That build is complete.** F1–F15 and M1–M13 exist, are tested, and are
deployed at haulmeter.online. v1.0's build law has no more work to do.

Between v1.0 and this document, the product was shown to working drivers for the first time. That
conversation is the only new information the project has that did not come from the project itself,
and it does two things v1.0 could not: it **confirms the thesis** and it **corrects the order**.

**Confirmed by drivers, unprompted:**
- Driver pays $0; the platform earns a percentage of bookings (v1.0 §1, §5.1 — validated)
- Detention recovery is the wedge (v1.0 §3 — validated)
- The document wallet is wanted (v1.0 §8.5 — validated)

**Corrected by drivers:**
- Food vendors are not wanted. M13's food half is deferred indefinitely.
- Parking must be **plannable in advance**, not discoverable on arrival. M6 as built answers the
  wrong question.
- Fuel must filter to the driver's **own** card program — not to a platform partner.
- Photo-and-send paperwork after loading is a daily burden nothing addresses.
- Repair shops, tire shops and service centers must be on the map and contactable.
- Crowd reporting must be prompted and easy, or drivers will not do it.
- Three separate features drew the same note: **"easy to follow."**

**This amendment therefore replaces a build law with a validation law.**

---

## 2. §6 SUPERSEDED — the new governing rule

v1.0 §6 said: build the Common Ground in full, then M1→M13 in order, one continuous build, no
release phasing. **That rule is retired, having been satisfied.**

**Governing rule of v2.0:** work is ordered by **distance to a validated driver outcome**, not by
module number. A requirement is not done when its tests are green; it is done when a driver who is
not the owner has used it and the outcome is observable in the database.

Consequences:
- **No new module may begin** until §7's Phase Definition of Done is met.
- **Every requirement below names its validation**, not just its tests. Tests remain mandatory
  (working rule 4); they are now necessary and not sufficient.
- Module boundaries, import-linter contracts, flag discipline, the design constitution and all nine
  working rules are **unchanged**. This amendment changes what to build next and what "done" means.
  It changes nothing about how.

---

## 3. Amendment requirements

New requirements are numbered **A1…A12** rather than extending each module's FR series, to avoid
collision with existing numbering. Each names its home component, its flag, and its validation.

Requirements are grouped by dependency, not by preference. Group 1 has no external dependency and
should be built first.

### Group 1 — no external dependency

#### A1 — Stop Packet: automated post-loading paperwork
**Home:** M5 Protection + F4 Evidence · **Flag:** `a01_stop_packet`

After loading or delivery, drivers photograph documents and cargo and send them to a dispatcher or
broker by hand. This is the highest-frequency unaddressed burden reported.

Nothing new is required. F4 supplies guided capture with EXIF, GPS and server timestamps; F4's
Evidence Pack Composer is explicitly "one composer, many templates"; F6 types and OCRs documents;
F5 holds the counterparty; F8 sends with per-thread tracking; F12 queues offline; F3 already emits
the EXIT event that marks the moment.

Requirements:
1. A capture checklist per stop type — BOL, seal, cargo condition, lumper receipt, damage. The
   checklist is configuration (F13), not code.
2. A new F4 template, **`stop_packet`** — a routine handoff document, explicitly not a claim and
   not a dispute. Tone is neutral (v1.0 §5.5).
3. Composition triggered on F3 EXIT at a `shipper_receiver` stop; queued through F12; sent on
   connectivity.
4. Load reference numbers from F5 in the subject line, so an accounts-payable clerk can file it
   without opening it.
5. **The driver reviews before it sends.** Nothing leaves silently. A packet the driver did not see
   is a document they cannot vouch for.
6. Recipients: dispatcher and/or broker, from the F5 counterparty registry, driver-editable.

**Validation:** a driver who is not the owner completes a real stop, sends a real packet, and the
recipient confirms it arrived usable.

#### A2 — In-app lot-status prompt
**Home:** M1 + F10 + F8 · **Flag:** `a02_inapp_prompt`

The arrival prompt exists (HANDOFF-103/104) but only over Web Push, which requires permission,
class opt-in, a live service worker, a mirrored token and — on iOS — an installed PWA. Four
consecutive sessions found breaks in that chain. Drivers described an in-app dialog.

Requirements:
1. An **in-app prompt** shown when the app is foregrounded and F3 reports arrival. Reuses
   `prompt_for_lot_status`, the same report endpoint, the same F10 belief path.
2. Push remains the fallback for a backgrounded app.
3. **The two carry separate budgets.** §13.1's two-interruptions-per-day cap exists to protect the
   notification permission from revocation. An in-app sheet cannot revoke anything, and applying a
   push cap to a non-push surface means a driver who stops twice is asked once.
4. Trigger timing is **owner decision D5** (§6) — arrival versus settled. The most valuable report
   in the system is the driver who circles a full lot and leaves; the current settled-time trigger
   misses that case.
5. All existing refusals stand: wrong facility kind, already reported, not opted in, quiet hours,
   and the §13.4 DRIVING ban on interactive prompts.

**Validation:** ≥20 lot-status reports from drivers who are not the owner, within one week.

#### A3 — Belief source attribution
**Home:** F10 / F11 / M1 · **No flag** — this is a defect fix

The freshness badge reads `7m · 1 driver` even when the source is an authoritative DOT feed. A
driver who sees "1 driver" against an IDOT sensor learns to distrust every number on the map. The
timestamp is correct; the noun is wrong.

Thread `belief.authoritative` / `source` through to a feed-aware label (`7m · IDOT`). This is the
accuracy complaint, self-inflicted, and already scoped in HANDOFF-066 §6.

**Validation:** no facility card attributes a DOT feed reading to a driver.

#### A4 — Fuel program filter
**Home:** M7 + F1 profile · **Flag:** `a04_fuel_program`

M7 is built around `is_network`, meaning Haulmeter's future fuel partner — which does not exist.
The module's entire value is currently gated on a deal. **What drivers asked for requires no deal.**

Requirements:
1. F1 profile field: the driver's fuel program(s) — Comdata, EFS, TCH, or a carrier's brand
   agreement (Pilot / Flying J, TA / Petro, Love's).
2. Filter the map's fuel layer to brands the driver's program covers. Brand data already exists in
   the OSM pull.
3. `sells_fuel` remains **one definition** shared by the preset that draws a pin and the badge that
   prices it — they cannot be allowed to disagree (§23 entry 94's regression).
4. Whether this is a new chip or a state on the existing Fuel preset is **owner decision D3**.

**Validation:** a driver with a card program sees only stations they can use.

#### A5 — Service & repair discovery
**Home:** M1 + F2 · **Flag:** `a05_service_preset`

Drivers asked for repair shops, tire shops and "other entities that may help" on the map.

Most of this exists. `SERVICE_KINDS` already defines tire, wash, repair, mobile_repair, towing,
parts, scale and fuel. The OSM adapter already reads `shop=tyres`, `shop=truck_repair`,
`shop=car_repair`, `shop=truck_parts`, `amenity=car_wash` and the `service:vehicle:*` family.
`f02.search_service_facilities` already searches them.

Requirements:
1. Surface services on the map as a filter. **Precedent: the Food chip (§23, 2026-07-25) established
   that a preset chip is a filter row, not navigation — NAV-1 is untouched.** The same reasoning
   applies here.
2. Facility-versus-service rule, carried from the existing co-located-amenity mechanism: a
   **standalone** repair or tire shop is a facility of kind `repair`; one **inside** a truck stop is
   a `services` entry on the host, never a second pin (design-prd §11.1).
3. Facility card exposes tap-to-call, hours, directions and the service list.

**Validation:** a driver with a breakdown finds and calls a shop from the app.

#### A12 — Operational floor
**Home:** infra · **No flag — blocking**

Deployed today with no backups beyond manual dumps, no monitoring, all live API keys on an
internet-facing VM, and deployment by tarball of the working tree.

Requirements:
1. Automated database backups with a proven restore.
2. One health alert that reaches a human when the box is down.
3. Every data load records a snapshot identifier, so what the box is running is answerable.

**This is blocking for A9.** Loading ten times the data into an unbacked box is not a risk worth
taking.

**Validation:** a restore is performed and verified. An alert is triggered deliberately and arrives.

### Group 2 — depends on an owner decision or an external party

#### A6 — Service-center vendors
**Home:** M13 · **Flag:** `m13_service_center` (new, split from `m13_vendor`)

M13's food half is deferred (§4). Its **service-center half is exactly what drivers asked for** and
is already specified: M13-FR7 (claiming an F2 `repair` facility via document check, gaining verified
hours, service list, phone and callout) and M13-FR8 (the vendor portal they manage it from).

Requirements:
1. Split the flag. `m13_vendor` stays OFF for `food_mobile`. `m13_service_center` gates FR7/FR8 for
   `service_center` only.
2. FR1's verification ladder applies unchanged — `unverified` → `documents_on_file` → `verified`,
   displayed with §11.7's honesty discipline.
3. `SERVICE_TOWING` has no dependable OSM tag by design; it arrives from an admin edit or a claiming
   vendor. **That is the argument for A6 over more ingestion.**

**Validation:** one real repair shop claims its facility and receives one call through the app.

#### A7 — Advance parking search and booking
**Home:** M6 + M8 · **Flag:** `a07_parking_ahead`, with an F13 **validation gate on inventory**

The reported scenario: a driver leaving Philadelphia at 6am books a spot in Ohio for that night,
because they know it will be full when they arrive.

M6 as built answers the opposite question. `bookable_near(lat, lon, radius_m)` finds inventory near
where the driver **is now**; `closing_loop` fires when nearby lots are **already** full. Both are
reactive.

Demand-side requirements:
1. Search by **destination or along a route**, not current position.
2. Arrival-time estimate for the destination.
3. Availability for a **future window**. `Booking` already carries `start_at`/`end_at`; the data
   model needs no change.
4. A forecast that a lot **will be** full at arrival. F10 answers "full now." M8's "where do I sleep
   tonight" solver is the component that belongs here, brought forward.
5. Every prediction states its basis (v1.0 §8.8 — the UI never fakes precision).

Supply side is **owner decision D1** (§6).

**The flag's activation gate is inventory.** F13 already supports validation gates as flag
preconditions; use one. `a07_parking_ahead` may not activate until bookable inventory exists in the
target corridor. **A parking search that returns zero results teaches a driver the app is empty, and
that lesson is not easily unlearned.**

**Validation:** a driver books a spot more than 100 miles ahead of their current position and
occupies it.

#### A8 — Parking as a primary destination
**Home:** design-prd NAV-1 · **Owner decision — see D7**

Drivers asked for Parking as a bottom tab. NAV-1 fixes five tabs and names no sixth; navigation
structure is a §22.2 never-improvise category; and a §23 entry dated 2026-07-29 states explicitly
that "a sixth was never a candidate." **This is a reversal and must be logged as one.**

No session may act on this without an approved §23 entry. Three options are specified in D7.

#### A10 — Comprehension pass on detention and documents
**Home:** M3, M4, M5 · **No flag** — this is a quality pass

The two features drivers already like both drew the same note: make them easy to follow.

Requirements:
1. **Amend design-prd §22.3** to add a comprehension criterion: *can a driver complete this task in
   one pass, first time, without asking?* — evaluated on a driver, not in the harness. This is
   **owner decision D4** and a design-prd change, so it needs its own §23 entry.
2. Walk the detention flow with a driver end to end. Record where they stop, not what they say.
3. **Do not specify the document-portal work yet.** "Streamlined" is not actionable. One more
   conversation is required before this becomes a requirement.

**Validation:** a driver who has never seen the app files a detention claim without being told how.

#### A11 — Contribution economy
**Home:** F10 + F7 · **Flag:** `a11_points` · **Gated on A2**

F7 already carries points as a ledger currency redeemable against parking bookings. That closes a
loop no competitor has: report a lot status → earn points → discount the booking. Both halves were
asked for in the same conversation.

1. Points issue on accepted crowd reports (v1.0 §5.4 — contributions requiring effort are paid).
2. **Reciprocity display**, which is cheaper and usually stronger: "your report is why 6 drivers saw
   this lot as full tonight." The data exists to say it truthfully.
3. **Do not activate until A2 lands.** §23 entry 112's caution stands: watch whether prompted
   beliefs disagree with volunteered ones before scaling either.

### Group 3 — coverage

#### A9 — National facility coverage
**Home:** F2 ingestion · **Blocked by A12**

Coverage today is **9 states** (WI IN IA MN KS KY MI OH TX) and ~4,573 facilities. Measured: zero
pins within 8 km of downtown Dallas. A driver in the other 41 states opens the map, sees nothing,
and does not return. **This is the single largest product risk.**

Requirements, in order — the order is the requirement:

1. **Extend the osmium filter FIRST.** The service rules already read `shop=tyres`,
   `shop=truck_repair`, `shop=truck_parts`, `amenity=car_wash` and `service:vehicle:*` — but if the
   filter does not pass those tags into the extract, **the rules never fire.** HANDOFF-099 hit this
   exact trap. Going national on the current filter means redoing all 51 extracts. Verify against
   one state before the national run.
2. **Batch by Geofabrik region** (`us-midwest`, `us-northeast`, `us-south`, `us-west`) rather than by
   state — four downloads instead of 51.
3. **Run `make repair-fuel` and `make repair-scales` after every ingest.** The co-located rule is
   order-dependent *within* a batch; Texas produced 162 unmerged fuel islands and 203 unmerged
   scales on exactly that path.
4. **Handle volume before it arrives.** `_enrich` is per-pin (191 queries for 263 pins, bounded by a
   300-pin cap) and that cap will bind in every metro at national density — bulk reads in M3, M6 and
   M7 come first. Every `geom::geography` predicate needs a GiST index on the **expression**, not
   the column; run `EXPLAIN (ANALYZE)` before multiplying the table.
5. **Dedupe at density.** geohash-7 blocking with 0.4 name similarity will produce more false merges
   once metros are dense. An admin merge-review surface is required, and `/admin/facilities/*` must
   resolve merged ids — today an admin URL and a driver URL for the same id answer about different
   places.
6. **TPIMS live availability** is 1 state. Four are blocked on registration, two publish nothing,
   two are unreachable. This is forms and emails, not code; assign it to a person and a date.
7. **Chain locators** remain a deliberate stub pending ToS review — **owner decision D6.** Never
   scrape. Never Google Places.
8. **ODbL** — national OSM makes the dataset substantially OSM-derived. An attribution line in the
   map UI is required either way; the share-alike position is **owner decision D2**.

**Acceptance:** every US state returns non-zero truck-relevant results at a metro-scale viewport,
and the map renders within budget at national density.

---

## 4. Non-goals — amended

Added to v1.0 §5's exclusions:

- **Food vendors (M13 `food_mobile`).** Drivers said no. `m13_vendor` stays OFF for food. **Do not
  delete the code** — the cost is sunk and the flag makes it free to carry. Do not invest further.
- **"Better than Trucker Path, Truck Parking Club and the rest combined."** Reported by drivers as
  enthusiasm; it is not a specification and will not be treated as one. Taken literally it reopens a
  scope contest the product is currently losing on coverage. The five capabilities drivers actually
  named — detention that is easy, paperwork that is automatic, parking bookable in advance, fuel
  filtered to their card, repair shops they can call — constitute a coherent product no incumbent
  has. That is the scope.
- **New modules.** None begin until §7 is met.

---

## 5. What is unchanged

Stated explicitly so no session treats this amendment as permission to loosen anything:

- All nine working rules (CLAUDE.md) — plan first, Docker-only, push and deploy are the owner's call
  each time, tests with every change, `AI-CONTEXT` comments only, import-linter authoritative,
  design constitution supremacy, session handoffs, no secrets in the repo.
- The design constitution in full, including LAW 0 (mobile-first at 360×800), NAV-1 through NAV-6,
  the §22.2 never-improvise categories, and the §22.3 DoD — **to which A10 adds one criterion and
  removes none.**
- Every architectural boundary: `core < foundation < modules`, `.public` only, no lateral imports.
- Six launch locales. Every driver-facing string in all six.
- v1.0 §5's product principles, all seven.

---

## 6. Open decisions — owner only

Numbered for reference. No session may resolve these; a session that needs one **stops and asks**.

| # | Decision | Blocks |
|---|---|---|
| **D1** | Parking supply: recruit P4 property owners on one corridor, or become the booking layer over existing reservable inventory (Love's, Pilot Prime, TA Reserve-It)? | A7 |
| **D2** | ODbL position. Attribution line is required regardless; the share-alike stance is not decided. | A9 |
| **D3** | Fuel program filter: new chip, or a state on the existing Fuel preset? | A4 |
| **D4** | Add the comprehension criterion to design-prd §22.3? | A10 |
| **D5** | Lot-status trigger: arrival time or settled time? | A2 |
| **D6** | Chain locators — official API, partnership, or stay OSM-only? | A9 |
| **D7** | **Parking as a primary destination.** Three options: **(a)** amend NAV-1 to six tabs — *measure this before arguing it*: build a throwaway six-tab bar and run the 181-state layout sweep under all six locales and xx-XL; 360÷6 = 60 dp clears the 48 dp glove floor but the labels are the risk; **(b)** fold Money into Load and take the freed slot; **(c)** build A7 as a full-screen flow reached by a NAV-5 cross-link from Map, and promote it to a tab once inventory exists. **Recommendation: (c), with (a) measured in parallel.** A tab opening onto an empty screen is worse than no tab. Whatever is chosen, it reverses a §23 entry and must be logged as a reversal. | A8 |

---

## 7. Phase Definition of Done

This phase is complete when **all** of the following are true. Every one is an observation about a
person or the world, not about the test suite.

1. A driver who is not the owner has sent a Stop Packet that a real recipient could use. (A1)
2. ≥20 lot-status reports exist from drivers who are not the owner. (A2)
3. A detention claim has reached **actual payment**. (v1.0 §8.3 — the wedge, still unproven)
4. Push has been proven on a real Android handset **and** a real iOS device, or iOS has been
   formally excluded with a recorded reason. (standing item, four sessions old)
5. The map returns non-zero truck-relevant results in **all 50 states**. (A9)
6. A driver has found and called a repair shop through the app. (A5, A6)
7. A database restore has been performed and verified. (A12)
8. The iOS background-location question is answered. **F3 is the sensory system for the entire
   evidence engine and A1 depends on it.** An iOS PWA cannot hold background geolocation; if the
   answer is bad it reshapes the roadmap rather than adding to it.

**Until #3 and #8 are answered, the product's central claim and its central mechanism are both
unproven, and no amount of further building changes that.**

---

## 8. Acceptance criteria

Verified against reality, not against this document.

| # | Criterion |
|---|---|
| 1 | Every A-requirement built carries tests **and** a recorded validation observation |
| 2 | import-linter contracts still 30/30 KEPT |
| 3 | Every new surface registered in the layout harness **in the same commit** that creates it |
| 4 | Every A-requirement's UI passes §22.3 including A10's new criterion |
| 5 | Six locales complete for every new string; no English fallback reaches a driver |
| 6 | Every new flag has a description and, where it depends on the world, an F13 validation gate |
| 7 | No new §23 category (colour, type, spacing, component, navigation, notification class) invented without an approved entry |
| 8 | Coverage: 50 states non-zero; national render within budget |
| 9 | Backups proven by restore; one alert proven by firing |
| 10 | Every open decision D1–D7 either resolved and logged, or explicitly still open |

---

## 9. The standing warning

Carried forward verbatim from the handoffs, because it is the most expensive lesson this project has
learned and it applies to everything above:

> **A suite proves the code does what it was written to do. It cannot tell you the code was written
> to do the wrong thing, and it cannot see the thing nobody built at all.**

Every defect in the last twenty sessions was invisible to a green suite: a placeholder plus a test
of the placeholder; thirteen tests calling a function nothing else called; a token written by a path
production never took; a label asserted against the same table it rendered from.

**This amendment adds a second half to that warning.** Every requirement above was invisible to a
green suite *and* to the owner, for months, until a driver said it out loud. The suite cannot see
what nobody built. **The owner cannot see what nobody asked for.**

Measure the real data. Drive the real screen. Put it in front of a driver.
