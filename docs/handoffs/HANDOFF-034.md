# HANDOFF-034 — M5 camera-first cargo-condition capture (the last deferred driver UI)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live, offline read+write cached. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–033 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-033)

The **cargo-condition capture** flow (M5-FR2) — the last major deferred driver UI — is now live. The M5 backend has shipped since HANDOFF-017; this session exposes it over HTTP and builds the camera-first capture screen.

### Backend — condition-capture endpoints (`api/app/api/m05_protection.py`)
- `GET /protection/condition/sequence` → the 4-step guided sequence (`trailer_exterior → seals → load_blocking → reefer_setpoint`).
- `POST /protection/condition/start` `{stop_id, phase}` → opens an F4 evidence log for the stop, returns `{capture_id, sequence}`.
- `POST /protection/condition/{capture_id}/photo` `{prompt, content_b64?}` → appends a **hash-chained F4 photo** (base64 JSON, no `python-multipart` dependency; the chain hashes the bytes; a dev placeholder is synthesized when `content_b64` is absent).
- Also added: `fileIncident` helper (queued) for the existing `POST /protection/incident`.

### UI — `ConditionSurface` (`/protection/condition`)
- A **camera-first, one-decision-per-step** guided flow (S2 dock task, §202): each step shows its label + "Step N of 4" + a **giant camera target** (a styled `<input type=file accept=image/* capture=environment>` — opens the rear camera on a phone). Each shot reads the file to base64 → appends the F4 photo → advances; "Condition documented" on completion.
- Reached from the **Load tab** ("Capture cargo condition", shown when there's a live active stop). Ties to `activeStopId`.

### Verified this session (in compose)
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 277 passed** (was 276; +1 condition-capture API walking the 4 steps).
- UI: **vitest 86 passed** (was 84; +2: guided-first-step, no-stop prompt) · `vite build` clean · six-locale completeness at **187 keys**.
- **Live smoke:** create load → `condition/start` → photo 1 (count 1) → photo 2 (count 2) — the hash-chained sequence builds.

## 2. Decisions made (append to Decision Log)

129. **Condition photos ride base64 JSON, not multipart.** `python-multipart` isn't installed and adding it means a dependency + image rebuild; base64 in the JSON body keeps the endpoint dependency-free and the F4 chain hashes the bytes exactly the same. The web file input reads the photo via `FileReader` → base64. Revisit multipart only if payload size becomes a problem at real image resolution.
130. **A dev placeholder is synthesized when no image is sent** (`f"photo:{prompt}"`), so the evidence *chain* is exercisable end-to-end without a real camera (tests, smoke). Real captures send `content_b64`; the chain integrity is identical.
131. **Condition/incident captures are NOT on the crowd write-queue.** They're transactional evidence — a hash-chained pack that protects the driver in a dispute — so they must not silently queue-and-maybe-drop like a parking report. Offline, the capture fails and the driver retries; the proper offline path is the F12 **idempotent SyncEnvelope** (Decision 125), which is the noted follow-up for these writes.
132. **The incident sheet is deferred, its endpoint + `fileIncident` helper are ready.** The headline M5-FR2 camera sequence shipped; the simpler incident capture (M5-FR4) is a small follow-up (kind + note → `/protection/incident`) — deferred to avoid Load-tab clutter and extra kind-label localization this pass.

## 3. Exact next task — continue the backlog

Remaining cross-cutting hardening (no owner input):
- **F12 idempotent SyncEnvelope for evidence** — wire the built `f12_offline` `ingest`/`get_receipt` protocol so transactional captures (condition photos, incidents, generate-claim) queue-and-sync safely offline. The proper completion of "offline is a mode" for evidence. **Recommended next.**
- **Incident capture sheet** (M5-FR4) — small: kind + note → `/protection/incident` → confirmation.
- **The other two web portals** (Property-Owner, Public Scorecard, §18) — reuse `meta.portal`.
- **A minimal F14 admin console** (web-first portal: feature-flag toggles, moderation queue, registered admin views, analytics funnels) — the user asked about admin access; there's no admin UI yet (F14 is backend-only). Fully buildable without owner input.
- Small backend polish: counterparty **names** in the fleet claims desk; `GET /load/active`.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name.

**Note on admin access (owner asked):** there is **no admin console yet** — F14 is backend-only (registers admin views, moderation, analytics; no HTTP router, no frontend). The seeded `admin@longhaul.local` / `longhaul-admin-dev` account (via `scripts/seed_admin.py`) is a real `platform_admin` F1 account but currently only logs into the driver app. Today's ops surfaces: the **API docs** at `http://localhost:8008/docs` (exercise every endpoint) and the **Fleet Workspace** at `http://localhost:9008/fleet`. A minimal admin console is a good next backlog item (§3).

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **187 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 → start a load → arrive → "Capture cargo condition" walks the 4-step camera sequence. API http://localhost:8008 (condition routes under `/protection/condition/*`). *(Restart api after adding endpoints — dev server doesn't hot-reload.)*
Suite: **pytest 277 · vitest 86 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; integration e2e green; offline read+write cached; the last deferred driver UI (M5 condition-capture) shipped.** Hardening to date: M5 capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3.

## 8. Commits this session (local only, never pushed)

`641e4c6` HANDOFF-033 → `78d790c` M5 condition-capture (+ this handoff). **94 commits** on `main`, never pushed.

*— End of session. Next: the F12 idempotent SyncEnvelope for evidence captures (safe offline sync for transactional writes), or a minimal F14 admin console (the owner asked about admin access). Activation seams await owner/BD inputs (§4).*
