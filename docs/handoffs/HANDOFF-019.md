# HANDOFF-019 — M7 Fuel Savings Network (backend + API + fuel UI)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–F15 complete. **M1–M7 built** (backend + API + UI). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 (Foundation DoD), 012–018 (M1–M6).

---

## 1. What now exists and passes (delta since HANDOFF-018)

**New: M7 — Fuel Savings Network** (the sleeper economics) + the **Fuel net-price map card, pump-code flow, and Money savings row**. **Payment partner deferred** to the F7 gateway seam (same pattern as M6's Stripe); the F7 ledger is the source of truth, so the net-price → spread → settlement economics are real and tested now.

### M7 backend — `api/app/modules/m07_fuel` (schema `m07`, PRD §8.7)
Composes foundation publics **+ `m01_map.public`** (corridor). 29 contracts KEPT. **F7 already ships `fuel_clearing` + `fuel_txn`** — the foundation anticipated M7, so no enum change.
- **Merchant network + station pricing** (M7-FR1): `Merchant` + `StationPricing` per F2 `fuel_station` (gross / driver-discount / **platform-spread** ¢per-gal, network vs crowd `source`). F14 admin view "Fuel Network".
- **Net-price corridor** (M7-FR2): `corridor_fuel` composes `m01.corridor_view(fuel)`, attaches net price, ranks by **net ¢/gal then proximity** — no fabricated deviation-mile coefficient (design-prd §11.7, never fake precision).
- **In-app pump code** (M7-FR3): `issue_pump_code` (network stations only, else `NotAFuelPartner`) → `FuelTransaction`; `settle` posts the **balanced F7 entry** (debit `cash_clearing` net / credit `platform_revenue` spread / credit `fuel_clearing` merchant payable). The take is baked into the owner side so the **driver sees one net price** — no fees/minimums.
- **Driver analytics** (M7-FR4): `driver_analytics` — gallons, spend, **savings-to-date**; IFTA export = M9 hook.
- **Crowd honesty** (M7-FR5): `confirm_price` submits an F10 `fuel_price` signal + syncs non-network gross to the consensus.
- F13 flag `m07_fuel` **gated on `merchant_agreement` + `payment_partner`**.
- **Integer discipline:** gallons stored as `gallons_milli` (thousandths); all money in cents.

### M7 HTTP API + fuel UI
- API: `GET /fuel/corridor`, `GET /fuel/analytics`, `POST /fuel/pump-code` (409 for non-network), `POST /fuel/confirm-price`.
- **Facility card** now leads a fuel-network station with the **NET price + savings pill** and a contextual **"Fuel here"** CTA (§227), Navigate demoted to secondary.
- **FuelSurface** (`/fuel/:stationId`) — a **full-screen linear flow** (NAV-3): net price big in ledger-green Mono, posted gross for contrast, one question (gallons stepper), live "You save" + total; **"Get pump code"** issues the code and shows it big to hold at the pump (payment partner deferred). Fixture-safe offline fallback.
- **Money tab** gains the **fuel savings-to-date row** (design-prd §238 / M7-FR4) in ledger-green Mono.

### Verified this session (in compose)
- `alembic upgrade head` through **`0020`**; up→down→up verified (m07 schema + `price_source`/`fuel_txn_state` enums round-trip clean).
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 214 passed** (was 203; +7 M7 module +4 M7 API).
- UI: **vitest 58 passed** (was 55; +3: fuel net-price card, pump-code flow, Money savings row) · `vite build` clean · six-locale completeness at **72 keys**.

## 2. Decisions made (append to Decision Log)

69. **Payment partner deferred; the F7 ledger is the truth.** `issue_pump_code(..., gateway=None)` is the seam where the payment-partner authorization attaches at activation; `settle` posts the balanced spread entry now. Provable end-to-end without any provider — DoD for activation stays "discounted purchase + settlement reconciliation", now a wiring task.
70. **Spread lives between the merchant discount and the driver discount → one net price.** `net = gross − driver_discount`; `merchant_payable = net − spread`; `platform_revenue = spread`. The driver's figure is the whole story (PRD §8.7, no fees/minimums). Merchant settlement clears through the existing `fuel_clearing` account — no new F7 enum.
71. **Corridor ranks by net price, not a modeled deviation cost.** M7-FR2 says "true cost including deviation miles", but a deviation-mile-to-dollars coefficient would be invented precision (design-prd §11.7). Ranked by net ¢/gal then proximity; a real deviation model waits for M8's routing. Logged as an honest limitation.
72. **Gallons in milli-units** (`gallons_milli`, ×1000) to keep the whole domain integer (money-in-cents discipline extends to volume); the UI divides by 1000 for display.
73. **The map facility card is now a 3-way contextual lead** (Book / Fuel here / Navigate) driven by badge kind (`bookable` → `fuel_net` → default), Navigate always reachable as secondary. One primary action preserved (§Principle 4); the card stays a switch, not a menu.

## 3. Exact next task

**Continue modules in order → M8.** Plan **M8 — Trip Intelligence** (PRD §8.8), plan-first — the first intelligence layer (consumes M1/M2/M3/M6/M7 via their publics; bootstraps on heuristics until data accrues):
- **True-profit load calculator** (M8-FR1): net = revenue − route fuel (**M7 net prices**) − tolls − expected accessorial time-cost from **M2/M3** facility distributions; output rate-per-mile *after* this receiver's dwell history.
- **Appointment-hour optimizer** (M8-FR2): which hour unloads fastest (M2 by-hour dwell).
- **"Where do I sleep tonight" solver** (M8-FR3): HOS input (manual, no ELD) + corridor + live/predicted parking (**M1**) + bookable inventory (**M6**) + fuel plan (**M7**) → ranked stop recommendations.
- Backend `m08_intelligence` (imports foundation + M1/M2/M3/M6/M7 publics). F13 flag. Then UI — likely a Load-tab "true profit" surface + the sleep solver. **Monetization: none directly** (drives claim/booking/fuel attach); it's the core of the M12 data product.

**Fold-in follow-ups (owner priority):** F1 **login UI**, **Mapbox token**, active-load API, **offline read-cache (F12)** (Map/Docs/Booking/Fuel all want it), M5 capture flows; M6 owner portal + two-way reviews; M7 owner portal for merchants (web §18) is a deferred surface.

## 4. Blockers / owner questions

1. **Fuel payment-partner selection + merchant agreements** (M7) — needed before *activation* only; built behind F13 gates + the F7 gateway seam. **Spread ¢/gal is per-station config** (`spread_cents_per_gal`), owner/BD-set per merchant deal.
2. **Stripe/Connect structure + take rate** (M6) and **refund/damage-liability posture** — still open for M6 activation.
3. **Mapbox token** — live map tiles (M1); Book + Fuel flows ride the same map.
4. **Collection-partner + legal sign-off** — F13 gates to activate M3/M4.
5. **Locale wording** — new M7 strings (10 keys × 6 locales) native review pending (F15); completeness gate green at **72 keys**.
6. Standing seams: timestamping/PDF (F4), Twilio/FCM/email (F8), model keys + budgets + embedding dim (F9), MinIO bucket (F6), brand name.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 (Map · `/facility/:id` · `/book/:spotId` · **`/fuel/:stationId`** · `/load` · `/money` incl. fuel-savings row · `/docs`) · API http://localhost:8008 (`/docs`, `/auth/*`, `/map/*`, `/facility/*`, `/detention/*`, `/accessorial/*`, `/protection/*`, `/parking/*`, **`/fuel/*`**) · MinIO :9019 · Mailpit :8038. Admin: `admin@longhaul.local` / `longhaul-admin-dev`.
Suite: **pytest 214 · vitest 58 · 29 contracts · ruff clean**, migrations through `0020`.

## 7. Build progress

**Common Ground F1–F15: complete.** Modules: **M1, M2, M3, M4, M5, M6, M7 done.** Next: **M8** → M9 → … → M12. The Map now carries three contextual deep-link flows (Navigate / Book / Fuel); the Money tab shows recovered + fuel-saved.

## 8. Commits this session (local only, never pushed)

`138552f` HANDOFF-018 → `d1c106f` M7 backend+API → `f015eff` M7 fuel UI (+ this handoff). **55 commits** on `main`.

*— End of session. Next: plan M8 (Trip Intelligence — true-profit calculator consuming M7 fuel + M2/M3 dwell, and the "where do I sleep tonight" solver over M1/M6/M7), plan-first. M7 payment activation is a wiring task pending owner payment-partner + merchant deals, not a build.*
