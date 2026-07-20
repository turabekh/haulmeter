# HANDOFF-036 — F12 idempotent evidence-sync (offline captures apply exactly once)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live, offline read+write cached, admin console live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–035 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-035)

"Offline is a mode" is now complete for **transactional evidence** too. HANDOFF-033 queued fire-and-forget crowd writes (report/Q&A/review); this session makes the **transactional captures** (condition photos, incidents) queue offline and **apply exactly once** on reconnect via the F12 idempotent-ingest primitive — no duplicate hash-chain.

### Backend — F12-wired capture endpoints (`api/app/api/m05_protection.py`)
- `POST /protection/condition/{capture_id}/photo` and `POST /protection/incident` now accept an **`Idempotency-Key`** header and route the effect through **`offline.ingest(account, key, kind, payload, occurred_at, handler)`**: the same `(account, key)` applied twice yields exactly one effect (`applied:true` then `applied:false`). Without a key they behave as before (direct).

### Client — stable idempotency keys through the write-queue (`ui/src/core/api.js`)
- `queuedPost` now generates a **stable idempotency key** per write (`crypto.randomUUID` with fallback), sends it as `Idempotency-Key`, **stores it in the queue item**, and **re-sends the same key on every replay**. So even a write that reached the server before the dead zone (response lost → client re-queues) is deduped on replay.
- `addConditionPhoto` now routes through the queue (offline-safe); `fileIncident` already did.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 281 passed** (was 280; +1: replay = one photo, `applied` flips true→false, `photo_count` stays 1).
- UI: **vitest 88 passed** (write-queue test now also asserts the `Idempotency-Key` on replay) · `vite build` clean.
- **Live smoke:** condition photo with `Idempotency-Key: K1` → `applied=true, count=1`; replay K1 → `applied=false, count=1` — exactly-once, chain stays length 1.

## 2. Decisions made (append to Decision Log)

137. **Two tiers of offline write, by write semantics.** Crowd contributions (report/Q&A/review) use at-least-once client replay (Decision 127) — cheap, and a lost one isn't worth idempotency plumbing. Transactional evidence (condition photos, incidents) uses the F12 **idempotent ingest** so replays apply exactly once and never duplicate a hash-chain. The client mechanism is one queue; the difference is whether the server endpoint routes through `offline.ingest`.
138. **The idempotency key is generated once, at first send, and stored.** It must be stable across replays for the server to dedupe, so it lives in the queue item — not regenerated on flush. `crypto.randomUUID` in the browser, with a timestamp+random fallback.
139. **A key is sent on every queued write; the server honors it only where wired.** `queuedPost` always attaches `Idempotency-Key`; endpoints not routed through `offline.ingest` (the crowd captures) simply ignore it — harmless, and it future-proofs turning any capture idempotent by wiring its endpoint.
140. **`applied` is returned so the client/UI can tell a fresh apply from a dedup.** Not used for control flow yet (the capture UI advances optimistically either way), but it's the honest signal for a future "synced" confirmation.

## 3. Exact next task — continue the backlog

Offline is now complete (reads cache, crowd writes queue, evidence applies exactly-once). Remaining hardening (no owner input):
- **The other two web portals** (Property-Owner, Public Scorecard, design-prd §18) — reuse `meta.portal` + the fleet/admin portal pattern. **Recommended next** (the last §18 surfaces).
- **Incident capture sheet** (M5-FR4) — small: kind + note → `/protection/incident` (now idempotent).
- **Richer admin console** — analytics funnels + config editing (F14 `funnel`/`set_config` ready).
- Small backend polish: counterparty **names** in the fleet claims desk; `GET /load/active`.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name. Flip these on in the **admin console** once gates are satisfied.

**Recommendation:** the **Public Scorecard** web portal (§18) — it's the public-facing face of the M2 facility data (dwell benchmarks, ratings) and the closest to a growth/SEO surface; fully buildable on existing M2 + M12 data-product publics.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **199 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 — start a load → arrive → "Capture cargo condition"; go offline mid-sequence and the photos queue with idempotency keys, then sync exactly-once on reconnect. API `/protection/condition/photo` + `/protection/incident` honor `Idempotency-Key`.
Suite: **pytest 281 · vitest 88 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; integration e2e green; offline is fully a mode (reads cache, crowd writes queue, evidence applies exactly-once); three web portals (driver, fleet, admin).** Hardening to date: evidence-sync (036), admin console (035), M5 capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3.

## 8. Commits this session (local only, never pushed)

`f1b7dbc` HANDOFF-035 → `ee112a6` F12 evidence-sync (+ this handoff). **98 commits** on `main`, never pushed.

*— End of session. Next: the Public Scorecard web portal (§18, on M2 + M12 data-product publics), then the Property-Owner portal and the incident sheet. Activation seams await owner/BD inputs (§4).*
