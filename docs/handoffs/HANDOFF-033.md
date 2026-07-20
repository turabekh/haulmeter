# HANDOFF-033 — Offline write-queue (the daily loop survives a dead zone)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live, full-platform e2e green, reads cache offline. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–032 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-032)

HANDOFF-032 made **reads** survive offline (read-cache). This session makes **writes** survive too — completing design-prd §15.1 ("offline is a MODE, not an error; everything saves to your phone").

### `ui/src/core/api.js` — the write-queue
- `queuedPost(path, body)`: on a **genuine network failure** it stores the write to `localStorage` and returns `{queued: true}` (the capture is saved, not lost); a **server rejection (4xx/5xx)** rethrows so the caller handles it.
- `flushQueue()`: replays queued writes on reconnect. Queued items were never sent, so at-least-once replay is **effectively once**; a server-rejected replay is **dropped** (not retried forever).
- `pendingWrites` (ref) drives the indicator. Routed the field captures: **report** (parking status — the §15.1 canonical), **askQuestion** (facility Q&A), **submitReview**.
- `logout()` clears the queue too (no cross-driver bleed).

### `StatusStrip` + `App.vue`
- The strip shows a **subtle `CloudOff` + count** pending glyph (silent sync, never a toast parade — §15.1).
- `App.vue` calls `flushQueue()` on mount and on the browser's `online` event; the strip binds `online` + `pendingWrites`.

### Verified this session (in compose)
- UI: **vitest 84 passed** (was 83; +1: queue-offline → replay-on-reconnect) · `vite build` clean · six-locale completeness at **172 keys**.
- Backend untouched: **pytest 276** · 29 contracts · migrations `0023`.

## 2. Decisions made (append to Decision Log)

125. **Client-side POST replay, not the F12 SyncEnvelope protocol (yet).** The `f12_offline` backend has an idempotent `ingest`/`get_receipt` batch-sync protocol; this UI pass uses simpler client-side replay of the real endpoints, which is correct because queued items never reached the server (so replaying once creates once). Adopting the backend envelope + idempotency keys is a later hardening step for higher-volume/duplicate-risk writes (evidence packs), noted not done.
126. **Only fire-and-forget crowd captures are queued** — report, Q&A, review. Transactional writes with money or immediate confirmation (book, pump code, generate-claim, handoff) are NOT queued: the driver expects a real receipt, and a stale queued booking could double-charge or claim a taken spot. Those fail→retry online; queuing them needs true backend idempotency first.
127. **A server-rejected replay is dropped, not retried forever.** If a queued report is rejected on sync (e.g., stale, moderated), the queue drops it rather than looping — an unsent crowd signal isn't worth a poison-pill retry. Network failure keeps it queued; only a *reached-server rejection* discards it.
128. **Sync is silent; the only tell is the count.** Per §15.1 no toast parade — the pending glyph appears while items wait and disappears when they drain. The driver never manages sync.

## 3. Exact next task — continue the backlog

Remaining cross-cutting hardening (no owner input):
- **M5 condition-capture / incident flows** — the camera-first evidence sequences (M5 backend shipped since HANDOFF-017); these are the transactional captures that would benefit from the **F12 SyncEnvelope + idempotency** path (Decision 125). **Recommended next** — it pairs the capture UI with the proper offline-evidence sync.
- **The other two web portals** (Property-Owner, Public Scorecard, §18) — reuse `meta.portal` + the fleet-portal pattern.
- Small backend polish: counterparty **names** in the fleet claims desk; `GET /load/active`.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name.

**Recommendation:** **M5 condition-capture / incident flows** — the last major deferred driver UI (backend shipped), and a natural place to wire the F12 evidence-sync envelope for transactional captures.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **172 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 — go offline (DevTools), report a parking status → it queues (a count appears on the strip); go back online → it syncs silently and the count clears.
Suite: **pytest 276 · vitest 84 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; integration e2e green; reads cache AND writes queue offline.** Hardening to date: write-queue (033), read-cache (032), full-platform e2e (031), fleet portal live (030), relay UI (029), detention loop closed (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3, led by M5 capture flows.

## 8. Commits this session (local only, never pushed)

`7d0ddb1` HANDOFF-032 → `4d5f38c` F12 write-queue (+ this handoff). **92 commits** on `main`, never pushed.

*— End of session. Next: M5 condition-capture / incident flows (camera-first capture; wire the F12 evidence-sync envelope for transactional captures), then the remaining §18 web portals. Activation seams await owner/BD inputs (§4).*
