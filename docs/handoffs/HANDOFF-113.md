# HANDOFF-113 — A6: the flag split, and the surface claiming was never reaching

> One session under **PRD v2.0**, building **A6 — service-center vendors**, the only
> Group-2 requirement with no owner decision in front of it.
>
> **Stack UP · nothing pushed, nothing deployed — three commits sit on local `main`
> awaiting the owner's word.** haulmeter.online is untouched and serving 112's code.
>
> The requirement asked for one thing (split the flag). Two more were underneath it:
> **the shared endpoints made the split a label rather than a gate**, and **claiming
> improved `/facility/<id>` while A6's own validation happens on the map card.**

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **3 commits ahead of `origin/main`** — `f722d51`, `9cf9775`, `fe31171` |
| Gates | **pytest 1364 · vitest 636 · layout 213 checks / 210 states · import-linter 30/30** |
| Migrations | unchanged — dev and production both `0059_f13_config_decl`. **A6 needed no migration** |
| Working tree | clean apart from untracked `collect_files.py` (pre-existing, not mine) |
| Local stack | **UP** |
| Deploy | **not run.** Nothing has left this machine |

**`m13_service_center` is OFF in dev**, deliberately — it was switched on to drive the
probe in §5 and switched back. Production has never seen the flag.

## 2. A6 was three requirements, and only the first was written down

v2.0 §3 A6 says: split the flag, FR1's ladder applies unchanged, `SERVICE_TOWING`
arrives from an admin edit or a claiming vendor. Measured before building:

- **FR7 and FR8 are already built** — HANDOFF-072, Session B. Claiming, the document
  check, the claimable picker, the vendor portal, and the service-center-only "My site"
  rail item (§23 entry 415) all exist. So A6 is **not** a build of FR7/FR8.
- **Everything M13 sat behind one flag.** `require_module("m13_vendor")` gated the whole
  `/vendors` router and `_require_active` guarded all 14 portal routes. Honouring §4's
  "`m13_vendor` stays OFF for food" would have taken the repair shops with it — which is
  precisely what A6 req 1 exists to prevent.
- **`m13_vendor` was ON in dev**, so the half §4 defers was live locally.

## 3. The gate is per vendor TYPE, and the shared endpoints are the whole difficulty

Both halves are the same endpoints, the same portal, the same tables. So the type is
what the flag answers about: `is_active_for(db, vendor_type)` is the capability
predicate, `is_active` survives only as "is this module reachable at all", and
`require_any_module` lets the router admit on **either** half.

**Gating the routes whose NAME says food is not a split.** `/vendors/{id}`, review,
report and confirm all take a `vendor_id`, and a `vendor_id` carries its half with it —
with food deferred, a cook's entire sheet (menu, appearances, reviews, show-up rate)
stayed readable through every one of them. Those now gate on the **vendor's own** half.
So does the portal, at `_my_vendor`, which all 14 routes already pass through — one
place, so a route added later cannot be left ungated by forgetting.

**Three holes worth naming**, each of which would have made the split cosmetic:

1. **`PATCH /vendor/profile` accepts `vendor_type`.** It is the one write that MOVES a
   vendor between halves, so a deferred cook could have walked back in by editing one
   field. Gated on the DESTINATION as well as the origin.
2. **A service centre could publish a food appearance** — `_my_vendor` passes them
   through, their half is on. The food-SHAPED routes assert food on their own.
3. **`/vendors/promotions/at/{facility}` is the one read that mixes the halves.** A
   truck stop can carry a cook's promotion and a claimed shop's; filtered by live half.

**Unfollow and mute are deliberately NOT gated.** §21.8 makes off exactly as easy as on,
and a driver who followed a cook before the deferral must not be locked into alerts by a
flag they cannot see.

## 4. Claiming was improving the surface nobody in a breakdown is looking at

FR7 has always fed `/facility/<id>`. **A5 put tap-to-call on the map CARD**, and A6's
validation is *"one real repair shop claims its facility and receives one call through
the app"*. So a shop could claim its site, enter the number it actually answers, and a
driver tapping that pin would still see the OSM number — or, for **28 of the 45 repair
facilities**, no call action at all.

The overlay is applied at the composition layer because **M1 may not import a later
module**. `claimed_facility_views` is a bulk read costing two queries plus one per
CLAIMED facility, so it scales with how many shops have claimed rather than with how
much map is on screen — A9 §4 is explicit that per-pin reads are what bind at national
density.

**Claimed phone and hours WIN; services UNION.** That asymmetry is deliberate: a service
list is a fact ingestion recorded and the shop is adding to (E3.2), while a phone number
is a single value the business is simply the better authority on. Nothing is written back
to the registry — read-time overlay only, and the probe in §5 confirmed `f02.facility`
was byte-identical afterwards.

`claimed_by` carries attribution because §11.7 forbids rendering a business's own claim
as the platform's finding — the same rule that stops a vendor's word being counted as
"N drivers". The card names who is speaking, reusing the caption row A5's rows already
use. **No new token, component pattern, navigation structure or notification class.**

## 5. Driven end to end on the running stack, on a real ingested facility

`247 Diesel and Tire Repair`, Valdosta GA — a real OSM row from the 18,317, chosen
because it has **no phone**, which is the common case:

```
before:            phone=None              services=['truck_repair']            claimed_by=None
pending claim:     phone=None              services=['truck_repair']            claimed_by=None
after approval
   + curation:     phone='+1-229-xxx-xxxx' services=[mobile_repair,towing,...]  claimed_by='247 Diesel and Tire Repair'
                   hours='24/7 roadside callout'
unknown service:   422 {"error":"unknown_service","unknown":["helicopter_rescue"]}
service half OFF:  phone=None              services=['truck_repair']            claimed_by=None
```

**A pending claim changes nothing** — approval is what speaks. Everything was rolled
back: the claim, the vendor, both probe accounts, and the flag. `f02.facility.attributes`
is unchanged, verified directly. **Dev carries no leftover state.**

The curated phone is masked above on purpose: the facility name is real OSM data and the
number was invented for the probe, so writing an invented number beside a real business
in a **public** repo is a small way to send someone a wrong call. Fixtures use the
reserved `555-01xx` range for the same reason.

## 6. Two tests were weak and the revert check caught them, not review

Every new assertion was run against reverted code before being trusted. **9 of 11** in
`test_vendor_flag_split.py` bite, across four separate reverts — pre-split single flag;
split present but gates absent; shape gates removed; flag unregistered.

- **The registration assertion was vacuous.** `flags.is_enabled` returns False for a flag
  **nobody registered**, so `assert is_enabled(...) is False` would have passed about a
  flag that did not exist. It asserts the ROW and its description now.
- **The layout state was proved by deleting `claimed_by` from its fixture** and watching
  all four checks fail — §112's rule that a state the harness cannot prove it rendered is
  a state that ships unmeasured.

The two that never bite are structural by design: the `VendorType`→flag mapping guard
(it bites when a third type is added ungated) and the both-halves-off router check.

## 7. A6 req 3 — towing, and a hole in the curation path

`SERVICE_TOWING` was already in `CLAIMABLE_SERVICES`, so req 3 looked done. It was not:
**`curate_claim` validated nothing**. Any string a claimant sent was stored and rendered
as `facility.service.<junk>` — a visible missing i18n key on the one card a broken-down
driver is reading. The vocabulary is closed now, refusals name the offender, and `scale`
cannot be curated in through the back door either (it is excluded from the picker for a
reason and the edit must agree).

## 8. The F13 defect the probe found, which has nothing to do with A6

`register_flag` returned an existing row **untouched**, so a description written once was
frozen on every box that had already booted — and A6 had just changed what `m13_vendor`
MEANS. Dev and production both still called the food half "M13 Vendor Network", the name
of both halves together. An operator reading that would switch off what they believed was
the whole vendor network and leave the service centres running.

`register_config` has refreshed declarations since `0059`. Flags now match, and the
asymmetry is the point: **`enabled` is operator state and a redeploy must never silently
flip a flag back.** Confirmed on the box — after a restart the description corrected
itself and `m13_vendor` stayed enabled.

**This lands on production the moment A6 deploys, and it is the only change in these
three commits that touches a foundation everything else uses.**

## 9. What I did NOT verify

- **Nothing is deployed and nothing is pushed.** Three commits, local only.
- **No real repair shop has claimed anything.** A6's validation — *"one real repair shop
  claims its facility and receives one call through the app"* — is **unmet**, and no
  amount of building meets it. What exists now is the path; a shop has to walk it.
- **No human has driven the claimed card on a handset.** The layout harness measures it
  at 360 dp, pa and xx-XL, and vitest asserts the rows — but a push on a real handset is
  now **eight** sessions old.
- **The vendor portal's claim/curate screens are unchanged and untested by a person.**
  `UnknownService` returns a named 422 the portal does not yet render specially; a
  claimant currently sees a generic failure. Stated rather than fixed.
- **`m13_service_center` has never been enabled anywhere but this laptop**, for minutes.
- **The A5→A6 overlap on `/facility/<id>` is untouched.** The profile renders its own FR7
  card and the map card now renders claimed data too; both are correct, neither knows
  about the other. No duplication today because they are different surfaces, but nothing
  enforces that.

## 10. Exact next task

**A6's build is complete; its validation is not, and cannot be by a session.** The next
Group-1/2 item is the owner's call, and the shape of the board has not moved:

- **A2 blocked on D5 · A4 on D3 · A7 on D1 · A8 on D7 · A10 on D4.** All seven decisions
  D1–D7 remain open; the §23 rule-6 delegation does not reach them (v2.0 §6 is a
  different document).
- **A11 is gated on A2.**
- **A9's tail** is the only other unblocked work: §6 TPIMS live availability (1 state —
  forms and emails, needs a person and a date), and the ODbL attribution line, which is
  required regardless of how D2 lands. I did not check whether that line is in the map UI.
- **Phase DoD stands at 2 of 8** (§7 items 5 and 7). A6 moves item 6 —
  *"a driver has found and called a repair shop"* — no closer without a real shop.

## 11. Restarting

```
make up          # stack is already up; this is idempotent
make test        # 1364 pytest + 636 vitest — do NOT pipe it
make lint        # ruff + import-linter (30 contracts)
make ui-layout   # 213 checks, ~4 min — only after touching a token or layout.spec
```

To see A6 at all, the flag has to be on: it is OFF in dev and unregistered in production
until these commits deploy.

Nothing is waiting on a background job, an ingest, or a queue.
