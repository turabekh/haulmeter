# HANDOFF-039 — Incident capture sheet (M5-FR4; the last M5 UI gap closed)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** F1–F15 + M1–M12 complete, every surface live, offline fully a mode, all three §18 web portals live. Post-build hardening. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 complete), 026–038 (hardening).

---

## 1. What now exists and passes (delta since HANDOFF-038)

The **incident capture sheet** (M5-FR4) — the driver-app UI for logging when something goes wrong at a stop (damage, refusal, unsafe site, theft). The backend endpoint was already live and idempotent since HANDOFF-034; this closes the last M5 UI gap by giving it a driver-facing sheet.

### UI — `IncidentSheet` (`ui/src/core/components/IncidentSheet.vue`)
- A **driver-app bottom sheet** (mobile-first, NOT a portal): pick a kind chip (Damage / Load refused / Unsafe site / Theft / Other) + an optional note → files to `POST /protection/incident`, which opens an **F4 evidence log** (the record that protects the driver in a dispute). One decision per step (§202); calm confirmation, never alarming (§15.3).
- **Offline-safe (F12):** files via `queuedPost` (`fileIncident`, already in api.js) — a dead-zone incident saves to the write-queue and replays **exactly-once** on reconnect (stable `Idempotency-Key`; the backend `offline.ingest` dedupes). The sheet shows "Filed" when it lands, "Saved — syncs when online" when queued.
- **Host:** wired into `LoadSurface` (the active-load context), a "Report an incident" text CTA next to the M5-FR2 condition-capture CTA — both are active-stop evidence actions. `BottomSheet` `v-if`-unmounts on close, so the sheet resets each open. Six-locale `incident.*` keys added (**+13 → 237 keys/locale**).

### Verified this session (in compose)
- UI: **vitest 95 passed** (+3: files kind+note→confirm with an Idempotency-Key header; disabled until a kind is chosen; queued-offline path) · `vite build` clean · six-locale completeness at **237 keys**.
- Backend: **unchanged** this increment (UI-only). `ruff` clean · `lint-imports` **29/29 KEPT** · incident tests still green (`-k incident` → 2 passed) · **pytest 287** unchanged.
- **Live smoke:** `POST /protection/incident` with an `Idempotency-Key` → `applied:true` + `incident_id`/`evidence_log_ref`; **replay of the same key → `applied:false`** (exactly-once confirmed).

## 2. Decisions made (append to Decision Log)

147. **The incident sheet lives in the active-load context (LoadSurface), beside condition capture.** Both M5 evidence actions (condition photos FR2, incident FR4) attach to the current stop and belong together; the sheet is only offered when there's a live load (`v-if="live"`). An incident without an active load can be added later if needed, but the common case is "something happened at this stop."
148. **Incident kinds are a fixed driver-facing chip set (damage / refused / unsafe / theft / other), not free text.** The M5 domain accepts any string `kind`, but a bounded chip set keeps capture to two taps under stress and makes the evidence log categorizable. "Other" + the note field covers the long tail.
149. **The incident sheet reuses the existing `fileIncident`/`queuedPost` path — no new offline plumbing.** It's a crowd-grade write on the F12 queue with an idempotency key, so it inherits exactly-once replay for free. No backend change was needed; this was purely the missing UI.

## 3. Exact next task — continue the backlog

Remaining hardening (no owner input):
- **Richer admin console** — analytics funnels + config editing (F14 `funnel`/`set_config` ready). **Recommended next** (largest remaining value; makes the admin console operational rather than just flags/moderation).
- **Owner spot CRUD** — make the Property-Owner portal read-write (add/pause a listing/spot); currently read-only.
- Small backend polish: counterparty **names** in the fleet claims desk; `GET /load/active`; approved-review snippets on the public scorecard.

**Activation seams** (owner/BD input — not buildable now): F9 real model provider (M9/M11), Stripe/Connect (M6, deferred), fuel partner (M7), collections+legal (M3/M4), Mapbox (M1), IFTA data (M9), M10 params→F13, brand name. Flip these on in the admin console once gates are satisfied.

**Recommendation:** the **richer admin console** (analytics funnels + config editing) — the F14 backend primitives (`funnel`, `set_config`) are ready and it turns the operator portal from a flag/moderation panel into a real cockpit. Then owner spot CRUD to make the owner portal read-write.

## 4. Blockers / owner questions

Unchanged — all **activation inputs**: brand name · F9 provider (M9/M11) · Stripe/Connect (M6, deferred) · fuel partner (M7) · collections+legal (M3/M4) · Mapbox (M1) · IFTA data (M9) · M10 params→F13 · locale native review (F15, gate green at **237 keys**).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

**Incident sheet:** on the **Load** tab with an active load → "Report an incident" → pick a kind, add a note, file. Works offline (queues, syncs on reconnect). API `POST /protection/incident` (idempotent).
Suite: **pytest 287 · vitest 95 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**F1–F15 + M1–M12: complete; every surface live; integration e2e green; offline fully a mode; five surfaces (driver app + fleet/admin/public-scorecard/owner portals); M5 UI complete (condition FR2 + incident FR4).** Hardening to date: incident sheet (039), owner portal (038), public scorecard (037), evidence-sync (036), admin console (035), M5 condition capture (034), write-queue (033), read-cache (032), full-platform e2e (031), fleet portal (030), relay UI (029), detention loop (028), live Meter (027), M9/M11/M8 UIs (026). Remaining backlog §3, led by the richer admin console.

## 8. Commits this session (local only, never pushed)

`b61dc5d` Property-Owner portal → this session: incident capture sheet (+ this handoff). **103 commits** on `main`, never pushed.

*— End of session. Next: the richer admin console (analytics funnels + config editing, F14 primitives ready), then owner spot CRUD. Activation seams await owner/BD inputs (§4).*
