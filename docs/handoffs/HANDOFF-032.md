# HANDOFF-032 — Offline read-cache (the app works in a dead zone)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live, full-platform e2e green. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–031 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-031)

The driver app's defining constraint is intermittent connectivity (design-prd §15.1: **offline is a MODE, not an error**). The core daily reads now **cache**, so the app shows the last-known *real* data in a dead zone instead of a generic fixture, and the status strip tells the honest truth.

### `ui/src/core/api.js` — the read-cache layer
- `apiGet(path, cacheKey)`: caches every successful GET to `localStorage` (namespaced `longhaul.cache.*`). On a **genuine network failure** it serves the cached value and flips the exported **`online`** ref to `false`. A **server error (4xx/5xx)** is *not* offline — it rethrows so the caller still falls back to a fixture.
- Wrapped (the surfaces a driver stares at): **overlay** (Map), **owed** + **earnings** (Money/DDD), **wallet** (Docs), **profile** (Facility), **meter** (Load), **points** (More).
- `logout()` clears the cache — a new driver never sees the last one's reads.

### `ui/src/App.vue`
- The status strip binds to `online` and also listens to the browser's own `online`/`offline` events → the honest "Offline — everything saves to your phone" banner (§15.1, calm `text-2`, never red).

### Verified this session (in compose)
- UI: **vitest 83 passed** (was 81; +2 F12 core tests: serve-cache-offline, rethrow-when-no-cache) · `vite build` clean.
- Backend untouched: **pytest 276** · 29 contracts · migrations `0023`.

## 2. Decisions made (append to Decision Log)

121. **Network failure vs server error are distinguished.** `apiGet` catches only the `fetch` throw (true offline) to go offline + serve cache; a non-`ok` response (401/500) rethrows. So a logged-out 401 or a backend 500 still routes to the fixture fallback, and only real dead-zones flip the offline banner — no false "offline" on a server hiccup.
122. **The cache serves REAL last-known data, fixtures are the floor.** Order of preference on a read: fresh network → cached-real → fixture. The generic fixtures never overwrite a cached real read; they only appear when there's nothing better (never fetched, or offline with no cache).
123. **Read-cache now, write-queue later.** This pass caches GETs. Queuing offline WRITES (book/report/claim/broadcast) with idempotent sync is the F12 backend's job (`f12_offline` is built) and a separate UI pass — noted, not attempted here, to keep the change tight and correct.
124. **Cache is cleared on logout, keyed simply by path.** Per-driver isolation is by wiping `longhaul.cache.*` on logout (the token already scopes who can read); cache keys are the endpoint shape (`owed`, `meter:{id}`, `profile:{id}`), so a redeploy or new query naturally supersedes stale entries.

## 3. Exact next task — continue the backlog

Remaining cross-cutting hardening (no owner input):
- **F12 offline write-queue (UI)** — queue book/report/claim/broadcast/audit writes when offline and sync idempotently on reconnect (the `f12_offline` backend is built). The natural partner to this session's read-cache; completes "offline is a mode" for the whole app. **Recommended next.**
- **M5 condition-capture / incident flows** (camera-first capture; backend shipped).
- **The other two web portals** (Property-Owner, Public Scorecard, §18) — reuse `meta.portal`.
- Small backend polish: counterparty **names** in the fleet claims desk; `GET /load/active`.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name.

**Recommendation:** the **F12 write-queue (UI)** — pairs directly with the read-cache to make every capture path work offline (design-prd §15.1's full promise), and the backend foundation is already there.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **171 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 — kill the network (or DevTools offline) after a read and the daily surfaces keep showing the last real data; the strip flips to "Offline — everything saves to your phone".
Suite: **pytest 276 · vitest 83 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; integration e2e green; core reads cache offline.** Hardening to date: read-cache (032), full-platform e2e (031), fleet portal live (030), relay UI (029), detention loop closed (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3, led by the F12 write-queue.

## 8. Commits this session (local only, never pushed)

`91bdda9` HANDOFF-031 → `554ec82` F12 read-cache (+ this handoff). **90 commits** on `main`, never pushed.

*— End of session. Next: the F12 offline write-queue (UI) — queue captures offline, sync idempotently on reconnect — then M5 capture flows and the remaining §18 portals. Activation seams await owner/BD inputs (§4).*
