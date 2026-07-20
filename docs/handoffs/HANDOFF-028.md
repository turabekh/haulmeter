# HANDOFF-028 — Detention loop closed (arrive → accrue → file a claim)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–027 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-027)

HANDOFF-027 made **The Meter live** (create load → arrive → running clock). This session **closes the loop**: the running clock now **files a claim**. The Load tab's state-dependent CTA is wired end-to-end to M3.

### Load API — notice + claim (`api/app/api/load.py`)
- **`POST /load/{stop_id}/notice`** — M3 `send_detention_start_notice` via the F8 gateway seam (no-ops while still within free time — nothing owed yet).
- **`POST /load/{stop_id}/claim`** — M3 `generate_pack`: the running clock becomes a **GPS-backed, chain-valid detention pack** + an opened receivable (invoice mode) or an exported pack (company-driver mode). Returns `{amount_cents, state, chain_valid, receivable_ref}`.
- Both **409 before arrival** (no claim yet). `claim_id` added to the `GET /meter` response.

### Load-tab UI (`LoadSurface`)
- Primary CTA by phase: pre-arrival → **I've arrived** · within free → **Send notice** · accruing → **Generate claim**. `api.js`: `sendDetentionNotice` + `generateClaim`.
- On filing, a **"Claim filed · $X"** banner appears with a link to the Money tab.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 273 passed** (was 271; +2 load API).
- UI: **vitest 78 passed** (was 77; +1 accruing→file) · `vite build` clean · six-locale completeness at **156 keys**.
- **Live end-to-end smoke:** `POST /load` → `arrive` → `POST /claim` = `state=exported`, `chain_valid=true`. The detention loop (arrive → accrue → file) is real end-to-end. *(Note: the dev API server must be reloaded to pick up new endpoints — `docker compose restart api`; tests always run against fresh code.)*

## 2. Decisions made (append to Decision Log)

109. **The claim-filing loop lives on the same `/load/*` surface as the Meter**, wrapping M3's `send_detention_start_notice` and `generate_pack` so the client only ever deals with `stop_id`. No new module, no schema, contracts unchanged (29). The F8 send is the same `RecordingNotificationGateway` dev seam the M3 API uses.
110. **Notice no-ops within free time by design.** `send_detention_start_notice` returns `None` until detention has actually started; the endpoint returns `{sent: false}` rather than sending a premature/false notice — consistent with the "never fake a claim" evidence discipline (an on-time notice only fires when truly owed).
111. **A filed claim within free time exports rather than invoices** (amount 0, company-driver default mode → `exported`). With real accrued detention it invoices and opens a receivable. The Load-tab banner shows whatever amount the pack computed; the receivable then surfaces on the Money tab / DDD.

## 3. Exact next task — continue the backlog

- **M10 handoff-relay UI** — the highest-novelty feature: "leaving in X" broadcast + claim on the Map free-lot pins (`/community/handoff` shipped). Recommended next.
- **Fleet-selection flow** — make `/fleet` live (create/pick a fleet → live report/claims).
- **M5 condition-capture / incident flows** (camera-first capture; backend shipped).
- **Offline read-cache (F12)** across Map/Docs/Booking/Fuel/Voice/Load.
- **Synthetic full-platform e2e** across M1–M12.
- **The other two web portals** (Property-Owner, Public Scorecard, §18).

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **156 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 · API http://localhost:8008 (load routes: create/arrive/meter/**notice**/**claim**). Admin: `admin@longhaul.local` / `longhaul-admin-dev`.
Suite: **pytest 273 · vitest 78 · 29 contracts · ruff clean**, migrations through `0023`. *(If new API endpoints 404 live, `docker compose -f infra/docker-compose.yml restart api`.)*

## 7. Build progress

**F1–F15 + M1–M12: complete.** Post-build hardening: The Meter is live AND files (this session). Prior hardening: active-load API + live Meter (027), M9/M11/M8 deferred UIs (026). Backlog in §3.

## 8. Commits this session (local only, never pushed)

`6fa04a5` HANDOFF-027 → `aea562a` close-the-loop notice/claim wiring (+ this handoff). **81 commits** on `main`, never pushed.

*— End of session. Next: M10 handoff-relay UI (highest-novelty), then the fleet-selection flow. Activation seams await owner/BD inputs (§4).*
