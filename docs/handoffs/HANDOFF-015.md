# HANDOFF-015 — M3 Detention Tracker & Recovery (backend + API + The Meter/Load UI)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–F15 complete. **M1 + M2 + M3 built** (backend + API + UI). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 (Foundation DoD), 012–014 (M1/M2).

---

## 1. What now exists and passes (delta since HANDOFF-014)

**New: M3 — Detention Tracker & Recovery** (the differentiator) + **The Meter** (the signature UI element).

### M3 backend — `api/app/modules/m03_detention` (schema `m03`, PRD §8.3)
Composes foundation publics only (29 contracts KEPT).
- **Detention clock math** (the money core, exact integer cents): free-time countdown from the contractually-correct **trigger** (appointment vs arrival) → accrual at the load's rate. Billing rounding a config seam. Exhaustively tested.
- **Evidence accrual** — fills the F5→F4 seam (decision #20): F3 geofence events → the stop's **F4 hash-chained log**; idempotent, chain-valid.
- **Claim pack on EXIT** (M3-FR5): compute → F4 evidence pack → *invoice mode*: **F7 receivable** in the driver's name + **F8** contract-citing counterparty email + F5 counterparty claim-count; *company-driver mode* (M3-FR9): pack only, **no invoice**.
- **Counterparty notices** (M3-FR3/FR4): pre-detention 30-min threshold + detention-start (F8). **Dunning schedule** day 3/10/21 (M3-FR6). **Escalation seam** (M3-FR7). Every completed stop already feeds M2 dwell via F3 (M3-FR10).
- **F13 flag `m03_detention` behind validation gates** (legal sign-off + collection-partner agreement — cannot activate until satisfied).

### M3 HTTP API — `app/api/m03_detention`
`POST /detention/start`, `GET /detention/{id}/clock`, `POST /detention/{id}/pack` (F8 gateway seam). New F5 reads: `get_stop`, `get_counterparty`.

### The Meter + Load tab UI
- **THE METER** (design-prd §9) — the product's signature visual, built once in `ui/core` on tokens (Q-4): label + type-meter **Mono tabular** figure + status, color by variant (countdown text-1 / last-30-min marker / accruing ledger / disputed flare). The only animated, Mono-set hero element.
- `core/meter.js`: `formatClock`/`formatMoney`, `computeDetentionState` (**mirrors the backend clock** so The Meter ticks live in-app between syncs), `meterVariant`.
- **Load tab** (design-prd §10.2) replaces the placeholder: live Meter card (fixture stop **accruing → money ticking up**), stop context, evidence checklist, state-dependent CTA; **DRIVING collapses to a Meter-only glance**. Fixture-backed pending the active-load API.

### Verified this session (in compose)
- `alembic upgrade head` through `0016`; up→down→up verified.
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 172 passed** (Common Ground 136 + M1 14 + M2 10 + M3 module 11 + M3 API 1).
- UI: **vitest 49 passed** (contrast both themes, six-locale completeness at 41 keys, pseudo-locale, state/presentation/i18n/meter logic, components incl. The Meter + Load surface).

## 2. Decisions made (append to Decision Log)

54. **Detention clock is a pure function** (`compute_detention`) mirrored in JS (`computeDetentionState`) so the money math is identical on server and client; The Meter ticks live client-side, the server is authoritative on sync. Billing = prorated `round(seconds/3600 * rate)`; rounding convention → F13 config.
55. **Evidence accrual is M3's job** (finally wiring decision #20): F3 events → F4 records, idempotent by `event_id` in the record payload. The evidence pack's hash chain stays valid.
56. **Invoicing gated by authority** (F1 `can_invoice`): own-MC/leased → invoice mode (receivable in driver's name); company driver → evidence-only pack for their carrier. Same capture either way (PRD §8.3).
57. **The Meter is the sole signature element** (design-prd §9) — one component, tokens-only, reused wherever detention money/time appears (Load card now; Money tab, notifications, PDF header, voice later). Nothing else on a screen competes with it.

## 3. Exact next task

**Continue modules in order → M4.** Plan **M4 — Accessorial Recovery Suite** (PRD §8.4), plan-first:
- Same evidence-and-invoice rail extended to **TONU** (M4-FR1), **layover** (M4-FR2), and **lumper reimbursement** (M4-FR3, receipt photo → F6 OCR → invoice). Accessorial terms extraction from rate cons (F5/F9) with driver-confirm + missing-terms warning (M4-FR4). Unified **"Money Owed"** view (M4-FR5) over M3+M4 receivables.
- Reuses the **M3 pipeline** (M4 imports `m03.public`) — TONU/layover invoices flow through M3's claim/pack/receivable machinery. Keep the claim-type registry + templates independently testable (why M4 is its own module).
- Backend `m04_accessorial` → then UI (the **Money tab**, design-prd §10.3 — receivables list with status pills + aging in Mono, per-receivable "next action").

**Fold-in follow-ups (owner priority):** F1 **login UI** (browser → live API for M1/M2/M3), **Mapbox token**, active-load API (so the Load tab uses live detention, not fixtures), full 10-aspect review form, offline read cache.

## 4. Blockers / owner questions

1. **Mapbox token** — live map tiles (M1).
2. **Collection-partner agreement + legal sign-off** — the F13 **validation gates** for activating M3 (and M4). Building behind the gates; activation needs these.
3. **Locale wording** — pa/uz/so/ru/es incl. new M3 strings, native review pending (F15). Completeness gate green (41 keys).
4. Standing seams: timestamping/PDF (F4), Stripe/Connect + points rate (F7), Twilio/FCM/email (F8), model keys + budgets + embedding dim (F9), MinIO bucket (F6), brand name.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 (Map · `/facility/:id` · **`/load` = The Meter**) · API http://localhost:8008 (`/docs`, `/auth/*`, `/map/*`, `/facility/*`, `/detention/*`) · MinIO :9019 · Mailpit :8038. Admin: `admin@longhaul.local` / `longhaul-admin-dev`.
Suite: **pytest 172 · vitest 49 · 29 contracts · ruff clean**, migrations through `0016`.

## 7. Build progress

**Common Ground F1–F15: complete.** Modules: **M1, M2, M3 done.** Next: **M4** → M5 → … → M12.

## 8. Commits this session (local only, never pushed)

… `c191a12` HANDOFF-014 → `76b7a35` M3 backend+API → `c193907` M3 UI (The Meter) (+ this handoff). ~44 commits on `main`.

*— End of session. Next: plan M4 (Accessorial Recovery — TONU/layover/lumper on the M3 rail + the Money tab), plan-first.*
