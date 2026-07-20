# HANDOFF-030 — Fleet-selection flow (every built surface is now live)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–029 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-029)

The **Fleet Workspace** was the last fixture-only surface. It's now live: a driver creates or picks a fleet and the web-first portal fetches its real report + claims desk. **Every built module now has a live in-app surface.**

### Backend
- `service.list_fleets_for(account_id)` — the fleets an account belongs to (active memberships), resolving F1 `Organization` names via `db.get`.
- **`GET /fleet/mine`** — `[{fleet_id, name, role}]`.

### UI — `FleetWorkspaceSurface`
- `api.js`: **`activeFleetId` persisted to localStorage**; `fetchMyFleets` / `createFleet` / `fetchFleetReport` / `fetchFleetClaims`.
- Flow: **create-a-fleet** (none yet) → or **pick from "Your fleets"** → **live workspace** (KPI row + consented-members table + broker recovery rates). A "switch" link returns to the picker. Falls back to the **fixture demo** when unauthenticated/offline. Raw member UUIDs truncated for readability (the live report keys members by account id).

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 275 passed** (was 274; +1 `/fleet/mine`).
- UI: **vitest 81 passed** (was 80; +1 create→live, demo-fallback test kept) · `vite build` clean · six-locale completeness at **171 keys**.
- **Live smoke:** `GET /fleet/mine` = `[]` → `POST /fleet` → `GET /fleet/mine` = `[{name:"Acme Fleet", role:"owner"}]`.

## 2. Decisions made (append to Decision Log)

115. **The selected fleet is client-held (localStorage), like the active stop.** No "current fleet" server state; `GET /fleet/mine` lists membership and the portal remembers the pick. Reload reopens on the same fleet; a stale id (not in `/mine`) silently drops to the picker.
116. **The portal degrades to the fixture demo, never an error screen.** Unauthenticated/offline → the rich SAMPLE_FLEET demo renders (so the §18 portal is always presentable); authenticated paths (create/pick/workspace) drive live data. Same fixture-first discipline as every driver surface.
117. **The live claims desk keys counterparties by ref, the demo by name.** `fleet_claims_desk` returns `by_counterparty` keyed by the F7 receivable's counterparty_ref (UUID); a fresh fleet has none, so the live desk is empty until claims accrue. Resolving broker names into the desk is a small backend follow-up (not blocking).

## 3. Exact next task — continue the backlog

The remaining backlog is **cross-cutting hardening** (no owner input) — no fixture-only surfaces left:
- **Synthetic full-platform e2e** across M1–M12 — one test that walks: register → map overlay → book parking → fuel corridor → create load → arrive → file claim → audit settlement → broadcast/claim a handoff → create fleet → fleet report. Locks the whole platform down end-to-end. **Recommended next.**
- **Offline read-cache (F12)** across Map/Docs/Booking/Fuel/Voice/Load/Fleet.
- **M5 condition-capture / incident flows** (camera-first capture; backend shipped).
- **The other two web portals** (Property-Owner, Public Scorecard, §18).
- Small backend polish: resolve counterparty **names** in the fleet claims desk; a "list my active load" endpoint so the Load tab recovers its stop without localStorage.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name.

**Recommendation:** the **synthetic full-platform e2e** — with every surface live, one end-to-end test proves the twelve modules integrate through their publics as a single product, and guards every future change.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **171 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged. *(Reminder: `restart api` after adding endpoints — dev server doesn't hot-reload; tests run fresh.)*

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 · Fleet portal http://localhost:9008/fleet (create/pick → live) · API http://localhost:8008 (fleet routes now include `GET /fleet/mine`).
Suite: **pytest 275 · vitest 81 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete.** Post-build hardening: **every built module now has a live in-app surface** (fleet portal live this session). Prior: relay UI (029), detention loop closed (028), live Meter (027), M9/M11/M8 UIs (026). No fixture-only surfaces remain; backlog is cross-cutting hardening (§3).

## 8. Commits this session (local only, never pushed)

`2645f32` HANDOFF-029 → `5392150` fleet-selection flow (+ this handoff). **86 commits** on `main`, never pushed.

*— End of session. Next: a synthetic full-platform e2e across M1–M12 (register → map → book → fuel → load→arrive→file → audit → relay → fleet), then offline read-cache (F12). Activation seams await owner/BD inputs (§4).*
