# HANDOFF-018 — M6 Parking Marketplace (backend + API + booking UI)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–F15 complete. **M1–M6 built** (backend + API + UI). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 (Foundation DoD), 012–017 (M1–M5).

---

## 1. What now exists and passes (delta since HANDOFF-017)

**New: M6 — Parking Marketplace** (the transaction layer) + the **Map Book flow**. **Stripe/Connect deferred** to the F7 gateway seam per owner ("strip … can be deferred, use best judgement"); the F7 double-entry ledger is the source of truth, so the booking→payout economics are real and tested *now*, and the card charge / Connect payout wire in at activation.

### M6 backend — `api/app/modules/m06_parking` (schema `m06`, PRD §8.6)
Composes foundation publics **+ `m01_map.public`** (the closing loop) — 29 contracts KEPT (m06→m01.public verified allowed).
- **Listings** (M6-FR1): `create_property` spawns an **F2 `parking_property` facility** (map-native), `add_spot` with per-night pricing. Vetting flag; no residential is a listing-policy gate (posture below).
- **Instant booking** (M6-FR2): overlap guard → nights/price/take math → **balanced F7 entry** (debit cash_clearing `price` / credit owner_payable `owner_payout` / credit platform_revenue `take`). The **17.5 % take is baked into the owner side** so the driver sees **one transparent price** (design-prd §21.8 / line 344). Gateway is an optional `PaymentGateway` arg (Stripe seam, unused until activation).
- **Closing loop** (M6-FR3): `closing_loop` imports `m01.map_overlay` (Tonight preset); when a nearby public lot reads `full`, surface `bookable_near` inventory (F2 `nearest` → active spots).
- **Geofence check-in/out** (M6-FR4): `check_in` verifies F3 `is_present` at the property facility; `is_overstay` clock.
- **Refund engine** (M6-FR7): full refund ≥24 h before start, else 50 %; posts the **reverse F7 entry** and flips state to `refunded`.
- F13 flag `m06_parking` **gated on `refund_policy` + `damage_liability_posture`** + F14 admin view "Bookings & Payouts".

### M6 HTTP API + Map Book flow UI
- API: `GET /parking/bookable`, `GET /parking/closing-loop`, `POST /parking/book` (409 on unavailable).
- **Facility card** gains a contextual lead action (§227): a bookable `parking_property` leads with **"Book spot — $XX"** naming the take-inclusive nightly (§12.2), demoting Navigate to secondary.
- **BookingSurface** (`/book/:spotId`) — a **full-screen linear checkout** (NAV-3, not a sheet): one question (nights stepper) → **the one final price** in Mono/tabular ledger-green (§6.2 T-2 / §9) = nightly × nights, **no fees at confirm**. The confirm verb **persists into the confirmation** ("Book spot — $X" → "Booked", §12.2). Fixture-safe: an unauthenticated/offline confirm still resolves.

### Verified this session (in compose)
- `alembic upgrade head` through **`0019`**; up→down→up verified (m06 schema + `booking_state` enum round-trip clean).
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 203 passed** (was 192; +7 M6 module +4 M6 API).
- UI: **vitest 55 passed** (was 52; +3: bookable card CTA, checkout one-final-price, Booked confirmation) · `vite build` clean · six-locale completeness at **62 keys**.

## 2. Decisions made (append to Decision Log)

64. **Stripe/Connect deferred; the F7 ledger is the truth (owner-authorised).** Booking posts a balanced double-entry (cash → owner_payout + platform_take) **now**; `book(..., gateway=None)` is the seam where the Stripe charge + Connect payout attach at activation. The take→payout loop is provable in test without any payment provider. DoD for activation stays "test-mode charge→payout parity", now a wiring task not a build one.
65. **Take is baked into the owner side → one driver-facing price** (design-prd §21.8 / anti-pattern 8, line 344). `owner_payout = price − take`; the driver's `price_cents` is the whole story. The checkout shows exactly one figure and adds nothing at confirm.
66. **Booking checkout is a full-screen linear flow, not a sheet** (design-prd NAV-3 lists booking checkout among the reserved full-screen pushes). The map card CTA is the NAV-5 cross-link *into* it; sheets stay for glance/quick-action.
67. **M6 owns an F2 facility per property** so listings are map-native from day one (the closing loop and `bookable_near` both key off F2 `nearest`), while booking/pricing/state live in `m06`. Clean schema-per-module; M1 stays oblivious to M6 (import direction preserved).
68. **`chore(format)` split from the feature commit.** The container's ruff picked up newer rules (blank-line-after-docstring + long-line reflow) on files committed earlier; normalized in one no-logic commit so the M6 diff stays reviewable.

## 3. Exact next task

**Continue modules in order → M7.** Plan **M7 — Fuel** (PRD §8.7), plan-first — the savings layer:
- **Net-price intelligence** (M7-FR1): branded cash/credit + discount-aware net price per station; the map Fuel preset already reserves the slot.
- **Fuel-stop optimization** (M7-FR2): cheapest viable stop within range/off-route tolerance along the corridor (composes M1 corridor + F2 geo).
- **Discount / loyalty program hooks** (seam), **price crowd-sourcing** via F10 (fuel_price signal already exists), **fleet fuel policy** stubbed (M12).
- Backend `m07_fuel` (imports foundation + earlier module publics as needed). F13 flag. Then UI — the **Fuel preset** gains real net-price figures on pins + a station detail; the facility card fuel figure is already Mono-ready.

**Fold-in follow-ups (owner priority):** F1 **login UI** (browser → live API), **Mapbox token**, active-load API, **offline read-cache (F12)** — now wanted by Map/Docs/Booking alike; M5 condition-capture + incident UI flows; M6 **owner portal** (web §18) + **two-way reviews** (M6-FR6, F10/F14) are deferred M6 surfaces to revisit.

## 4. Blockers / owner questions

1. **Stripe/Connect account structure + take rate** (M6) — needed before *activation* only; built behind F13 gates + the F7 `PaymentGateway` seam. Default take modelled at **17.5 % (1750 bps)**, F13-config-overridable — **confirm the rate.**
2. **M6 refund-policy + damage/liability posture** — the two F13 activation gates; owner text needed (also drives the "no residential" listing rule).
3. **Mapbox token** — live map tiles (M1); the Book flow rides the same map.
4. **Collection-partner + legal sign-off** — F13 gates to activate M3/M4.
5. **Locale wording** — new M6 strings (8 keys × 6 locales) native review pending (F15); completeness gate green at **62 keys**.
6. Standing seams: timestamping/PDF (F4), Twilio/FCM/email (F8), model keys + budgets + embedding dim (F9), MinIO bucket (F6), brand name.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 (Map · `/facility/:id` · **`/book/:spotId`** · `/load` The Meter · `/money` · `/docs`) · API http://localhost:8008 (`/docs`, `/auth/*`, `/map/*`, `/facility/*`, `/detention/*`, `/accessorial/*`, `/protection/*`, **`/parking/*`**) · MinIO :9019 · Mailpit :8038. Admin: `admin@longhaul.local` / `longhaul-admin-dev`.
Suite: **pytest 203 · vitest 55 · 29 contracts · ruff clean**, migrations through `0019`.

## 7. Build progress

**Common Ground F1–F15: complete.** Modules: **M1, M2, M3, M4, M5, M6 done.** Next: **M7** → M8 → … → M12. All five driver tabs (Map/Load/Money/Docs/More) have real surfaces except More; the Map now carries a full Book→checkout→confirm flow.

## 8. Commits this session (local only, never pushed)

`8ca3af4` HANDOFF-017 → `d884245` chore(format) normalize under updated ruff → `7488dd3` M6 backend+API → `bab1bdd` M6 booking UI (+ this handoff). **52 commits** on `main`.

*— End of session. Next: plan M7 (Fuel — net-price intelligence, stop optimization along the M1 corridor), plan-first. M6 payment activation (Stripe/Connect) is a wiring task pending owner take-rate + posture, not a build.*
