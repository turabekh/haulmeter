# HANDOFF-012 — M1 Road Intelligence Map (backend + first driver UI)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground complete (F1–F15). **M1 backend + first driver UI built, tested, green in Docker.** Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 for the Foundation-DoD milestone; 001–010 for per-component detail.

---

## 1. What now exists and passes (delta since HANDOFF-011)

Everything from HANDOFF-011 holds (F1–F15, Foundation DoD met, light theme). **New:** M1 — the first module and first driver UI.

### M1 backend — `api/app/modules/m01_map` (PRD §8.1)
Thin composition over foundation publics (import-linter: `m01 → foundation.*.public` only). No owned tables.
- Rig/amenity-aware **POI overlay with presets** (Drive/Tonight/Work/Fuel, §11.3); Tonight sorts by parking availability. Live status/badges from F10 beliefs via F11.
- **Corridor view** (F11 heading-cone). **Heuristic parking-fill prediction** with basis always surfaced (explicitly heuristic until M8, §11.7).
- **One-tap status contribution**: online via F10 (geofence-presence-gated, points via F7) and offline via F12 (queued, applied once). **External-nav deep-link** handoff (no in-house routing). F13 flag `m01_map` + F14 admin view/analytics. 9 tests.

### M1 frontend — first driver UI (mobile-first, tokens-only)
- **Custom token components** (`ui/src/core/components`, §19 Q-4 — zero Quasar defaults): TabBar (5 labeled tabs, no hamburger), StatusStrip (+voice mic), StatusPill, BottomSheet, PresetChips, MapCanvas (token placeholder + shaped pins; tiles are a seam), FacilityCard (one primary CTA + Navigate), CorridorStack, ReportSheet.
- **Core logic** (swappable-UI, §19): driver state machine (SM-4, one place; DRIVING stamps `data-state`), theme control (system + manual, §6.1 C-3), reactive i18n (six locales), presentation helpers (honest freshness/stale, §11.7).
- **Map surface** (§10.1): presets, report chip, facility sheet, DRIVING → Corridor mode — **fixture-backed pending the M1 HTTP API**. Load/Money/Docs/More are calm placeholders. Vue Router five-tab nav; App scaffold (§7.2); ≤480 dp column.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 145 passed** (Common Ground 136 + M1 9).
- UI: **vitest 42 passed** (contrast both themes + `--on-accent`; six-locale completeness incl. new M1 keys; pseudo-locale; state machine; presentation; i18n; components — tabs/presets/facility card/corridor).
- Dev server boots clean; M1 shell + Map surface live at **http://localhost:9008**.

## 2. Decisions made (append to Decision Log)

44. **Quasar-framework integration deferred; signature surfaces custom on tokens.** design-prd §19 Q-4 mandates the tab bar, cards, sheets, map overlays, corridor cards be custom-built with **zero Quasar defaults**; M1's surfaces need no Quasar behavior components. Building them custom (Vue 3 + Router) is fully §19-compliant and avoids Material-default leakage (Forbidden #12). Quasar's behavior plumbing (Q-3: QForm/QVirtualScroll/QDialog) integrates when a screen first needs it (M3 claim review, M6 checkout), wired with Q-1 tokens + Q-2 material-off then. *(This refines the approved-plan phrase "scaffold Quasar" — flagged for owner; reversible.)*
45. **`--on-accent` token — PROPOSED (owner decision needed).** Filled-shield buttons need a label color §6/§8 don't specify. Smallest-reversible choice (§0.3): dark = ink-0 (4.24:1, just under AA on the mid-luminance dark shield), light = white (5.93:1). Logged design-prd §23 PROPOSED. **Owner: accept as-is, or fill dark primary buttons with `shield-600` for a white label at 5.93:1 AA.**
46. **M1 UI is fixture-backed; the HTTP API is the next seam.** `ui/src/core/fixtures.js` mirrors the M1/F11 pin shape exactly; swap it for a fetch client behind the same interface once the API exists — components unchanged.

## 3. Exact next task

**Complete M1 to its DoD by wiring the HTTP API + UI, then move to M2.** M1's DoD (PRD §8.1) needs the status pipeline live end-to-end (report → aggregate → pin) — the backend logic exists; the UI must consume it over HTTP.
- **API layer (`api/app`):** FastAPI routers exposing M1 (`GET /map/overlay`, `GET /map/corridor`, `POST /map/report`, prediction) + **F1 session auth dependency** (resolve_session) + **CORS** for the frontend origin (`:9008`) + Pydantic response schemas. Add API tests (httpx TestClient). Keep routers thin over module publics; do not let routers reach foundation internals.
- **UI wiring:** replace `fixtures.js` with a fetch client (same interface); add offline read-cache (F12 client concern) as a thin layer. Verify the report → belief → pin refresh path.
- **Owner inputs to fold in:** the `--on-accent` decision (#45); a **Mapbox token** (into `infra/.env`, gitignored) to light up real tiles behind `MapCanvas`.
- **Then M2 — Facility Intelligence & Scorecard** (PRD §8.2): facility profiles, objective dwell stats from F3/F4, structured reviews (moderation via F14), semantic review search (F9 embeddings), public scorecard. Present an M2 plan first (plan-first).

## 4. Blockers / owner questions

1. **`--on-accent` (design-prd §23 PROPOSED)** — accept dark 4.24:1, or switch dark primary buttons to `shield-600` fill (5.93:1)? (Decision #45.)
2. **Mapbox token** — needed to render live tiles (M1 map canvas is a token placeholder until then). Paste into `infra/.env` (gitignored); I'll wire it.
3. **Locale wording** for pa/uz/so/ru/es — new M1 strings added best-effort; native-speaker review pending (F15). CI completeness gate is live (all six present).
4. Standing activation seams (unchanged): timestamping/PDF (F4), Stripe/Connect + points rate (F7), Twilio/FCM/email (F8), model keys + cost budgets + embedding dim (F9), MinIO bucket (F6), collection partner (M3), brand name.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged. (A Mapbox token, when provided, goes in `infra/.env` only.)

## 6. How to run (all Docker) — stack is UP

| Surface | URL |
|---|---|
| Driver app (M1 shell + Map) | **http://localhost:9008** |
| API | http://localhost:8008 (`/health`, `/docs`) |
| MinIO console | http://localhost:9019 · Mailpit http://localhost:8038 |

Admin (dev): `admin@longhaul.local` / `longhaul-admin-dev`. Suite: **pytest 145 · vitest 42 · 29 contracts · ruff clean**, migrations through `0014`.

Note: after adding UI deps, recreate the ui container with a fresh node_modules volume: `docker compose -f infra/docker-compose.yml up -d --force-recreate --renew-anon-volumes ui`.

## 7. Build progress

**Common Ground F1–F15: complete.** Modules: **M1 backend + UI done** (pending HTTP-API wiring for full DoD). Next: M1 API layer → M2 → … → M12.

## 8. Commits this session (local only, never pushed)

… `3890b3f` HANDOFF-011 → `eab0083` light theme → `edbf8e3` handoff update → `f1a553d` M1 backend → `09622fa` M1 frontend (+ this handoff commit).

*— End of session. Next: wire the M1 HTTP API + UI (with the `--on-accent` and Mapbox decisions), then plan M2.*
