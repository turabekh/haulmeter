# HANDOFF-025 — M12 Fleet & B2B Layer · **the M1–M12 build is complete**

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** Common Ground F1–F15 complete. **ALL modules M1–M12 built** (backend + API + UI). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 (Foundation DoD), 012–024 (M1–M11 + login UI).

---

## 1. What now exists and passes (delta since HANDOFF-024)

**New: M12 — Fleet & B2B Layer** (the final module — the multiplier) + the **web-first Fleet Workspace portal**. **This completes the entire PRD §6 build sequence: Common Ground F1–F15, then M1 → M12 in order.**

### M12 backend — `api/app/modules/m12_fleet` (schema `m12`, PRD §8.12)
Composes **F1 + F5 + F7 + M2 + M4 + M7**. 29 contracts KEPT.
- **Fleet workspace** (M12-FR1): a fleet IS an F1 `Organization(type=fleet)`; M12 owns membership so it can require **EXPLICIT consent** — an invited-but-unconsented driver's data never enters any fleet view (consent is the gate on every rollup).
- **Parking benefits** (M12-FR2): monthly per-driver allowance + usage tracking (completes M6-FR8).
- **Fleet claims desk** (M12-FR3): the M3/M4 receivable pipeline across members + **counterparty analytics** — which brokers actually pay (recovery rate per counterparty, from F7 receivables).
- **Fleet reporting** (M12-FR4): recovered $, fuel saved, owed per driver and fleet-wide.
- **Data product** (M12-FR5): aggregate facility dwell benchmarks with a **hard minimum-sample floor** (`MIN_BENCHMARK_SAMPLE=5`) — suppressed below it, never identifiable, subscription-gated (§13 privacy).
- **TMS/webhook** (M12-FR6): `push_load` into F5 (`source=tms_push`) + `claim_status` out.
- F13 flag `m12_fleet`.

### M12 HTTP API + web-first UI
- API: `POST /fleet`, `POST /fleet/{id}/invite`, `GET /fleet/{id}/report`, `GET /fleet/{id}/claims`, `GET /fleet/benchmark/{facility}` (402 without subscription; `suppressed` below min-sample).
- **Fleet Workspace** (`/fleet`) — the **first web-first surface** (design-prd §18): desktop-first, `meta.portal` widens the frame to 1200 dp (driver app stays capped at 480, **LAW 0 intact**), comfortable tables, shares `ui/core` tokens, not a driver-app screen. KPI row + members table + claims desk (broker recovery rates).

### Verified this session (in compose)
- `alembic upgrade head` through **`0023`**; up→down→up verified. **Single clean head `0023_m12_fleet`, 23 migrations, linear chain.**
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 268 passed** (was 258; +7 M12 module +3 M12 API).
- UI: **vitest 73 passed** (+1: Fleet Workspace) · `vite build` clean · six-locale completeness at **125 keys**.
- **Live smoke:** create fleet → owner is the sole consented member → `GET /fleet/{id}/report` returns 200.

## 2. Decisions made (append to Decision Log)

98. **A fleet is an F1 Organization; M12 owns consent.** F1's `Organization(type=fleet)` + `OrgMembership` give the identity, but M12-FR1 needs explicit per-member consent that F1's membership lacks — so `FleetMembership` (m12) is the source of truth for who's in a fleet, and `consent && active` is enforced on every rollup (`_member_ids`). Privacy by construction.
99. **The data product suppresses below the minimum sample, never anonymizes-and-hopes** (§13). `dwell_benchmark` returns `None` under `MIN_BENCHMARK_SAMPLE`; the API surfaces `{suppressed: true}`, never a small-n figure. Subscription-gated (402 otherwise). Aggregate-only; there is no code path to per-driver data in a benchmark.
100. **The web portal escape hatch is a route meta flag, not a second app.** `meta.portal` toggles `.app-frame--wide` (1200 dp) and `meta.chrome:false` drops the tab bar; the driver app's 480 dp cap is untouched (LAW 0). One SPA, tokens shared, but the portal is not a driver screen (§18).
101. **F5's `tms_push` LoadSource and F1's fleet Organization confirm the foundation was built for M12** — no foundation changes were needed for the final module; it composed entirely from existing publics. The schema-per-module + public-only discipline held across all 12 modules (29 import contracts, unchanged since the Common Ground).

## 3. Exact next task — the build sequence is done; this is a transition point

**There is no M13.** The PRD §6 build law (Common Ground F1–F15 → M1–M12 in order) is **fully satisfied**. The next session is **not** a new module; it is **owner-directed hardening / activation**, choosing from:

**A. Activation seams (turn built features live) — each gated on an owner/BD input, not a build:**
- **F9 real model provider + budgets** → activates M9 settlement parse + M11 voice/ghostwriter (six-language eval fixtures for the 95% DoD).
- **Stripe/Connect + take rate + refund/liability posture** → M6 activation.
- **Fuel payment-partner + merchant agreements + spread ¢/gal** → M7 activation.
- **Collection-partner + legal sign-off** → M3/M4 activation.
- **Mapbox token** → M1 live tiles.
- **IFTA jurisdiction dataset + account-wide traces** → M9-FR2/FR3.
- **M10 economy params → F13 config** → M10 activation.
- **Brand name** → replaces the "LONGHAUL" login placeholder.

**B. Deferred UI follow-ups (backends already shipped):** M11 ghostwriter approve screen · M10 handoff-relay UI · M9 settlement-auditor UI · M8 sleep-solver UI · M5 condition-capture/incident flows · M6/M7 owner portals · the fleet-selection flow to make `/fleet` live · M9 IFTA/per-diem once data lands.

**C. Cross-cutting hardening:** offline read-cache (F12) across Map/Docs/Booking/Fuel/Voice · active-load API (replace the Load-tab fixture) · the two other web portals (Property-Owner, Public Scorecard, §18) · a synthetic full-platform e2e across M1–M12 · fresh-install migration check from wiped volumes.

**Recommendation:** start the next session by asking the owner which of A/B/C to prioritize; the highest-leverage single item is **F1 login is already done**, so the **F9 real provider** (unblocks M9+M11) or **Stripe (M6)** are the biggest revenue-adjacent unlocks.

## 4. Blockers / owner questions

All are **activation inputs**, not build blockers (the build is complete):
1. **Brand name** (login placeholder).
2. **F9 model provider + per-module budgets** (M9, M11).
3. **Stripe/Connect + take rate + refund/liability posture** (M6).
4. **Fuel payment-partner + merchant deals + spread** (M7).
5. **Collection-partner + legal** (M3/M4). **Mapbox token** (M1). **IFTA data** (M9). **M10 economy params → F13** (M10).
6. **Locale wording** — all new module strings need native review (F15); completeness gate green at **125 keys**.
7. Standing seams: timestamping/PDF (F4), Twilio/FCM/email (F8), MinIO bucket (F6).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged across the entire build.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 → `/login` → Map (+voice) · `/facility/:id` · `/book/:spotId` · `/fuel/:stationId` · `/load` · `/load/calc` · `/money` (DDD) · `/docs` · `/more` (points) · **`/fleet`** (web-first portal). API http://localhost:8008 — routers: auth, map, facility, detention, accessorial, protection, parking, fuel, intel, money, community, voice, **fleet**. Admin: `admin@longhaul.local` / `longhaul-admin-dev`.
Suite: **pytest 268 · vitest 73 · 29 contracts · ruff clean**, migrations through `0023` (single head).

## 7. Build progress — **COMPLETE**

**Common Ground F1–F15: complete.** **Modules M1–M12: ALL complete** (backend + API + UI, each behind its F13 flag, tests alongside). The PRD §6 dependency sequence is fully built:
M1 map · M2 facility intel · M3 detention · M4 accessorial · M5 protection · M6 parking · M7 fuel · M8 intelligence · M9 money/tax · M10 community/points · M11 voice · M12 fleet/B2B.
Plus the F1 driver login UI. What remains is **activation** (owner/BD seams) and **hardening/follow-up UIs** — not new modules.

## 8. Commits this session (local only, never pushed)

`421fb6d` HANDOFF-024 → `ae6c1aa` M12 backend+API → `816906a` M12 UI (+ this handoff). **72 commits** on `main`, spanning the full F1–F15 + M1–M12 build. Nothing has ever been pushed (local-only rule held throughout).

*— End of the build. The M1–M12 sequence is complete to each module's DoD (activation seams excepted, as designed). Next session: owner picks activation vs. hardening vs. deferred-UI priorities (§3). Suggested opener: wire the F9 real model provider (unblocks M9 + M11) or Stripe (M6), whichever the owner ranks first.*
