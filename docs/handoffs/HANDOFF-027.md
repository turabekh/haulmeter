# HANDOFF-027 — Active-load API + live Meter (The signature element goes real)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026 (deferred-UI batch).

---

## 1. What now exists and passes (delta since HANDOFF-026)

**The Meter is live.** The Load tab's Meter (design-prd §9 — the product's one signature element) had run on the `SAMPLE_STOP` fixture since it was built. It now runs on a real active-load lifecycle end-to-end.

### Active-load API — `api/app/api/load.py`
A new API surface (prefix `/load`) composing **F2 + F5 + F3 + M3** (the API/serving layer, allowed to compose publics):
- **`POST /load`** — create an F2 facility + F5 counterparty + load + stop (with detention terms), then `arm_stop` (opens the F4 evidence log + arms the F3 geofence). Returns `{load_id, stop_id}`.
- **`POST /load/{stop_id}/arrive`** — a **geofence ENTER at the stop** (F3 `evaluate_ping`) is the arrival the **M3 detention clock** triggers on; starts the claim.
- **`GET /load/{stop_id}/meter`** — pre-arrival vs a live **clock snapshot** (phase, free-time-remaining, detention seconds/cents) + stop context, so the client reconstructs arrival and ticks the Meter locally each second without polling.

### Load-tab UI wired to it — `LoadSurface`
- `api.js`: `activeStopId` **persisted to localStorage** (the Load tab reopens on the running clock); `createActiveLoad` / `arriveAtStop` / `fetchMeter`.
- With an active stop, the Meter derives arrival from the clock snapshot and **ticks free-time down, then money up** locally. **Pre-arrival** shows an "I've arrived" CTA. **No active load** → the fixture demo Meter + a **"Start a load"** sheet (facility / broker / terms); **"End load"** clears it.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 271 passed** (was 268; +3 load API).
- UI: **vitest 77 passed** (was 76; +1 live pre-arrival, existing demo test kept) · `vite build` clean · six-locale completeness at **155 keys** (was 148; +7).
- **Live end-to-end smoke:** `POST /load` → `GET meter` = `not_arrived` → `POST arrive` (201) → `GET meter` = `within_free_time`, `arrived=true`, `free_time_remaining_seconds=7199` (120-min clock running). The Meter is real.

## 2. Decisions made (append to Decision Log)

105. **The active-load lifecycle lives in the API/serving layer, not a new module.** "Active load" is a composition of F2/F5 (load+stop) + F3 (arrival) + M3 (clock); `app/api/load.py` composes their publics exactly as `app/api/m03_detention.py` already does. No new schema, no import-contract change (still 29). The client holds the active `stop_id`; there's no "list my loads" query to build.
106. **Arrival is a geofence ENTER, not a manual flag.** `POST /arrive` records an F3 ENTER at the stop's facility — the same signal the M3 clock reads for every stop — so the live Meter and any future claim share one source of truth (the GPS trail), consistent with the evidence-first design.
107. **The Meter ticks client-side from a snapshot, not by polling.** `GET /meter` returns the M3 clock state once; the client reconstructs `arrivalMs` (from free-time-remaining or detention-seconds) and runs `computeDetentionState` each second locally. One request per open, not one per second — and it degrades to the fixture demo offline.
108. **The Load tab keeps a demo when there's no active load.** Rather than an empty state, an unauthenticated/no-load Load tab still shows the accruing fixture Meter (so the signature element is always visible) plus a "Start a load" path into the live flow.

## 3. Exact next task — continue the backlog

Remaining **deferred UIs / hardening** (no owner input needed), in suggested order:
- **M10 handoff-relay UI** — the highest-novelty feature: "leaving in X" broadcast + claim on the Map free-lot pins (`/community/handoff` shipped).
- **Fleet-selection flow** — make `/fleet` live (create/pick a fleet → live `/fleet/{id}/report|claims`).
- **Send-notice / Generate-claim wiring** on the Load tab — the primary CTA currently only handles "I've arrived"; wire the accruing-state CTA to M3 (`/detention/start` + `/detention/{claim}/pack`) so a claim is generated from the live stop.
- **M5 condition-capture / incident flows** (camera-first capture; M5 backend shipped).
- **Offline read-cache (F12)** across Map/Docs/Booking/Fuel/Voice/Load.
- **Synthetic full-platform e2e** across M1–M12.
- **The other two web portals** (Property-Owner, Public Scorecard, §18).

**Activation seams** (need owner/BD input — not buildable now): F9 real model provider (M9+M11), Stripe (M6, **deferred by owner**), fuel payment-partner (M7), collection-partner (M3/M4), Mapbox (M1), IFTA data (M9), M10 economy params → F13, brand name.

**Recommendation:** the **Send-notice / Generate-claim wiring** is the natural next step — it completes the Load-tab loop just made live (arrive → accrue → *file the claim*), turning the detention clock into a filed receivable end-to-end. Then the **M10 handoff-relay UI**.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**, none block the buildable backlog: brand name · F9 provider (M9/M11) · Stripe (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **155 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 → `/login` → Map (+voice, +sleep) · `/facility/:id` · `/book/:spotId` · `/fuel/:stationId` · **`/load`** (live Meter + Start-a-load) · `/load/calc` · `/money` (DDD + Audit + Draft) · `/docs` · `/more` · `/fleet`. API http://localhost:8008 — routers now include **`/load/*`** (create/arrive/meter) alongside auth + 12 modules.
Suite: **pytest 271 · vitest 77 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete.** Post-build hardening: this session made **The Meter live** (active-load API + Load-tab wiring). Prior hardening (HANDOFF-026): M9 auditor, M11 ghostwriter, M8 sleep-solver UIs. Backlog remaining in §3.

## 8. Commits this session (local only, never pushed)

`24ae7b7` HANDOFF-026 → `74ed208` active-load API → `0ba1fed` Load-tab live UI (+ this handoff). **79 commits** on `main`, never pushed.

*— End of session. Next: wire the Load tab's Send-notice / Generate-claim CTA to M3 (close the arrive→accrue→file loop), then the M10 handoff-relay UI. Activation seams await owner/BD inputs (§4).*
