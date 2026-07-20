# HANDOFF-017 — M5 Protection & Document Wallet (backend + API + Docs tab)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–F15 complete. **M1–M5 built** (backend + API + UI). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 (Foundation DoD), 012–016 (M1–M4).

---

## 1. What now exists and passes (delta since HANDOFF-016)

**New: M5 — Protection & Document Wallet** (the shield to M3/M4's sword) + the **Docs tab**.

### M5 backend — `api/app/modules/m05_protection` (schema `m05`, PRD §8.5)
Composes foundation publics only (29 contracts KEPT); **owns its own F4 logs so it never writes F5's tables**.
- **On-time proof** (M5-FR1): geofence ENTER vs appointment window → within-window flag + F4 proof artifact + opt-in F8 "checked in at HH:MM" counterparty notice (sent only when actually on time).
- **Cargo-condition protocol** (M5-FR2): guided sequence (trailer/seals/blocking/reefer) → **hash-chained F4 photos** (chain-valid), prompt stored in EXIF.
- **Document wallet** (M5-FR3): typed docs via F6 with expiry status (ok/expiring/expired via the F6 engine); **inspection mode** filters to credential types (CDL/med-card/insurance/permit).
- **Incident capture** (M5-FR4): generic F4 evidence flow → shareable pack. **Protection summary** (M5-FR5): documented vs missing per stop.
- F13 flag `m05_protection` + F14 admin view.

### M5 HTTP API + Docs tab UI
- API: `POST /protection/on-time|incident`, `GET /protection/wallet|inspection|summary/{stop}`.
- **Docs tab** (design-prd §10.4) replaces the placeholder: **Inspection-mode button** (top, 56 dp, ≤2 taps from cold start) → credential-only sheet; **expiring-soon strip** (marker/flare pills); **document grid by type**; capture chip. Doc-type acronyms (CDL/BOL/POD) stay English (§12.3). Fixture-backed pending live `/protection/wallet`.

### Verified this session (in compose)
- `alembic upgrade head` through `0018`; up→down→up verified.
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 192 passed** (Common Ground 136 + M1 14 + M2 10 + M3 12 + M4 9 + M5 module 8 + M5 API 3).
- UI: **vitest 52 passed** (contrast both themes, six-locale completeness at 54 keys, pseudo-locale, meter/presentation/state/i18n, components incl. Docs tab).

## 2. Decisions made (append to Decision Log)

61. **M5 owns its F4 logs** (create_log per proof/capture/incident) rather than writing the F5 stop's `evidence_log_id`. Keeps the F5 boundary clean; multiple protection logs per stop is fine (F4 `stop_ref` is a soft link). On-time notice only fires when actually on time — no false claims.
62. **The evidence engine is dual-use** (PRD §5 shield-and-sword): the same F4 hash-chain that powers M3/M4 claims now powers M5 protection (on-time proof, cargo condition, incidents). One engine, opposite intents.
63. **Inspection mode is credential-scoped + fixture-fast**: filters to CDL/med-card/insurance/permit; the UI button is ≤2 taps from cold start (design-prd §10.4). Offline read-cache is the remaining client piece (F12).

## 3. Exact next task

**Continue modules in order → M6.** Plan **M6 — Parking Marketplace** (PRD §8.6), plan-first — the transaction layer:
- **Listings** (M6-FR1): property onboarding (vetting, no residential), spot inventory, pricing, amenities, photos, rules — the P4 supply side.
- **Instant booking + payment** (M6-FR2): payment captured on booking (F7 Stripe seam), platform take deducted, owner payout via Connect (seam).
- **The closing loop** (M6-FR3): when M1 shows public lots Full nearby, surface bookable inventory in the same view (cross-link to M1).
- Check-in/out via geofence (M6-FR4, F3). Owner portal (M6-FR5, web §18). Reviews both ways (M6-FR6, F10/F14). Cancellation/refund engine (M6-FR7). Fleet hooks stubbed (M6-FR8, M12).
- Backend `m06_parking` (imports m01 public for the closing loop + foundation). F13 flag gated on refund-policy + damage/liability posture. Then UI — booking surfaced in the Map's facility card (M6-FR3) + a booking flow.
- **Note:** M6 introduces **Stripe/Connect** for the first time (F7 `PaymentGateway` seam) — booking→payout loop in test-mode parity is the DoD. Owner input on Stripe account structure + take rate needed before *activation*, not build.

**Fold-in follow-ups (owner priority):** F1 **login UI** (browser → live API), **Mapbox token**, active-load API, offline read-cache, condition-capture + incident UI flows (M5 has backend; UI capture flows are a follow-up).

## 4. Blockers / owner questions

1. **Mapbox token** — live map tiles (M1).
2. **Collection-partner + legal sign-off** — F13 gates to activate M3/M4.
3. **Stripe/Connect structure + take rate** (M6) and **refund/damage-liability posture** — owner input before M6 activation; building behind F13 gates + the F7 gateway seam.
4. **Locale wording** — new M5 strings native review pending (F15); completeness gate green (54 keys).
5. Standing seams: timestamping/PDF (F4), Twilio/FCM/email (F8), model keys + budgets + embedding dim (F9), MinIO bucket (F6), brand name.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 (Map · `/facility/:id` · `/load` The Meter · `/money` · **`/docs`**) · API http://localhost:8008 (`/docs`, `/auth/*`, `/map/*`, `/facility/*`, `/detention/*`, `/accessorial/*`, `/protection/*`) · MinIO :9019 · Mailpit :8038. Admin: `admin@longhaul.local` / `longhaul-admin-dev`.
Suite: **pytest 192 · vitest 52 · 29 contracts · ruff clean**, migrations through `0018`.

## 7. Build progress

**Common Ground F1–F15: complete.** Modules: **M1, M2, M3, M4, M5 done.** Next: **M6** → M7 → … → M12. (All five driver tabs — Map/Load/Money/Docs/More — now have real surfaces except More.)

## 8. Commits this session (local only, never pushed)

… `cd459e6` HANDOFF-016 → `e936abe` M5 backend+API → `12a7333` M5 UI (Docs tab) (+ this handoff). ~52 commits on `main`.

*— End of session. Next: plan M6 (Parking Marketplace — listings, instant booking, the closing loop; first Stripe/Connect seam), plan-first.*
