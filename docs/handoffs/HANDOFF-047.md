# HANDOFF-047 — POST /load/{stop}/end (durable end; /load/active is now exact)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live and browser-reachable via /dev, active-load lifecycle resumable + closable, offline fully a mode, admin console operational, M6 self-serve, two F13-config knobs live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–046 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-046)

Closes the correctness gap flagged in HANDOFF-046 (Decision 165): "ending" a load was a **client-only** clear of `activeStopId`, so `/load/active` could resurface an ended load on another device. Ending is now **durable** — it marks the stop `departed` server-side and drops it from the active-stop query.

### Backend
- **F5** `depart_stop(db, stop, occurred_at)` — disarm the geofence + set `status = departed`, `departed_at`. Exported via public (import-linter clean, 29/29).
- **`POST /load/{stop_id}/end`** (`api/app/api/load.py`) — session-required and **ownership-checked** (a driver only ends their own load → 403 otherwise); departs the stop, returns `{stop_id, status}`. After it, `active_stop_for_account` (armed-only) no longer returns the stop.

### UI — `LoadSurface` / `api.js`
- New `endActiveLoad(stopId)`: best-effort `POST /load/{stop}/end`, then clears local `activeStopId` (offline → local clear still happens, server stays armed until the next end). `LoadSurface.endLoad` now calls it (was a bare local clear), then reverts to the demo Meter.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 303 passed** (was 301; +2: end departs the stop and clears active; end rejects another owner with 403).
- UI: **vitest 100 passed** (+1: "End load" POSTs `/load/{stop}/end` then reverts to the demo) · `vite build` clean · six-locale completeness at **261 keys**.
- **Live smoke:** create → `/load/active` shows the stop → `POST /end` returns `status: departed` → `/load/active` returns `{stop_id: null}`.

## 2. Decisions made (append to Decision Log)

167. **Ending a load sets the stop `departed`; `/load/active` stays armed-only.** `depart_stop` disarms the geofence (mirroring the arm on create) and sets `status=departed` + `departed_at`, so the active-stop query (which filters `status==armed`) excludes it. The lifecycle is now pending→armed→departed with arrival still geofence-derived in between. This makes the resume exact: a driver who ends a load on device A won't see it resurface on device B.
168. **The end endpoint is ownership-checked; the older mutation endpoints are not (yet).** `/end` verifies `load.account_id == account.id` (403 otherwise) — the right posture for a new endpoint. The pre-existing `arrive`/`notice`/`claim` endpoints don't check ownership; that's a latent authz gap worth a dedicated pass, but widening it here (or leaving `/end` unchecked to "match") would both be wrong. New code gets the correct check.

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input):
- **Ownership pass on the older load mutations** — add the same `account.id` check to `arrive`/`notice`/`claim` (and audit other stop-scoped endpoints). **Recommended next** (a real, if latent, authz gap; small and high-integrity).
- **More F13-config seams** — M3 free-time/rate default, M10 `REDEEM_CENTS_PER_POINT`/`RATE_LIMIT_PER_DAY` (the HANDOFF-041 pattern).
- Small polish: approved-review snippets on the public scorecard; fold moderation decisions into the audit feed; **gate `/dev` behind a dev-mode flag before any deploy**.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), brand name.

**Recommendation:** the **ownership pass on `arrive`/`notice`/`claim`** — `/end` exposed that these stop-scoped mutations don't verify the caller owns the load. It's a small, correctness/security-positive increment (one helper + a check per endpoint + tests). Then the M3 config seam or the remaining polish.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · locale native review (F15, gate green at **261 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

**End-load test:** sign in as driver (`/dev`) → Load → "Start a load" → "End load"; the stop is departed server-side and `/load/active` returns null. API `POST /load/{stop}/end` (session + ownership).
Suite: **pytest 303 · vitest 100 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live and browser-reachable via /dev; active-load lifecycle resumable AND closable (pending→armed→departed); integration e2e green; offline fully a mode; five product surfaces + a dev directory; admin console operational with full accountability; M6 marketplace self-serve; two F13-config knobs live; fleet claims desk shows broker names.** Hardening to date: end-load (047), GET /load/active (046), dev directory + counterparty names (045), M10 earn config (044), audit-log view (043), owner spot CRUD (042), config consumer (041), richer admin console (040), incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console v1 (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3.

## 8. Commits this session (local only, never pushed)

`75a5c6f` GET /load/active → this: POST /load/end (+ this handoff). **112 commits** on `main`, never pushed.

*— End of session. Next: ownership pass on arrive/notice/claim (the gap /end surfaced), then M3 config seam / small polish. Activation seams await owner/BD inputs (§4).*
