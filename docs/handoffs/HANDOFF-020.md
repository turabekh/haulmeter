# HANDOFF-020 — M8 Decision Intelligence (backend + API + intel UI)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–F15 complete. **M1–M8 built** (backend + API + UI). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 (Foundation DoD), 012–019 (M1–M7).

---

## 1. What now exists and passes (delta since HANDOFF-019)

**New: M8 — Decision Intelligence** (the first intelligence layer) + the **true-profit calculator** and **facility pre-acceptance intel**. M8 is a **schema-less serving layer** (F11 precedent): it owns no tables, composes the modules below it through their publics, and takes the driver's inputs. Every output carries its **basis** — sample size or "heuristic" — nothing fabricates precision (M8-FR5 / design-prd §11.7).

### M8 backend — `api/app/modules/m08_intelligence` (no schema, PRD §8.8)
Composes **F3 + m01/m02/m03/m06/m07** publics. 29 contracts KEPT (M8→earlier-module imports all legal). **No migration** (schema-less).
- **True-profit calculator** (M8-FR1): `true_profit` = revenue − route fuel (**M7** corridor net price × gallons) − tolls − **expected detention**, where expected detention values each historical stop with the **same M3 clock the live meter uses**, then averages (`expected_detention_cost` over **F3** dwell samples). Output **rate-per-mile after** this receiver's dwell history.
- **Appointment-hour optimizer** (M8-FR2): `appointment_hours` from **M2** dwell-by-hour, ranked fastest-first, confidence from sample size.
- **"Where do I sleep tonight" solver** (M8-FR3): `where_to_sleep` = HOS range + **M1** corridor/forecast + **M6** bookable inventory (a guaranteed spot) + **M7** fuel plan → ranked stops (guaranteed-bookable first, then predicted availability, then nearest).
- **Parking-fill forecast** (M8-FR4): `predict_parking` wraps M1's heuristic today, basis always shown (upgrades to a learned model as data accrues).
- **Detention-risk pre-acceptance flag** (M8-FR6): `detention_risk_flag` = % of tracked stops that ran past free time, with sample-size basis.
- **Confidence** (M8-FR5): `confidence_for(n)` — heuristic (0) / low (1–2) / medium (3–9) / high (10+).
- F13 flag `m08_intelligence` (no external gates — read/compute only, so `can_activate` is True once built).

### M8 HTTP API + intel UI
- API: `POST /intel/true-profit`, `GET /intel/appointment-hours/{id}`, `GET /intel/detention-risk/{id}`, `GET /intel/sleep`.
- **LoadCalcSurface** (`/load/calc`) — a **full-screen linear form** (NAV-3 / §202: one input per line, 56 dp, numeric keypad) reached from the Load tab's "Check load profit" text link. Result is the **true profit** in Meter treatment (Mono; **ledger-green when it clears, flare when it doesn't**), rate-per-mile after dwell, and a transparent breakdown with basis. Live via api.js; offline it degrades honestly (fuel + dwell need a session, and it says so).
- **Facility scorecard** gains the **detention-risk flag** (% past free time, flare at ≥40%) + **fastest appointment hour**, each with sample-size basis.

### Verified this session (in compose)
- No migration (schema-less); the M8 module needs no schema/db_registry/conftest entry.
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 224 passed** (was 214; +7 M8 module +3 M8 API).
- UI: **vitest 61 passed** (was 58; +3: true-profit offline net + flare, facility risk/fastest-hour) · `vite build` clean · six-locale completeness at **88 keys**.

## 2. Decisions made (append to Decision Log)

74. **M8 is a schema-less decision-serving layer** (F11 precedent). Its outputs are pure functions of other modules' data + driver inputs; persisting calculations/plans isn't needed for the DoD and would belong to the M12 data product. No tables, no migration — keeps M8 a clean composition over M1/M2/M3/M6/M7 + F3.
75. **Expected detention reuses the M3 clock, not a new formula.** `expected_detention_cost` calls `m3.compute_detention` per historical dwell sample and averages — the pre-acceptance number is computed by the exact machinery that will run live at the dock. One source of truth for detention math.
76. **The corridor is ranked by net fuel price, not a modeled deviation cost** (carried from M7): M8-FR1's "route fuel" uses the cheapest network net price on the corridor; a deviation-mile model waits for real routing (post-M8). Basis surfaced.
77. **M8 UI placement composed under §22 (design-prd silent on M8).** The true-profit calculator is a full-screen form off the Load tab; the risk flag + fastest hour fold into the existing M2 facility scorecard (their natural home). No new nav, no invented components — logged here as the §23-style record.
78. **Sleep-solver UI deferred** (backend + `GET /intel/sleep` shipped). It's a RESTING/Map-context surface; deferring its UI matches prior modules' UI deferrals (M5 capture flows, M6/M7 owner portals) and keeps this session's scope focused on the headline calculator.

## 3. Exact next task

**Continue modules in order → M9.** Plan **M9 — Financial Rails & Docs** (PRD §8.9), plan-first (verify the exact section title/FRs against the PRD before building):
- Consumes M3/M4 (recovered claims + packs) and M7 (fuel data) for an **earnings dashboard** (settlements + recovered + fuel savings in one view) that feeds the **North Star (Driver Dollars Delivered)**.
- Likely: IFTA-ready fuel export (the M7-FR4 hook lands here), document/settlement handling on F6, earnings rollups on F7.
- Backend `m09_money` (imports foundation + earlier module publics). F13 flag. Then UI — an earnings/DDD surface (the Money tab already shows recovered + fuel-saved; M9 completes it).

**Fold-in follow-ups (owner priority):** F1 **login UI** (unblocks every live API incl. M8 intel + fuel + booking), **Mapbox token**, active-load API, **offline read-cache (F12)**, **M8 sleep-solver UI**, M5 capture flows, M6/M7 owner portals.

## 4. Blockers / owner questions

1. **F1 login UI is now the top leverage point** — M6 booking, M7 fuel corridor/pump, and M8 intel all have live APIs but the app runs unauthenticated, so they show fixtures/offline fallbacks. A login surface turns them all live.
2. **Fuel payment-partner + merchant agreements + spread ¢/gal** (M7 activation).
3. **Stripe/Connect structure + take rate; refund/damage-liability posture** (M6 activation).
4. **Mapbox token** (M1 live tiles). **Collection-partner + legal sign-off** (M3/M4 activation).
5. **Locale wording** — new M8 strings (16 keys × 6 locales) native review pending (F15); completeness gate green at **88 keys**.
6. Standing seams: timestamping/PDF (F4), Twilio/FCM/email (F8), model keys + budgets + embedding dim (F9), MinIO bucket (F6), brand name.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 (Map · `/facility/:id` incl. risk/fastest-hour · `/book/:spotId` · `/fuel/:stationId` · `/load` · **`/load/calc`** true-profit · `/money` · `/docs`) · API http://localhost:8008 (`/docs`, `/auth/*`, `/map/*`, `/facility/*`, `/detention/*`, `/accessorial/*`, `/protection/*`, `/parking/*`, `/fuel/*`, **`/intel/*`**) · MinIO :9019 · Mailpit :8038. Admin: `admin@longhaul.local` / `longhaul-admin-dev`.
Suite: **pytest 224 · vitest 61 · 29 contracts · ruff clean**, migrations through `0020` (M8 adds none).

## 7. Build progress

**Common Ground F1–F15: complete.** Modules: **M1, M2, M3, M4, M5, M6, M7, M8 done.** Next: **M9** → M10 → M11 → M12. The Map carries three deep-link flows (Navigate/Book/Fuel); the Load tab now answers "should I take this load?"; the facility scorecard answers "will this receiver hold me hostage?"

## 8. Commits this session (local only, never pushed)

`f1519fd` HANDOFF-019 → `cf0254b` M8 backend+API → `6556112` M8 intel UI (+ this handoff). **58 commits** on `main`.

*— End of session. Next: plan M9 (Financial Rails / earnings — the North Star dashboard consuming M3/M4 recovered + M7 fuel savings, IFTA export), plan-first. Consider prioritizing the F1 login UI to turn M6/M7/M8's live APIs on.*
