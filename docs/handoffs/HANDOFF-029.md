# HANDOFF-029 — M10 spot-handoff relay UI (the highest-novelty feature is live)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–028 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-028)

The **spot-handoff relay** (M10-FR2) — the PRD's "highest-novelty bet," the structural move incumbents can't copy — is now live end-to-end. It had a broadcast endpoint only; this session added the rest of the HTTP surface and the full Map UI.

### Relay endpoints (`api/app/api/m10_community.py` + service)
- `service.nearby_handoffs(lat, lon, radius_m)` — open "leaving soon" broadcasts at free lots in range (the claimable feed).
- **`GET /community/handoff/nearby`** — the feed (facility name + leaving_at + `mine` flag).
- **`POST /community/handoff/{id}/claim`** — a nearby driver claims (409 if taken).
- **`POST /community/handoff/{id}/confirm`** — the claimer's on-site arrival confirms; **both earn** (403 if not present).

### Relay UI
- **FacilityCard**: a free public lot (truck_stop/rest_area) gets a **"Leaving soon"** action → broadcasts a handoff (backend proves geofence presence; never an M6 bookable lot).
- **MapSurface**: fetches nearby open handoffs on mount; a **"N opening nearby"** banner opens the **HandoffSheet** — the claimable feed with how soon each opens; tap **Claim** (your own broadcast shows "Yours"). `api.js`: `fetchNearbyHandoffs` / `broadcastHandoff` / `claimHandoff`.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 274 passed** (was 273; +1 relay API: broadcast → nearby → claim → re-claim 409).
- UI: **vitest 80 passed** (was 78; +2: HandoffSheet claim, FacilityCard free-lot emit) · `vite build` clean · six-locale completeness at **165 keys**.
- **Live check:** `GET /community/handoff/nearby` returns `200 []`; guards fire (broadcast without presence/valid free-lot → 4xx). Full broadcast→nearby→claim proven in the API test (presence set up in-session).

## 2. Decisions made (append to Decision Log)

112. **The relay's claimable feed is a facility-proximity query, not a subscription.** `nearby_handoffs` reuses `f02.nearest` (all types) then filters OPEN handoffs — the same geo primitive the map/parking/fuel corridors use. No new geo code, no polling; the Map fetches it once on open.
113. **Broadcast lives on the facility card, claim lives in a Map banner+sheet.** The two sides of the relay have different contexts: you broadcast *the lot you're at* (card action, presence-gated by the backend), you claim *from a feed* (a "N opening nearby" banner → sheet). Composed under §22 (design silent on M10 placement).
114. **"Mine" is surfaced, not hidden.** Your own broadcast appears in the feed tagged "Yours" and isn't claimable — honest over filtering it out, and it confirms to the broadcaster that their spot is live for others.

## 3. Exact next task — continue the backlog

- **Fleet-selection flow** — make `/fleet` live (create/pick a fleet → live `/fleet/{id}/report|claims`). Recommended next (the last fixture-backed portal).
- **M5 condition-capture / incident flows** (camera-first capture; backend shipped).
- **Offline read-cache (F12)** across Map/Docs/Booking/Fuel/Voice/Load.
- **Synthetic full-platform e2e** across M1–M12 (a single test that walks map → book → fuel → load→arrive→file → audit → relay → fleet).
- **The other two web portals** (Property-Owner, Public Scorecard, §18).

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name.

**Recommendation:** the **fleet-selection flow** — it's the last surface still fixture-only, and finishes making every built module live in-app. After that, a **synthetic full-platform e2e** to lock the whole thing down.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **165 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged. *(Reminder: `docker compose -f infra/docker-compose.yml restart api` after adding endpoints — the dev server doesn't hot-reload; tests always run fresh.)*

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 · API http://localhost:8008 (community routes now include `/handoff/nearby`, `/handoff/{id}/claim|confirm`).
Suite: **pytest 274 · vitest 80 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete.** Post-build hardening: the spot-handoff relay is live (this session). Prior: detention loop closed (028), live Meter (027), M9/M11/M8 UIs (026). Backlog in §3 — the fleet portal is the last fixture-only surface.

## 8. Commits this session (local only, never pushed)

`809fcfc` HANDOFF-028 → `fd174cc` relay endpoints → `474791b` relay UI (+ this handoff). **84 commits** on `main`, never pushed.

*— End of session. Next: the fleet-selection flow (make `/fleet` live), then a synthetic full-platform e2e across M1–M12. Activation seams await owner/BD inputs (§4).*
