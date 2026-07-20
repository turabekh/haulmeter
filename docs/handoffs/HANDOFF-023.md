# HANDOFF-023 — M10 Community & Points Economy (backend + API + UI)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–F15 complete (F1 has driver UI). **M1–M10 built** (backend + API + UI). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 (Foundation DoD), 012–022 (M1–M9 + login UI).

---

## 1. What now exists and passes (delta since HANDOFF-022)

**New: M10 — Community & Points Economy** (pay drivers for their data; peer-to-peer liquidity incumbents can't copy) + **points on the More tab** and **driver Q&A on the facility page**.

### M10 backend — `api/app/modules/m10_community` (schema `m10`, PRD §8.10)
Composes **F2 + F3 + F7 + F10 + m06**. 29 contracts KEPT.
- **Points economy** (M10-FR1): `award_contribution` issues F10 trust-weighted points per kind and logs it; `redeem_points` spends points at a fixed rate (F7 points currency) with an `InsufficientPoints` guard; **`book_with_points`** redeems ONLY against an M6 booking and **funds the discount from the M6 take** (platform_revenue → cash_clearing) — the "partially circular" economy. Anti-gaming: `RATE_LIMIT_PER_DAY` on the contribution log.
- **Spot handoff relay** (M10-FR2): `broadcast_handoff` requires geofence presence at a **FREE public lot** (truck_stop/rest_area — `NotFreeLot` on an M6 property, so it never cannibalizes inventory); `claim_handoff` → `confirm_handoff` on the claimer's proven ENTER, and **both earn**. Conservative geofence proof per the PRD note.
- **Contributor reputation** (M10-FR3): `reputation` (level + counts from the contribution log + F10 trust) and `leaderboard`.
- **Moderated facility Q&A** (M10-FR4): `ask_question` / `answer_question` (presence-proven answers earn and rank) / `list_questions`, pinned to the M2 facility page.
- F13 flag `m10_community`; economy params (`REDEEM_CENTS_PER_POINT`, `EARN_RULES`, `RATE_LIMIT_PER_DAY`) are constants ready to move to F13 config at activation.

### M10 HTTP API + UI
- API: `GET /community/points`, `GET /community/leaderboard`, `POST /community/handoff`, `GET /community/questions/{id}`, `POST /community/questions`, `POST /community/questions/{id}/answers`.
- **More tab**: a points card — balance in Mono + contributor level.
- **Facility scorecard**: the driver **Q&A** section (questions + answers, `on-site` badge on geofence-present answers, "Ask a question" sheet posting to the API).

### Verified this session (in compose)
- `alembic upgrade head` through **`0022`**; up→down→up verified (m10 schema + `handoff_state` enum round-trip clean).
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 246 passed** (was 233; +9 M10 module +4 M10 API).
- UI: **vitest 69 passed** (+2: More points card, facility Q&A) · `vite build` clean · six-locale completeness at **113 keys**.
- **Live smoke:** authenticated `GET /community/points` returns 200 (rookie, balance 0).

## 2. Decisions made (append to Decision Log)

88. **Points redemption is realized against an M6 booking and funded from the take.** `book_with_points` redeems points, calls `m6.book`, then posts an adjustment `platform_revenue → cash_clearing` for the discount — the driver's net cost drops, funded by the parking take (PRD §8.10 "partially circular"). Redemption never mints cash from nowhere; it moves value already in the take.
89. **The handoff relay is free-lot only, enforced by facility type.** `broadcast_handoff` refuses any facility whose type isn't truck_stop/rest_area (`NotFreeLot`) — the structural guarantee it never competes with M6 inventory. Both ends require geofence presence (broadcast + the claimer's confirmed ENTER) — conservative proof, tune later via config not code.
90. **The contribution log is M10's own table**, not a re-query of F7 points entries — it powers rate limits, streaks/reputation, and the leaderboard in one place, and keeps F7 the pure ledger.
91. **`points_balance` returns a plain `int`** (cast from the F7 `Decimal` balance) so the HTTP layer serializes a number, not a quoted string. General rule for money/points crossing the API: cast ledger `Decimal`s at the module boundary.
92. **M10 UI placement composed under §22** (design silent on M10): points on the More tab (next to the account), Q&A on the M2 facility scorecard (its PRD-named home). Handoff-relay UI deferred (Map-context interaction; backend + API shipped) — matches prior UI deferrals.

## 3. Exact next task

**Continue module order → M11.** Plan **M11 — Voice Copilot & AI Communications** (PRD §8.11 — verify title/FRs against the PRD before building), plan-first:
- Consumes F9 (STT/TTS/LLM gateway) over platform intents: parking/fuel/facility queries (M1/M2/M8), detention clock status + actions (M3), load context (F5), booking initiation (M6, confirm-on-screen when stopped). DRIVING-state voice is the S1 input (design-prd §14).
- Backend `m11_voice` (imports foundation + earlier module publics). F13 flag. Then UI — a voice affordance, likely DRIVING-state.

**Fold-in follow-ups (owner priority):** **Mapbox token**, active-load API, **offline read-cache (F12)**, **M10 handoff-relay UI**, **M9 settlement-auditor UI**, **M8 sleep-solver UI**, M5 capture flows, M6/M7 owner portals, **brand name**.

## 4. Blockers / owner questions

1. **Brand name** — "LONGHAUL" codename placeholder on login (design-prd §4 seam).
2. **M10 economy parameters** — earn amounts, redeem rate, rate limits are code constants; move to F13 config + owner sign-off before activation (PRD §8.10 DoD: "tunable via F13 config").
3. **Fuel payment-partner + merchant agreements + spread ¢/gal** (M7); **Stripe/Connect + take rate + refund/liability posture** (M6); **Mapbox token** (M1); **collection-partner + legal** (M3/M4); **IFTA jurisdiction data + account-wide traces** (M9-FR2/FR3).
4. **F9 model keys + budgets** — now consumed by M9 (settlement parse) and next by M11 (voice); real provider + budgets needed before those activate.
5. **Locale wording** — new M10 strings (11 keys × 6) native review pending (F15); completeness gate green at **113 keys**.
6. Standing seams: timestamping/PDF (F4), Twilio/FCM/email (F8), MinIO bucket (F6).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 → `/login` → Map · `/facility/:id` (dwell · risk · **Q&A**) · `/book/:spotId` · `/fuel/:stationId` · `/load` · `/load/calc` · `/money` (DDD) · `/docs` · **`/more`** (account + **points**). API http://localhost:8008 (`/auth/*`, `/map/*`, `/facility/*`, `/detention/*`, `/accessorial/*`, `/protection/*`, `/parking/*`, `/fuel/*`, `/intel/*`, `/money/*`, **`/community/*`**). Admin: `admin@longhaul.local` / `longhaul-admin-dev`.
Suite: **pytest 246 · vitest 69 · 29 contracts · ruff clean**, migrations through `0022`.

## 7. Build progress

**Common Ground F1–F15: complete.** Modules: **M1–M10 done.** Next: **M11** → M12. The platform now pays drivers for their data (points), lets them hand off spots peer-to-peer, and answers each other's facility questions — the network-effect layer is live.

## 8. Commits this session (local only, never pushed)

`bfe88fb` HANDOFF-022 → `11ce14e` M10 backend+API → `d0231b2` M10 UI (+ this handoff). **66 commits** on `main`.

*— End of session. Next: plan M11 (Voice Copilot — F9 STT/TTS over platform intents, DRIVING-state voice input), plan-first.*
