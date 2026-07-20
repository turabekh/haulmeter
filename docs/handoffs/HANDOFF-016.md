# HANDOFF-016 — M4 Accessorial Recovery Suite (backend + API + Money tab)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–F15 complete. **M1–M4 built** (backend + API + UI). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 (Foundation DoD), 012–015 (M1–M3).

---

## 1. What now exists and passes (delta since HANDOFF-015)

**New: M4 — Accessorial Recovery Suite** (TONU/layover/lumper on the M3 rail) + the **Money tab**.

### M4 backend — `api/app/modules/m04_accessorial` (schema `m04`, PRD §8.4)
Reuses the M3 invoice rail (imports `m03.public`); composes foundation publics only (29 contracts KEPT).
- **Extracted `M3.open_receivable`** (F7 receivable + F8 counterparty notice + F5 claim-count) as the shared rail — M4's claims flow through the same machinery, kept independently testable (why M4 is its own module, not M3 scope-creep).
- **TONU** (M4-FR1): rate-con terms → tonu receivable.
- **Layover** (M4-FR2): **overnight-dwell detection** (F3 ENTER/EXIT crossing midnight) → layover receivable; same-day dwell rejected.
- **Lumper** (M4-FR3): receipt → **F6 store** (`lumper_receipt`) → **F9 OCR** amount → lumper reimbursement receivable (tracked separately from earnings, `is_reimbursement`).
- **Terms check** (M4-FR4): rate-con silent-on-X warning. **Money Owed** (M4-FR5): unified M3+M4 receivables with state + aging (new **`F7.list_receivables`**).
- F13 flag `m04_accessorial` + F14 admin view + `lumper_ocr` F9 prompt.

### M4 HTTP API + Money tab UI
- API: `POST /accessorial/tonu|layover|lumper`, `GET /accessorial/owed`.
- **Money tab** (design-prd §10.3) replaces the placeholder: month summary in **The Meter treatment** (recovered total, ledger) + receivables list with **status pills** (state→semantic token) and **aging in Mono**; money always Mono/tabular, never truncated. Fixture-backed pending live `/accessorial/owed`. Trucking jargon (detention/TONU/layover/lumper) stays **English in every locale** (§12.3).

### Verified this session (in compose)
- `alembic upgrade head` through `0017`; up→down→up verified.
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 181 passed** (Common Ground 136 + M1 14 + M2 10 + M3 12 + M4 module 7 + M4 API 2).
- UI: **vitest 51 passed** (contrast both themes, six-locale completeness at 50 keys, pseudo-locale, meter/presentation/state/i18n logic, components incl. Money tab).

## 2. Decisions made (append to Decision Log)

58. **The invoice rail is `M3.open_receivable`, shared by M3 & M4.** F7 receivable + F8 counterparty notice + F5 claim-count in one reusable function. New accessorial types register through it; each module owns its amount computation + claim-type row. F4/F7 receivable kinds (detention/tonu/layover/lumper) were already in the ledger.
59. **Lumper is a reimbursement, not earnings** — flagged `is_reimbursement` in Money Owed so the P&L reads honestly (pass-through vs recovered).
60. **Jargon stays English in the catalog** (design-prd §12.3): detention/TONU/layover/lumper/BOL are the same string in all six locales; only surrounding labels translate. Keeps the glossary discipline in the UI strings.

## 3. Exact next task

**Continue modules in order → M5.** Plan **M5 — Protection & Document Wallet** (PRD §8.5), plan-first — the shield to M3/M4's sword:
- **On-time arrival proof** (M5-FR1): geofence ENTER inside the appointment window auto-fires a timestamped counterparty "checked in at HH:MM" (F8, opt-in) + files the proof artifact (F4) — runs on M3's arming.
- **Cargo-condition protocol** (M5-FR2): guided photo sequences (trailer/seals/blocking/reefer) at pickup + delivery, geotagged/hash-chained (F4).
- **Document wallet** (M5-FR3): CDL/med-card/insurance/permits/rate-cons — typed storage (F6), expiry alerts (F6 engine → F8), offline access, **inspection mode** (≤2 taps from cold start, design-prd §10.4).
- **Incident capture** (M5-FR4) + **protection summary** (M5-FR5).
- Backend `m05_protection` (imports m03 publics + foundation) → then the **Docs tab** (design-prd §10.4 — inspection mode button, expiring-soon strip, document grid).

**Fold-in follow-ups (owner priority):** F1 **login UI** (browser → live API), **Mapbox token**, active-load API (live Load tab), full 10-aspect review form.

## 4. Blockers / owner questions

1. **Mapbox token** — live map tiles (M1).
2. **Collection-partner + legal sign-off** — F13 validation gates to *activate* M3/M4 (built behind them).
3. **Locale wording** — new M3/M4 strings native review pending (F15); completeness gate green (50 keys).
4. Standing seams: timestamping/PDF (F4), Stripe/Connect + points rate (F7), Twilio/FCM/email (F8), model keys + budgets + embedding dim (F9), MinIO bucket (F6), brand name.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 (Map · `/facility/:id` · `/load` The Meter · **`/money`**) · API http://localhost:8008 (`/docs`, `/auth/*`, `/map/*`, `/facility/*`, `/detention/*`, `/accessorial/*`) · MinIO :9019 · Mailpit :8038. Admin: `admin@longhaul.local` / `longhaul-admin-dev`.
Suite: **pytest 181 · vitest 51 · 29 contracts · ruff clean**, migrations through `0017`.

## 7. Build progress

**Common Ground F1–F15: complete.** Modules: **M1, M2, M3, M4 done.** Next: **M5** → M6 → … → M12.

## 8. Commits this session (local only, never pushed)

… `a837caf` HANDOFF-015 → `90537a5` M4 backend+API → `cdf5a67` M4 UI (Money tab) (+ this handoff). ~48 commits on `main`.

*— End of session. Next: plan M5 (Protection & Document Wallet + Docs tab / inspection mode), plan-first.*
