# HANDOFF-013 — M1 complete (backend + UI + HTTP API, live pipeline)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–F15 complete. **M1 Road Intelligence Map functionally complete** (backend + first driver UI + HTTP API; status pipeline live over HTTP). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 (Foundation DoD), HANDOFF-012 (M1 backend/UI).

---

## 1. What now exists and passes (delta since HANDOFF-012)

**New: the M1 HTTP API layer + UI wiring + the `--on-accent` design resolution.**

### API layer — `api/app/api` (presentation layer above modules)
- **F1 session auth:** `POST /auth/register` (attaches driver role, no activation) + `POST /auth/login` → bearer token; `current_account` dependency resolves it. Pluggable-registry seam keeps OAuth/OTP future-proof.
- **M1 routers:** `GET /map/overlay` (rig/preset/amenity), `GET /map/corridor`, `POST /map/report` — thin over `m01_map.public`. **CORS** scoped to the LOCKED UI origins (9008/3008).
- **Live status pipeline:** `submit_status` now refreshes the belief inline, so **report → aggregate → pin badge is live under 60s** (M1 DoD) — proven over HTTP by API tests.
- Import boundaries intact: `app.api` imports module/foundation **publics only** (29 contracts still KEPT). 5 API tests via TestClient with `get_db` overridden to the transactional test session.

### UI wiring
- `ui/src/core/api.js` — fetch client (bearer token in memory; `login`/`fetchOverlay`/`report`). `MapSurface` tries the live overlay and **falls back to fixtures** when unauthenticated/offline (a login surface lands with F1 UI).

### Design resolution (design-prd §23)
- **`--on-accent` resolved** (owner deferred to best judgment): filled primary buttons use **`--accent-fill` = shield-600** with a **white `--on-accent`** label → AA/AAA in both themes (dark 5.93:1, light 7.75:1). `shield-500` stays the accent for links/active/focus. §23 entry marked **approved**; verified in `contrast.test.js`.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 150 passed** (Common Ground 136 + M1 module 9 + API 5).
- UI: **vitest 42 passed**.
- **Live API smoke:** routes registered; register→token; overlay 401 without token / 200 with; CORS preflight 200 from `:9008`.

## 2. M1 Definition of Done (PRD §8.1) — status

| DoD item | Status |
|---|---|
| Status pipeline live end-to-end (report → aggregate → pin) < 60s | ✅ verified over HTTP (inline belief refresh) |
| Contribution-with-proof flow shipped | ✅ backend (F10 presence-gated + points) + `POST /map/report` + Report sheet UI |
| Offline: contributions queue via F12 | ✅ (`queue_status_offline`) |
| Map performant to 50k POIs | ⏳ not load-tested (needs real tiles + seeded data; note) |
| Offline **read** region cache | ⏳ client-side cache not yet built (F12 read-side; a UI follow-up) |
| Live Mapbox tiles | ⏳ token placeholder canvas (awaiting owner token) |

**M1 is functionally complete and behind its F13 flag.** The three ⏳ items are refinements (perf load-test, client read-cache, tiles) tracked below — none block M2.

## 3. Decisions made (append to Decision Log)

47. **API layer lives in `app.api`** — the presentation/composition layer above modules. It imports module + foundation **publics only** (never internals); routers stay thin, all logic in modules. `get_db` is a FastAPI dependency over `core.db.get_session`; tests override it to the transactional session for isolation.
48. **Reporter's own contribution refreshes the belief inline** (`submit_status` → `update_belief`), making the M1 pipeline live under 60s without waiting on a batch worker. (Batch re-aggregation across all contributors remains a worker job later.)
49. **`--on-accent` / `--accent-fill`** resolved (see §1). Reusable pattern for every filled-accent button.

## 4. Exact next task

**Two small M1 follow-ups are optional-now; the build-law next module is M2. Recommend: proceed to M2, tracking the M1 ⏳ items.**

**Plan M2 — Facility Intelligence & Scorecard** (PRD §8.2), plan-first:
- Facility profile per `shipper_receiver`: attributes, structured 10-aspect ratings, moderated free-text reviews (F14 moderation queue).
- **Objective dwell statistics** from F3/F4 stop events (median/percentile by arrival-hour, sample sizes always shown).
- Detention-risk indicator (from M3 later; heuristic/empty until then).
- Post-stop micro-review prompt (geofence EXIT trigger, points).
- **Semantic review search** via F9 embeddings (already built: `embed_and_store`/`search_similar`).
- Public scorecard (web surface, design-prd §18 — later).
- Backend module `m02_facility_intel` (may import `m01_map.public` + foundation publics). Behind F13 flag. Then its UI (Facility profile surface, reachable from a map pin — cross-link, NAV-5).

**M1 follow-ups to fold in when convenient (or as owner priorities):** F1 **login UI** (so the browser uses live API not fixtures), offline **read** region cache, 50k-POI perf pass, and **Mapbox tiles** (owner token).

## 5. Blockers / owner questions

1. **Mapbox token** — the only thing between the placeholder canvas and live tiles. Drop into `infra/.env` (gitignored); I'll wire it.
2. **Locale wording** for pa/uz/so/ru/es (incl. new M1 strings) — native review pending (F15); completeness gate is green.
3. Standing activation seams (unchanged): timestamping/PDF (F4), Stripe/Connect + points rate (F7), Twilio/FCM/email (F8), model keys + budgets + embedding dim (F9), MinIO bucket (F6), collection partner (M3), brand name.

*(The `--on-accent` question from HANDOFF-012 is now resolved — no longer open.)*

## 6. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 7. How to run (all Docker) — stack is UP

| Surface | URL |
|---|---|
| Driver app (M1 shell + Map) | http://localhost:9008 |
| API (+ `/docs`, `/auth/*`, `/map/*`) | http://localhost:8008 |
| MinIO http://localhost:9019 · Mailpit http://localhost:8038 | |

Admin (dev): `admin@longhaul.local` / `longhaul-admin-dev`. Suite: **pytest 150 · vitest 42 · 29 contracts · ruff clean**, migrations through `0014`.
UI dep changes → recreate ui: `docker compose -f infra/docker-compose.yml up -d --force-recreate --renew-anon-volumes ui`.

## 8. Build progress

**Common Ground F1–F15: complete.** **M1: functionally complete** (backend + UI + API; 3 refinement items tracked). Next: **M2** → … → M12.

## 9. Commits this session (local only, never pushed)

… `f1a553d` M1 backend → `09622fa` M1 frontend → `91bd679` HANDOFF-012 → `5531dd3` M1 API + on-accent (+ this handoff commit). 36 commits total on `main`.

*— End of session. Next: plan M2 (plan-first); fold in the Mapbox token + M1 follow-ups as priorities allow.*
