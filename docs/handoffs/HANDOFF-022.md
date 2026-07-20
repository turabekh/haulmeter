# HANDOFF-022 — M9 Driver Money & Tax Tools (backend + API + DDD UI)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–F15 complete (F1 has driver UI). **M1–M9 built** (backend + API + UI). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 (Foundation DoD), 012–021 (M1–M8 + login UI).

---

## 1. What now exists and passes (delta since HANDOFF-021)

**New: M9 — Driver Money & Tax Tools** (the financial system-of-record + company-driver wedge) + the **Driver Dollars Delivered (DDD)** hero on the Money tab.

### M9 backend — `api/app/modules/m09_money` (schema `m09`, PRD §8.9)
Composes **F6 + F9 + m04 + m07** publics. 29 contracts KEPT.
- **Settlement auditor** (M9-FR1): `upload_settlement` stores a settlement's pay lines; `audit_settlement` reconciles them against the driver's own **GPS-backed receivables** (M3/M4 via `m04.money_owed`, excluding already-recovered), and flags anything **owed-but-unpaid** with the evidence receivable attached. Output is positioned "review with your carrier," never legal advice (PRD §8.9 note). The AI parse of a raw settlement doc is the **F9 seam** (`parse_settlement_lines`, tested via `FakeModelProvider`).
- **Earnings / North Star DDD** (M9-FR4): `earnings_dashboard` = recovered (M3/M4) + fuel saved (M7) + audit-flagged, in one figure.
- **Expense capture-lite** (M9-FR5): `add_receipt` (F6 document) + `expense_summary(year)` by category.
- **Honest seams** (basis surfaced, not fabricated — §11.7): `ifta_summary` (M9-FR2, totals from provided legs; per-jurisdiction split needs state-boundary geometry) and `per_diem_days` (M9-FR3, needs account-wide traces + home base). Both return explicit `basis` markers.
- F13 flag `m09_money` (no external gates — read/compute + upload).

### M9 HTTP API + DDD UI
- API: `GET /money/earnings`, `POST /money/settlements/audit`, `POST /money/receipts`, `GET /money/expenses/{year}`.
- **Money tab** now leads with the **DDD North Star** in Meter treatment (recovered + fuel saved + audit-flagged), with the three streams broken out below in ledger-green Mono (design-prd §238). The fuel savings row folded into this breakdown; the owed receivables list is unchanged.

### Verified this session (in compose)
- `alembic upgrade head` through **`0021`**; up→down→up verified (m09 schema + `discrepancy_status` enum round-trip clean).
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 233 passed** (was 224; +6 M9 module +3 M9 API).
- UI: **vitest 67 passed** (MoneySurface test updated fuel-row → DDD) · `vite build` clean · six-locale completeness at **102 keys**.
- **Live smoke:** authenticated `GET /money/earnings` returns 200 (`ddd_cents` computed).

## 2. Decisions made (append to Decision Log)

83. **The auditor reconciles against the driver's own receivables, not a re-derivation.** `audit_settlement` treats `m04.money_owed` (the F7 receivables M3/M4 already created from GPS evidence) as the entitlement, and the settlement's lines as what the carrier paid; missed = owed − paid per kind. Already-`recovered`/`written_off` receivables are excluded — money settled through our own rails isn't "missed carrier pay."
84. **DDD is the composition, not a stored number.** `earnings_dashboard` sums recovered (M3/M4) + fuel saved (M7) + flagged (M9) live from the source modules; nothing is denormalized. The Money tab's hero is this figure (design-prd §238 elevated from "recovered" to the full North Star).
85. **IFTA + per-diem ship as honest seams, not fake outputs.** Real per-jurisdiction mileage needs state-boundary geometry crossed against F3 traces, and per-diem needs an account-wide track vs. a home base — neither is in the foundation. The functions exist and return explicit `basis` ("needs_jurisdiction_boundaries" / "needs_account_traces") rather than fabricating precision (§11.7). Matches the M6/M7 activation-seam discipline.
86. **Expense receipts use `DocType.other`** (F6 has no generic `receipt` type; `lumper_receipt` is claim-specific). If expense-receipt OCR becomes first-class, add a `DocType.receipt` — logged for the owner.
87. **Settlement-auditor UI deferred** (backend + `POST /money/settlements/audit` shipped). The upload + discrepancy-report screen is a fuller flow; deferring its UI matches prior deferrals (M8 sleep-solver, M5 capture flows) and kept this session's UI on the highest-value DDD hero.

## 3. Exact next task

**Continue module order → M10.** Plan **M10 — Community & Points Economy** (PRD §8.10 — verify title/FRs against the PRD before building), plan-first:
- Consumes F10 (crowd/trust) + F7 (closed-loop points, already in the ledger) + F14. Likely: points earn/redeem surfaces, contributor reputation, community signals — building on the F10 trust + F7 points_balance/points_pool already in place.
- Backend `m10_community` (imports foundation + earlier module publics). F13 flag. Then UI.

**Fold-in follow-ups (owner priority):** **Mapbox token**, active-load API, **offline read-cache (F12)**, **M9 settlement-auditor UI**, **M8 sleep-solver UI**, M5 capture flows, M6/M7 owner portals, **brand name**.

## 4. Blockers / owner questions

1. **Brand name** — "LONGHAUL" codename placeholder on the login header (design-prd §4 seam).
2. **Fuel payment-partner + merchant agreements + spread ¢/gal** (M7 activation).
3. **Stripe/Connect structure + take rate; refund/damage-liability posture** (M6 activation).
4. **Mapbox token** (M1 live tiles). **Collection-partner + legal sign-off** (M3/M4 activation).
5. **IFTA jurisdiction-boundary dataset + account-wide trace query** — needed to turn M9-FR2/FR3 from seams into real outputs (M9 activation).
6. **Locale wording** — new M9 strings (2 keys × 6 locales, on top of prior) native review pending (F15); completeness gate green at **102 keys**.
7. Standing seams: model keys + budgets (F9, now used by M9's settlement parse), timestamping/PDF (F4), Twilio/FCM/email (F8), MinIO bucket (F6).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 → opens on `/login` → Map · `/facility/:id` · `/book/:spotId` · `/fuel/:stationId` · `/load` · `/load/calc` · **`/money`** (DDD North Star) · `/docs` · `/more`. API http://localhost:8008 (`/auth/*`, `/map/*`, `/facility/*`, `/detention/*`, `/accessorial/*`, `/protection/*`, `/parking/*`, `/fuel/*`, `/intel/*`, **`/money/*`**). Admin seed: `admin@longhaul.local` / `longhaul-admin-dev`.
Suite: **pytest 233 · vitest 67 · 29 contracts · ruff clean**, migrations through `0021`.

## 7. Build progress

**Common Ground F1–F15: complete.** Modules: **M1–M9 done.** Next: **M10** → M11 → M12. The Money tab now answers "what has this app delivered me?" with the North Star DDD; the settlement auditor gives company drivers the wedge (backend live, UI next).

## 8. Commits this session (local only, never pushed)

`30bf327` HANDOFF-021 → `d40be0a` M9 backend+API → `99ac093` M9 DDD UI (+ this handoff). **63 commits** on `main`.

*— End of session. Next: plan M10 (Community & Points Economy — building on F10 trust + F7 closed-loop points), plan-first.*
