# HANDOFF-035 — Minimal F14 admin console (there's an admin page now)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live, offline read+write cached, M5 capture live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–034 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-034)

The owner asked "where's the admin console?" — F14 was backend-only. This session lands the **operator portal**, `platform_admin` gated.

### Backend — `/admin` API (`api/app/api/admin.py`)
Composes **F13** (flags + gates) + **F14** (admin views, moderation) + **F1** (role check).
- `current_admin` dependency — 403 unless the account has the `platform_admin` role.
- **`GET /admin/flags`** → every feature flag with `enabled`, `can_activate`, and its **activation gates** (name + satisfied).
- **`POST /admin/flags/{key}/enable`** (409 if gates unsatisfied) / **`/disable`**.
- **`GET /admin/views`** → the module-registered admin views (F14 `register_admin_view`).
- **`GET /admin/moderation`** + **`POST /admin/moderation/{id}/decide`** `{approve}`.

### UI — `AdminConsoleSurface` (`/admin`)
- A **web-first portal** (design-prd §18, same pattern as the Fleet Workspace: `meta.portal` widens the frame, no tab chrome, shares `ui/core` tokens). **Feature-flag toggles** (a gated flag's toggle is disabled with a `2/3 gates` count), a **module admin-view table**, and the **moderation queue** with approve/reject. A **403 shows the no-access notice** — the console self-gates for non-admins.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 280 passed** (was 277; +3 admin API: gate, flag toggle incl. gated-409, views).
- UI: **vitest 88 passed** (was 86; +2: flags/gates/toggle, 403 no-access) · `vite build` clean · six-locale completeness at **199 keys**.
- **Live smoke:** the seeded `admin@longhaul.local` / `longhaul-admin-dev` → `GET /admin/flags` **200**; a regular driver → **403**.

## 2. Decisions made (append to Decision Log)

133. **The admin surface is a separate web portal, not a driver tab.** `/admin` uses the same `meta.portal` + `chrome:false` mechanism as the fleet portal — desktop-first, tokens shared, not a driver screen (§18). One SPA, three portals now (fleet, admin; public-scorecard/owner still to come).
134. **The role gate lives in a `current_admin` dependency, not scattered checks.** Every `/admin` endpoint depends on it; it reads `account.roles` for `platform_admin` (F1 has no `has_role` helper, so the check is explicit at the API boundary). The UI console *also* self-gates on the 403, but the server is the authority.
135. **The console surfaces gates, it doesn't bypass them.** Enabling a gated flag returns 409 (F13 `GateNotSatisfied`) and the UI disables the toggle with a satisfied/total count — an operator sees *why* M6/M7/M9 can't activate (payment partner, refund policy, etc.) rather than being able to force them. Activation stays honest.
136. **Minimal on purpose.** Flags + views + moderation are the operator essentials; analytics funnels, config editing, and per-module deep views are deferred (F14 exposes `funnel`/`count_events`/`set_config` for a later richer console). This answers the access question without over-building.

## 3. Exact next task — continue the backlog

Remaining cross-cutting hardening (no owner input):
- **F12 idempotent SyncEnvelope for evidence** — safe offline sync for transactional captures (condition photos, incidents, generate-claim) via the built `f12_offline` `ingest`/`get_receipt`. **Recommended next** (completes "offline is a mode" for evidence).
- **Incident capture sheet** (M5-FR4) — small: kind + note → `/protection/incident`.
- **The other two web portals** (Property-Owner, Public Scorecard, §18) — reuse `meta.portal`.
- **Richer admin console** — analytics funnels, config editing (F14 `funnel`/`set_config` are ready).
- Small backend polish: counterparty **names** in the fleet claims desk; `GET /load/active`.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name. **The admin console is now the place these get flipped on** once their gates are satisfied.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **199 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

**Admin console:** log into the driver app at http://localhost:9008 as `admin@longhaul.local` / `longhaul-admin-dev`, then visit http://localhost:9008/admin (feature flags, module views, moderation). API: `http://localhost:8008/admin/*` (platform_admin gated). Re-seed the admin: `docker compose -f infra/docker-compose.yml exec api python -m scripts.seed_admin`.
Suite: **pytest 280 · vitest 88 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; integration e2e green; offline read+write cached; M5 capture live; F14 admin console live.** Hardening to date: admin console (035), M5 capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3.

## 8. Commits this session (local only, never pushed)

`f32562f` HANDOFF-034 → `09de215` F14 admin console (+ this handoff). **96 commits** on `main`, never pushed.

*— End of session. Next: the F12 idempotent SyncEnvelope for evidence captures, or the incident sheet / remaining §18 portals. The admin console is now where module activation flags get flipped on (once gates are satisfied). Activation seams await owner/BD inputs (§4).*
