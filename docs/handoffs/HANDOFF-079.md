# HANDOFF-079 — FR7 service-center claim flow, end to end

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** the **last endpoint set with no UI now has one** — a service centre can find
its own site by name, claim it, and curate what a driver sees; and what a driver sees is a real card
rather than a dead function in `api.js`.

Read this alongside **HANDOFF-078**, which holds the consolidated whole-platform picture (§§6–11
there are still current).

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0045_m13_halal_claim** (no new migration this session) |
| Tests | **pytest 853 · vitest 317 · ruff clean · import-linter 30/30** |
| §23 decision log | 33 entries |
| Handoffs | 000 → 079 |
| Git | **14 commits local on `main`, no remote configured** |

## 2. What this session built

FR7's endpoints had existed and been tested since Session A with **nothing calling them**. The admin
half was already wired (`AdminVendors.vue` has the dispute desk). This session built the vendor half,
the discovery the flow could not work without, and the driver-facing payoff.

### The one thing the server genuinely lacked

Every facility lookup in the product is **geographic**. A claimant sits at a desk with a business name
and no viewport, so `submit_claim`'s `facility_id` had no way of being obtained by a human.

- `f02.public.search_service_facilities` — name search over facilities carrying a `services` list.
- `GET /vendor/claimable?q=` — portal-actor auth, so impersonation works.
- `GET /vendor/claims` reshaped to `{claims, service_kinds}`, mirroring `/vendor/documents`. Rows carry
  the facility's own **name and address** and **both halves of the union**.

### The four places a claim flow can quietly disappoint someone

1. **A name mismatch names the site we hold**, never the similarity score — "0.42" tells a business
   owner nothing about what to type next. The claimed-name field prefills from the **vendor's** own
   business name and never from the facility: prefilling from the facility would score 1.00 every
   time and make the check theatre.
2. **A rival claim is a dispute an operator settles**, disclosed on the search row **before** the form
   is filled, worded so it never reads as a rejection. The domain refuses to let a second claimant
   silently lose; the screen must not undo that.
3. **Curation adds.** Services ingestion knows render ticked and locked, each saying whose fact it is
   ("from our records" / "added by you"). E3.2's union is the screen, not a footnote.
4. **Proof is optional and the form says what that costs** — an operator with no document has only the
   name to go on.

### The driver payoff

`fetchServiceCenter` had been defined and called from nowhere, so an approved, curated claim ended in
nothing visible. `FacilityProfileSurface` now renders one card for a **claimed** service centre: the
business's own name and rung, services, hours, phone, and one line saying those are the business's own
words. An unclaimed facility stays a plain POI. `documents_on_file` renders neutral (C-1).

### The rail

A seventh item, **"My site"**, shown to `service_center` vendors only — a mobile cook has no site to
claim and a control that leads to "this is not for you" is decoration. The **route stays open**, so
switching type in Profile is not a dead URL. §22.2 makes navigation a never-improvise category, hence
§23 entry 32.

## 3. What live verification caught, and why it mattered

The API tests were green and the flow still would have shipped wrong. A live smoke script inside the
container (per 078's own lesson) searched the dev DB and returned **weigh stations**:

```
search 'truck' -> 2 claimable site(s)
   Truck Parking     · ['scale']
   Casey's Truck Stop · ['scale']
```

`scale` was already excluded from **curation** — a weighbridge feeds the M1 weigh-station layer, and a
service a claimant could tick would put an unverified scale in front of a driver deciding to pull in.
The exclusion had been written in one place and needed to hold in two: a facility whose **only**
service is a scale has no business for anyone to speak for.

**604 of the 605 facilities carrying a services list in the dev DB are OSM weighbridges.** Without the
fix the picker was a list of weigh stations. `CLAIMABLE_SERVICES` now lives in the m13 domain — F2
records what is there, M13 decides who may speak for it — and answers both "may I claim this?" and
"may I add this?", so a search hit can never be a refusal in waiting. `submit_claim` re-checks rather
than trusting the picker. A composite site still works as E3.2 intends: a truck stop with a tire bay
**and** a weighbridge is claimable for the tire bay, and the scale is not presented as the claimant's.

## 4. Verified live

```
vendor registered as a service centre
search 'beacon'            -> Blue Beacon · ['wash']
mismatched name            -> 422, as designed
claim submitted            -> pending on Blue Beacon   (row carries the NAME, not an id)
portal offers              -> tire · wash · truck_repair · mobile_repair · towing · parts
curate before approval     -> 409, as designed
```

The approve half needs an admin account and is covered by the API tests.

## 5. Exact next task — recommendation

**Ingest OSM service tags.** This is now the binding constraint, and it is new information: the
claimable universe in dev is **one facility** (`Blue Beacon`, wash). `parse_osm` already has rules for
tyres / wash / repair / parts / mobile repair; the Geofabrik pass run for E3.1 pulled weighbridges
only. Until a service pass runs, the FR7 screen is correct and has almost nothing to point at — and
**founding-vendor onboarding for service centres cannot start**.

**Then:** founding-vendor onboarding itself, still the standing recommendation since HANDOFF-072 and
now unblocked on the food side (a cook can sign up, build a menu, publish, and be found).

**Alternatives:** the four remaining weigh-station states (KS, KY, MI, OH); §17 Q9 truck routing,
still the largest open product decision.

## 6. Blockers

- **No git remote — seven sessions running.** Fourteen commits sit locally on `main`.
- **NEW: the claimable universe is one facility.** See §5. Not a code defect — an ingest gap.
- **A service centre still sees "My week" and "Menu & prices".** Both are food-shaped. Making the whole
  rail type-aware is a larger change than this slice, and half-doing it would be worse than the honest
  gap; logged in §23 entry 32 rather than left implicit.
- **`merge_facilities` may leave the survivor's attributes stale.** Carried from 076 §5, still unchecked.
  Note it now also touches FR7: a claim points at a facility id, and a merge that leaves attributes
  stale could strand a claim against a survivor whose `services` list no longer justifies it.
- **A vendor cannot delete their own listing or account** (§17 Q16 consistent, but self-serve signup
  makes self-serve exit a fair expectation).
- **Nothing rate-limits vendor registration.**
- **`categories` is collected and unused** — needs the structured treatment halal got.
- **One OSM false positive, known:** a `weighbridge` named "Tractor Pull Weigh Scale".

## 7. Open questions (PRD §17)

Unchanged from 078 §9. **Still open:** Q1 · Q2 · Q3 · Q4 · Q5 · Q7 · Q8 · **Q9 truck routing (largest)**
· Q13 · **Q15 deactivation conduct policy** · **Q16 hard delete / retention** · Q6.

## 8. Working rules (unchanged — non-negotiable)

Docker-only · **local commits only, NEVER push** · **plan first**, owner approval, then code · **tests
with every change** · live pulls never in CI · **AI-CONTEXT comments only** · import-linter
authoritative · **design-prd governs ALL UI** (LAW 0 mobile-first for the driver app, §18 for portals,
tokens only, six locales + pseudo) · §22.2 never improvises a token, component pattern, navigation
structure or notification class · session ends by writing the next HANDOFF.

Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

**Phase A holds:** no order, basket, total, checkout or billing column anywhere.

## 9. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-079 — FR7 service-center claim flow
1379762 A weighbridge is not a business: one list for claim and curate
4b2cd99 The other end of the claim: what a driver actually sees
a0accd5 My site: the four places a claim flow can quietly disappoint someone
f5e33a9 FR7 discovery: a claimant has a business name, not a viewport
```

## 10. Key files touched

```
F2       api/app/foundation/f02_facility/domain/service.py (search_service_facilities)
         .../domain/ingest/adapters.py (SERVICE_KINDS) · public.py
M13      api/app/modules/m13_vendor/domain/claims.py (CLAIMABLE_SERVICES,
         claimable_services; submit_claim re-checks) · public.py
API      api/app/api/vendor_portal.py (GET /vendor/claimable; _claim_row; claims
         reshaped to {claims, service_kinds})
TESTS    api/tests/api/test_facility_claim_api.py (NEW, 11 tests)
         api/tests/foundation/f02_facility/test_facility.py (+4)
UI       ui/src/surfaces/vendor/VendorSite.vue (NEW — the §18 claim section)
         ui/src/surfaces/vendor/VendorPortalShell.vue (type-conditional rail)
         ui/src/surfaces/FacilityProfileSurface.vue (the driver's card)
         ui/src/router.js · ui/src/core/api.js (4 FR7 functions)
         ui/src/core/i18n/*.json (45 keys ×6) · ui/test/vendor-site.test.js (NEW, 14)
DOCS     design-prd.md §23 ×2 (entries 32–33) · HANDOFF-079.md · HANDOFF.md
```

## 11. Ports / env

**No port or env changes.** LOCKED: postgres **5438** · api **8008** · ui **9008**. No migration this
session; no new F13 flags — the claim flow rides the existing `m13_vendor` flag.

Operational note, still true: `make ci` leaves Postgres running, so `make up` straight afterwards fails
preflight. **`make down && make up`** is the sequence.
