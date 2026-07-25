# PRD Extension E1 — M13 Vendor Network + Platform Additions

**Status:** **APPROVED 2026-07-25 (owner).** Folded in: PRD §6 build-order amendment (M13), PRD §17 Q9–Q13 (Q12 resolved — attributes, not kinds), design-prd §23 entries E-D1/E-D2/E-D3 plus two derived honesty rulings. **Session A (E2 + E3.2 + M13-FR1..FR4) is BUILT** — see `docs/handoffs/HANDOFF-071.md`. Session B (FR5–FR8) is the next task; FR9/Phase B remains unscheduled.
**Amends:** `docs/trucker-platform-prd.md` v1.0 · **Date:** 24 July 2026
**Origin:** proven physical operation (containerized home-cooked food sold at FL truck stops to Uzbek / former-USSR drivers) + direct driver feature requests.

Both governing laws hold unchanged: build law (PRD §6 — foundation complete, modules in order, each behind an F13 flag to its DoD) and design law (design-prd §1 — mobile-first 360×800, tokens only, §22 protocol, never improvise).

---

## E0. Driver-request gap analysis

Requests received from drivers, checked against the platform as of HANDOFF-069:

| # | Request | Status | Where / what's missing |
|---|---|---|---|
| 1 | Driver registration (truck, plate, MC/DOT) | **~90% built** | F1 `DriverProfile` has MC/DOT + FMCSA verification (mig. 0025), truck length/height/weight, trailer + equipment type. **Missing:** license plate, unit number, optional VIN → §E2 |
| 2 | Parking reservation (owner + driver) | **BUILT** | M6 end-to-end: driver booking, owner listings, F7 owner payouts, OwnerPortalSurface. Activation gated on PRD §17 Q5 (damage-coverage insurance) + payment partner — business steps, not build |
| 3 | Truck navigation / maps | **Partial — deliberate** | M1 map is live over real national data. Turn-by-turn is explicitly OUT by M1-FR8 (deep-link handoff to external nav, no in-house routing). Reversing that is a major decision → §E4-Q9. Not in M13 scope |
| 4 | Weigh stations / rest areas / truck stops / parking | **Schema built, data partial** | `FacilityType` already covers all four (+ scale, fuel, repair, composite). NTAD/OSM/TPIMS cover parking, stops, rest areas. **Missing:** weigh-station ingestion source, richer OSM tag mapping → §E3 |
| 5 | Service centers (repair / tire / wash) with vendor access | **Schema partial, vendor side NEW** | `repair` kind exists; wash/tire granularity missing → §E3. Vendor-side access is new → M13-FR7/FR8 |
| 6 | Vendors can run promotions | **NEW** | → M13-FR6 |
| 7 | Driver feedback (open/closed, full/empty) | **BUILT** | F10 crowd beliefs exactly: parking fullness (crowd + TPIMS authoritative), distinct-driver counting, freshness labels (§11.7 honesty) |

Net-new work = **M13** (vendor network: food vendors + service-center vendors, promotions, vendor portal) + two small extensions (**E2** equipment fields, **E3** facility coverage) + one owner decision (**routing**, E4-Q9).

---

## E1. M13 — Vendor Network

### E1.1 Concept

A **vendor** is a person or business that serves drivers *at or near* F2 facilities: mobile food operators (the founding case) and fixed service centers (repair, tire, wash). M13 makes vendors discoverable on the map drivers already use — schedules, live presence, promotions, reviews — in all six launch locales (`en es pa ru uz so`), which already match the founding community.

**M13 is discovery-first.** Phase A (this spec) publishes information and processes **zero food/service payments** — the platform sells nothing and takes no cut, keeping it legally a directory while informal vendors formalize. Phase B (pre-order/prepay, flagged separately, NOT in this build) activates per-vendor only when that vendor's license documents are verified on file, using the existing F7 ledger + payment-partner seam (M6/M7 pattern). Driver pays $0 forever — unchanged; eventual monetization is vendor-side (Phase B take rate, promotion placement), mirroring M6/M7 economics.

### E1.2 Actors & roles

- **Driver** — existing F1 account; consumes discovery, confirms presence, reviews.
- **Vendor** — NEW account role via the F1 pluggable registry (same account model, `vendor` role). One vendor account may have multiple members (owner + helpers).
- **Platform admin** — F14: vendor moderation, verification review, promotion abuse handling.

### E1.3 Functional requirements

**M13-FR1 — Vendor identity & verification tiers.**
Vendor profile: display name, type (`food_mobile` | `service_center`), cuisine/service categories, languages spoken, halal-sourcing declaration (free-text supplier disclosure; formal cert upload optional). Verification ladder: `unverified` → `documents_on_file` (business license / permit / insurance uploaded via F6, admin-reviewed in F14) → `verified`. Tier is displayed to drivers with the same honesty discipline as §11.7 — never imply inspection that didn't happen. Phase B is hard-gated on `verified`.

**M13-FR2 — Appearances & schedules (food vendors).**
An *appearance* = vendor × F2 facility × time window × offering list (menu item, price shown as information only, portion count optional). One-off and weekly-recurring schedules; publish / update / cancel (cancellation notifies subscribed drivers). `property_approved` boolean per vendor×facility, set when the vendor attests written permission from the property — approved appearances rank above unapproved in discovery.

**M13-FR3 — Map & corridor discovery (drivers).**
Facility pins in the M1 overlay carry a food badge when an appearance is active or upcoming today (same enrichment pattern as parking availability / fuel price). "Food" preset chip filters the overlay (existing PresetChips component). Facility card gains a vendor section: who, when, menu, languages, verification tier, distinct-driver confirmations — ordered and pruned per the §E1.9 quality laws. M8 corridor view surfaces appearances ahead on the active route ("Osh 40 mi ahead · Love's exit 341 · until 9pm"). Service-center vendors surface through their claimed facility (FR7) under the existing pin/card model.

**M13-FR4 — Live crowd confirmation.**
New F10 signal types: `vendor_present` (he's here / not here) and `vendor_sold_out`. Standard belief pipeline: distinct-contributor counting, freshness labels, decay. Vendor's own "I've arrived / sold out" acts as an authoritative-style submission attributed to the vendor, never counted as "N drivers" (§11.7).

**M13-FR5 — Vendor reviews.**
M2 review pattern scoped to vendors: rating + short text, one per driver per vendor per 7 days, moderated via F14. Displayed with distinct-reviewer counts.

**M13-FR6 — Promotions.**
A promotion = vendor × text offer × validity window × facility scope (their appearances or claimed facility). Rendered on the facility card and vendor sheet. Push delivery ONLY as a new opt-in notification class (§E1.7); hard anti-spam laws: max one vendor push per driver per day, only for facilities on the driver's active route/corridor or favorites, quiet-hours respected, one-tap mute per vendor. Promotions are free in Phase A (growth); paid placement is a Phase B / §E4-Q10 decision.

**M13-FR7 — Service-center claiming.**
A `service_center` vendor claims an existing F2 facility of kind `repair` (or E3's new kinds) via document check (business name match, admin-reviewed). Claimed facility gains: verified hours, service list (tires, wash, mobile repair, towing), phone/callout, promotions. Unclaimed service facilities remain plain POIs.

**M13-FR8 — Vendor portal.**
Web-first portal surface (design-prd §18 pattern, alongside owner/admin/fleet portals): profile + documents, schedule management, promotion management, appearance analytics (views, confirmations, review summary). Mobile-usable but not the driver app.

**M13-FR9 — Phase B stub (build seams only).**
Pre-order + prepay per appearance portion; F7 double-entry (driver payment → vendor payable − platform take), payment-partner seam, pickup codes (M7 pump-code pattern). NOT built now beyond clean seams: no order model, no money movement. Separate flag `m13_orders`, activation gated on FR1 `verified` + payment partner + owner go.

### E1.4 Data model (schema `m13`)

- `vendor` (id, account_id owner, type, name, categories[], languages[], halal_disclosure, verify_status, created/updated)
- `vendor_member` (vendor_id, account_id, role)
- `vendor_document` (vendor_id, f06 document ref, kind: license | insurance | halal_cert, review_status)
- `appearance` (id, vendor_id, facility_ref → F2, starts_at, ends_at, recurrence rule nullable, status: scheduled | live | done | cancelled, property_approved)
- `offering` (appearance_id, name, price_cents informational, portions nullable)
- `promotion` (id, vendor_id, text, starts_at, ends_at, scope, status)
- `vendor_review` (vendor_id, account_id, rating, text, created_at)
- F10: new `SignalType.vendor_present`, `SignalType.vendor_sold_out` (foundation enum addition — additive, no F10 rework)

Boundaries: M13 imports `foundation.*.public` + earlier modules' public only (M1 map enrichment via the F11/M1 composition point, M2 review pattern is replicated not imported laterally, M8 corridor via its public interface). import-linter contract added for m13.

### E1.5 API (driver + vendor)

Driver: `GET /vendors/appearances?bbox=` (feeds map badges), `GET /vendors/{id}` (sheet), `POST /vendors/{id}/confirm` (present / sold-out → F10), `POST /vendors/{id}/review`, corridor inclusion via existing M8 endpoint payload.
Vendor: `POST/PATCH /vendor/profile`, `/vendor/documents`, `/vendor/appearances` CRUD, `/vendor/promotions` CRUD, `GET /vendor/analytics`.
Admin (F14): vendor list, verification review queue, promotion/report moderation.

### E1.6 Driver UI (design-prd §22.3 DoD applies in full)

- Map: food badge on pins + "Food" preset chip (existing components/tokens — no new visual classes).
- Facility card: vendor section (schedule line, menu, verification tier, confirmations, review count).
- Vendor sheet (BottomSheet pattern): full menu, schedule, languages, halal disclosure, reviews, mute control.
- More → "My equipment" additions per §E2; vendor discovery settings (opt-in food alerts).
- Offline (F12): today's appearances for snapshot region cached; confirmations queue offline like all F10 submissions.
- DRIVING state: vendor alerts render as one-line audio summaries only (§13.4); no interactive prompts.
- All strings ×6 locales + pseudo-locale; CI completeness enforced as always.

### E1.7 Notifications — §23 proposals required (owner approval before build)

- **E-D1:** new notification class `vendor_alert` (opt-in only, default OFF; promotion + appearance-cancelled events; anti-spam laws of FR6 are part of the class definition).
- **E-D2:** map badge + "Food" preset chip composed from existing tokens/components — logged as composition, no new visual class expected; if any new token proves necessary, STOP per §22.
- **E-D3:** vendor portal added to the §18 portal family (fourth web portal).

### E1.8 Definition of Done (module, PRD §7.16 style)

All FRs behind flag `m13_vendor` (default OFF) · tests alongside every FR (unit + API + vitest; e2e extends the full-platform day: a vendor schedules → driver discovers on corridor → confirms → reviews) · six locales + pseudo-locale pass · offline behaviors verified · DRIVING policy verified · a11y pass · import-linter green with the new contract · zero payment code paths reachable in Phase A · every §E1.9 quality law covered by an automated test · honesty labels reviewed against §11.7 · admin moderation surfaces live · seed: founding FL vendor as vendor #1 (real), plus DEV_SEED demo vendor (is_dev pattern).

### E1.9 Marketplace quality laws — the "denoised" discipline (binding, same force as design-prd laws)

The food/vendor section must read as a professional marketplace, not a classifieds board. These laws are enforceable requirements; each ships with a test.

- **Q-1 No dead content, ever.** Appearances auto-expire at window end; a `live` appearance with a sustained crowd "not here" belief flips to lapsed and leaves the map. A vendor with no published appearance in 28 days leaves discovery (profile persists; reactivates on next publish). The map never shows a vendor a driver cannot actually buy from tonight or this week.
- **Q-2 Reliability is public and load-bearing.** Show-up rate = crowd-confirmed appearances ÷ published appearances, displayed on the vendor sheet ("shows up 19 of 20") and weighted into ranking. Repeated no-shows demote automatically; three consecutive unconfirmed no-shows suspend publishing pending F14 review. No-show accountability is what makes pre-driving-detours trustworthy.
- **Q-3 Deterministic, incorruptible ranking.** Discovery order: live-and-confirmed > live > upcoming-today > this-week; ties broken by verification tier, property approval, reliability, then distance. **Promotions never reorder organic results** — promoted content is visually labeled and slotted, never blended. Pay-to-rank in discovery is constitutionally out (same spirit as the fuel-label honesty pass, §11.7).
- **Q-4 Listing completeness floor.** An appearance cannot publish without: facility, time window, ≥1 offering with price, and vendor profile complete (languages, halal disclosure answered — "none" is a valid answer, blank is not). Photos optional but format-governed (food only, no text-in-image per design-prd 12.5, size-normalized).
- **Q-5 One canonical vendor.** Dedupe at registration (phone/account/name+metro blocking, F2 pipeline pattern); duplicates merge, never coexist. A driver never sees the same cook twice under two names.
- **Q-6 Driver-side noise budget.** Facility card shows max 2 vendors (rest behind "all vendors" in the sheet); corridor surfaces max 3 food items per session; `vendor_alert` caps per FR6 (≤1/day, route-relevant, opt-in, quiet hours). The section must never make the core map louder — food enriches pins, it does not decorate the canvas.
- **Q-7 Clean empty states.** No vendors in view → the section simply doesn't render (no "nothing here yet!" filler on the card); the Food preset chip with an empty viewport shows one quiet line + "suggest a cook" affordance feeding the vendor-recruitment loop.
- **Q-8 Moderation SLA.** Reported listing/review → hidden-pending within the F14 queue, resolved ≤72h; repeat-offender vendors suspended. Trust is the product.

DoD addition: every Q-law carries at least one automated test (expiry, demotion, ranking determinism, publish validation, dedupe, caps, empty-state render).

### E1.10 Metrics

Adoption: weekly appearances published, appearance→confirmation rate, distinct drivers confirming, vendor retention (4-week), driver opt-in rate to `vendor_alert`. North-star note: Driver Dollars Delivered is NOT credited from food (no verifiable saving in Phase A); M13 carries its own counter ("meals connected") until Phase B produces real ledger events.

---

## E2. F1 extension — equipment registration (driver request #1)

Add to `DriverProfile` (migration 0031): `plate` (string, state + number), `unit_number`, `vin` (optional, format-validated only — no VIN decode service in v1). Surfaced in More → profile/equipment alongside existing truck dims. No verification claims made (honesty: "self-reported"). Rationale: parking owners (M6) and service vendors (M13-FR7) both benefit from plate/unit on bookings/callouts; fields are additive, no rework.

## E3. F2 extension — facility coverage (driver requests #4, #5)

1. **Weigh stations:** add ingestion source (state DOT / FHWA lists + OSM `amenity=weighbridge`-family tags) into the existing F2 pipeline (staging → dedupe → confidence). Kind `weigh_station` already exists.
2. **Service granularity:** extend OSM tag mapping to populate `repair`; add kinds `truck_wash` and `tire_shop` (enum addition + mapping) OR service-tag attributes on `repair` — implementer proposes in plan, owner picks (E4-Q12).
3. Both ride the established ingest discipline: fixtures in CI, live pulls via make targets/worker flags only.

## E4. New PRD §17 entries (owner decisions)

9. **Truck routing/navigation:** keep M1-FR8 deep-link law vs license truck-attribute routing (Mapbox/HERE truck profiles — recurring cost, major scope). Driver-requested; not blocking M13.
10. **Promotion economics:** free forever vs paid placement at scale (vendor-side revenue; never driver-side).
11. **Property permission policy:** is `property_approved` attestation sufficient, or require uploaded written consent for ranked placement? (durability + platform posture).
12. **Service-center taxonomy:** new kinds vs attribute tags (E3.2).
13. **Phase B trigger:** criteria to open `m13_orders` (N verified vendors? payment partner signed? per-state legal review?).

## E5. Build-order amendment & sequencing

PRD §6 module list extends to **M13** (after M12, same one-continuous-build law, own flag, own DoD). Proposed sequencing: **Session A** — E2 + E3.2 quick extensions + M13 core (FR1–FR4, driver map surfaces); **Session B** — FR5–FR8 (reviews, promotions, claiming, portal) + e2e + seed; the HANDOFF-069 quick-wins (crowd fuel nudge, points cooldown, TPIMS states) either precede Session A or fold into it — owner's call at plan approval. Phase B (FR9) is explicitly NOT scheduled.

---

*End of Extension E1. On approval, the implementing session logs §23 entries E-D1..E-D3, appends §17 Q9–Q13, renumbers the module worklist, and proceeds plan-first as always.*
