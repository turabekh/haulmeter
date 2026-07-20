# HANDOFF-014 — M2 Facility Intelligence & Scorecard (backend + API + UI)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–F15 complete. **M1 + M2 built** (backend + API + UI). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 (Foundation DoD), 012–013 (M1).

---

## 1. What now exists and passes (delta since HANDOFF-013)

**New: M2 — Facility Intelligence & Scorecard** (backend + HTTP API + Facility profile UI).

### M2 backend — `api/app/modules/m02_facility_intel` (schema `m02`, PRD §8.2)
Composes foundation publics only (29 contracts KEPT).
- **Facility profile** — M2-owned factual attributes extending F2; **self-service factual claim** (M2-FR7) rejects non-factual fields (never ratings/stats), F14-audited.
- **Structured 10-aspect reviews** (M2-FR1/FR4) — **moderated via F14**; on approval → **points (F10)** + **F9 embedding**; ratings validated 1–5; pending reviews invisible.
- **Objective dwell statistics** (M2-FR2) — median/p90 overall + by arrival-hour, **sample sizes always shown**, from a new **`F3.dwell_samples`** helper (pairs ENTER→EXIT across accounts).
- **Detention-risk** (M2-FR3) — seam (`"m3_pending"`) until M3.
- **Semantic review search** (M2-FR6) via F9 embeddings. F13 flag `m02_facility_intel` + F14 admin view.

### M2 HTTP API — `app/api/m02_facility_intel`
`GET /facility/{id}/profile` (profile + dwell stats + aggregate ratings + detention seam + approved reviews), `POST /facility/{id}/review`, `GET /facility/search` (F9 provider seam). Auth via F1 session (`current_account`).

### M2 UI — Facility profile / scorecard surface
`FacilityProfileSurface` (route `/facility/:id`, S3 density): dwell figures in **Mono with sample sizes always shown** (§11.7 — honest), driver rating, moderated reviews, quick-review sheet. Reached from the map facility card via a **"View facility" cross-link** (NAV-5). Fixture-backed pending auth; swaps to the live M2 API behind `api.js`.

### Verified this session (in compose)
- `alembic upgrade head` through `0015`; up→down→up verified.
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 160 passed** (Common Ground 136 + M1 module 9 + M1 API 5 + M2 module 8 + M2 API 2).
- UI: **vitest 44 passed** (contrast both themes, six-locale completeness at 33 keys, pseudo-locale, state/presentation/i18n, components incl. M2 profile surface).

## 2. Decisions made (append to Decision Log)

50. **Reviews are moderated before visible; approval pays + indexes.** `submit_review` → pending + F14 moderation queue; `moderate_review(approve)` → points (F10) + F9 embedding + F14 decide. Aggregates + search only over **approved** reviews. This is the PRD §13 defamation posture in code.
51. **Dwell = paired ENTER→EXIT** exposed by `F3.dwell_samples` (the geometry/trace owner), consumed by M2 for stats. Sample sizes are always surfaced — no faked precision (design-prd §11.7 / PRD M2-FR2).
52. **ruff B008 config** — `fastapi.Depends/Query/Header/Path` marked immutable (FastAPI's intended default pattern; B008 was a false positive latent since the M1 API).
53. **M2 UI quick review** captures one 1–5 rating + text (stored under `would_return`); the full 10-aspect capture form is a tracked follow-up.

## 3. Exact next task

**Two threads; recommend continuing modules in order → M3.**

**Plan M3 — Detention Tracker & Recovery** (PRD §8.3), the differentiator/acquisition wedge, plan-first. It's the biggest module and lights up F3+F4+F5+F7+F8+F9 together:
- Stop arming already exists (F5 `arm_stop`); M3 adds the **live detention clock** (free-time countdown from the contractually-correct trigger → accrual at the load's rate — The Meter, design-prd §9), **evidence accrual** (F3 geofence events → F4 hash-chained log; the seam F5 left open), **pre-detention + accruing counterparty notices** (F8, contract-citing), **one-tap claim pack** (F4 composer PDF + invoice in the driver's name → F7 receivable), **dunning cadence**, **escalation to a collection partner** (seam), **company-driver evidence-only mode**, and **dwell write-back to M2**.
- Backend `m03_detention` (may import m01/m02 publics + foundation). Gated on F13 flags with legal/partner **validation gates** (F13). Then its UI — the **Load tab** + **The Meter** (design-prd §9/§10.2), the product's signature element.
- **The Meter is a signature surface** — build it once in `ui/core` on tokens (Q-4), Mono tabular, live-counting. Present an M3 plan first.

**M1/M2 follow-ups to fold in (owner priority):** F1 **login UI** (browser → live API), **Mapbox token** (live tiles), offline read cache, full 10-aspect review form, per-aspect rating display, 50k-POI perf pass.

## 4. Blockers / owner questions

1. **Mapbox token** — for live tiles (M1). Drop into `infra/.env`.
2. **Locale wording** — pa/uz/so/ru/es incl. new M2 strings, native review pending (F15). Completeness gate green.
3. **M3 activation gates** (when M3 lands): licensed transportation **collection partner** agreement + legal sign-off (F13 validation gates) — building M3 with these as gates/seams.
4. Standing seams: timestamping/PDF (F4), Stripe/Connect + points rate (F7), Twilio/FCM/email (F8), model keys + budgets + embedding dim (F9), MinIO bucket (F6), brand name.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 (Map + `/facility/:id`) · API http://localhost:8008 (`/docs`, `/auth/*`, `/map/*`, `/facility/*`) · MinIO :9019 · Mailpit :8038. Admin: `admin@longhaul.local` / `longhaul-admin-dev`.
Suite: **pytest 160 · vitest 44 · 29 contracts · ruff clean**, migrations through `0015`.

## 7. Build progress

**Common Ground F1–F15: complete.** Modules: **M1 done, M2 done.** Next: **M3** → M4 → … → M12.

## 8. Commits this session (local only, never pushed)

… `91bd679` HANDOFF-012 → `5531dd3` M1 API → `8d3c848` HANDOFF-013 → `37b3501` M2 backend+API → `58f9734` M2 UI (+ this handoff). ~40 commits on `main`.

*— End of session. Next: plan M3 (Detention Tracker + The Meter) — the differentiator — plan-first; fold in Mapbox + login UI as priorities allow.*
