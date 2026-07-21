# HANDOFF-046 — GET /load/active (resume The Meter on a fresh device)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live and browser-reachable via /dev, offline fully a mode, admin console operational, M6 self-serve, two F13-config knobs live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–045 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-045)

**`GET /load/active`** closes the active-load lifecycle: a driver's current stop is now recoverable server-side, so a **fresh device (or cleared local state) can resume The Meter** without the client-persisted `activeStopId`.

### Backend
- **F5 query** (`f05_load.public.active_stop_for_account`): the most recent **armed** stop across the account's loads (`Stop.status == armed`, join `Load` on `account_id`, `created_at desc`). Arm is the active marker — arrival is derived from geofence presence, not a status change, so a stop stays "armed" through its life. Exported via public (import-linter clean, 29/29).
- **`GET /load/active`** (`api/app/api/load.py`) — session-required; returns `{stop_id}` (or `null`). Declared **before** the `/{stop_id}` routes so the static path wins.

### UI — `LoadSurface`
- On mount, when there's **no local `activeStopId`** and the driver is signed in, it calls `fetchActiveLoad()` (adopts the returned stop as active) before falling back to the demo Meter. `fetchActiveLoad` sets the active stop so the existing `loadMeter()` path opens the live Meter. The resume is guarded on `isAuthenticated` so a logged-out visitor still lands on the demo synchronously (no behavior change).

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 301 passed** (was 298; +3: active resumes the armed stop, null when none, requires auth, per-account isolation).
- UI: **vitest 99 passed** (+1: a session with no local stop recovers it from `/load/active` and opens the live Meter) · `vite build` clean · six-locale completeness at **261 keys** (no new keys).
- **Live smoke:** `GET /load/active` → **401** unauth; `{"stop_id": null}` with nothing armed; the **exact created stop id** after a load.

## 2. Decisions made (append to Decision Log)

165. **"Active" = the most recent ARMED stop for the account; there is no separate departed/completed transition yet.** `arm_stop` sets `status=armed`; `arrive`/`meter` never change it (arrival is geofence-derived). Ending a load is currently a client-only clear of `activeStopId`, so a stopped-then-resumed driver could re-surface a load they "ended" on another device — an accepted edge for now. A future `POST /load/{stop}/end` setting `departed` would make it exact; not needed for the resume use case.
166. **The resume is a client fallback, not a replacement for local state.** `activeStopId` in localStorage stays the fast path; `/load/active` only fires when it's empty and a session exists. This keeps the common case zero-latency and makes the server the source of truth only on a cold start. Ordering ties within a single DB transaction (Postgres `now()`) are a test artifact — real armings are separate transactions with distinct `created_at` (so the test asserts null/single/isolation, not multi-armed order).

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input):
- **More F13-config seams** — M10 `REDEEM_CENTS_PER_POINT`/`RATE_LIMIT_PER_DAY`, M3 free-time default (the HANDOFF-041 pattern). **Recommended next** (each small and self-contained).
- Small polish: approved-review snippets on the public scorecard; fold moderation decisions into the audit feed; **gate `/dev` behind a dev-mode flag before any deploy**; optionally a `POST /load/{stop}/end` (departed) so `/load/active` is exact.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), brand name. Flip these on in the admin console once gates are satisfied.

**Recommendation:** wire the **M3 free-time / rate default** as an F13-config knob (the third exemplar, and the one closest to the money) or pivot to the small-polish items. Both low-risk.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · locale native review (F15, gate green at **261 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

**Resume test:** sign in as driver (via `/dev`), start a load on the **Load** tab, then clear the browser's localStorage and reload `/load` — the Meter re-opens from `/load/active`. API `GET /load/active` (session).
Suite: **pytest 301 · vitest 99 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live and browser-reachable via /dev; active-load lifecycle now resumable; integration e2e green; offline fully a mode; five product surfaces + a dev directory; admin console operational with full accountability; M6 marketplace self-serve; two F13-config knobs live; fleet claims desk shows broker names.** Hardening to date: GET /load/active (046), dev directory + counterparty names (045), M10 earn config (044), audit-log view (043), owner spot CRUD (042), config consumer (041), richer admin console (040), incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console v1 (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3.

## 8. Commits this session (local only, never pushed)

`8fc26e1` counterparty names → this: GET /load/active (+ this handoff). **111 commits** on `main`, never pushed.

*— End of session. Next: an F13-config seam (M3 free-time) or small polish (scorecard snippets, gate /dev, POST /load end). Activation seams await owner/BD inputs (§4).*
