# HANDOFF-026 — Deferred driver-UI batch (M9 auditor · M11 ghostwriter · M8 sleep solver)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 21 July 2026 · **State:** Common Ground F1–F15 + all modules M1–M12 complete. Post-build **hardening / deferred-UI** phase. Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-025 (M1–M12 build complete), 011–024 (per-module).

---

## 1. What now exists and passes (delta since HANDOFF-025)

The M1–M12 build is complete; this session began the **post-build backlog** (owner directive: "defer Stripe and continue"). Focus: the **deferred driver-app UIs whose backends were already shipped** — three headless features now have screens. No owner input was needed for any of these.

- **M9 settlement-auditor UI** (M9-FR1 — the company-driver wedge). `AuditSurface` (`/money/audit`) off the Money tab: enter what the carrier PAID per accessorial kind → reconciled against the driver's own GPS-backed receivables → **missed pay flagged** as the hero figure (Mono/flare), "review with your carrier," never legal advice. `api.js: auditSettlement`.
- **M11 ghostwriter UI** (M11-FR3). `GhostwriterSheet` off the Money tab: pick a tone (Friendly / Neutral / Firm, segmented per §202), say what happened → the app drafts a professional message → **driver always approves before send** (F8 seam). Outbound English regardless of input language (F15). `api.js: draftMessage`.
- **M8 sleep-solver UI** (M8-FR3). `SleepSheet` on the Map's Tonight preset: enter remaining HOS → ranked stops within range (**guaranteed-bookable starred first**, then predicted availability, then nearest) + the guaranteed spot + cheapest fuel on the way. `api.js: fetchSleepPlan`.

All three are fixture-safe (live via api.js, graceful offline fallback), mobile-first at 360 dp, tokens-only.

### Verified this session (in compose)
- Backend untouched: **pytest 268** still green.
- UI: **vitest 76 passed** (was 73; +3, one per new surface) · `vite build` clean · six-locale completeness at **148 keys** (was 125; +23 across the three UIs).
- No migrations, no import-contract changes (UI-only session): still **29 contracts**, migrations at `0023`.

## 2. Decisions made (append to Decision Log)

102. **Post-build work is UI-composition over existing publics, not new backend.** Each deferred UI is a thin surface over an already-tested endpoint (`/money/settlements/audit`, `/voice/draft`, `/intel/sleep`); no service/schema/contract changes. The per-module discipline (fixture-safe, six-locale-together, one vitest per surface, §22 placement) carried into the hardening phase unchanged.
103. **The Money tab is the home for "get paid" tools.** The auditor and the ghostwriter both live off the Money tab as secondary actions below the owed list — they're the two ways a driver turns evidence into collected money (recover what was missed; write the message that unsticks it). Composed under §22 (design silent on their placement).
104. **The sleep solver lives in the Tonight preset**, appearing only there (the RESTING-state context, design-prd §11.3) — not a always-present chip. Keeps the Map's thumb-zone affordances (report, voice) uncluttered.

## 3. Exact next task — continue the backlog (owner-directable)

Remaining **deferred UIs** (backends shipped, buildable with no owner input):
- **M10 handoff-relay UI** — "leaving in X" broadcast + claim on the Map (free-lot pins); `/community/handoff` shipped.
- **Fleet-selection flow** to make `/fleet` live (create/pick a fleet → live report/claims); `/fleet/*` shipped.
- **M5 condition-capture / incident flows** — the camera-first capture sequences (M5 backend shipped, UI capture deferred since HANDOFF-017).
- **M9 IFTA / per-diem UI** — only once the data seams land (currently basis="needs_*").

**Cross-cutting hardening** (no owner input):
- **Active-load API** — the Load tab's Meter still runs on `SAMPLE_STOP`; wire a real active-load create/arm so The Meter (the signature element) is live.
- **Offline read-cache (F12)** across Map/Docs/Booking/Fuel/Voice.
- **Synthetic full-platform e2e** across M1–M12 (like the Common Ground e2e).
- **The other two web portals** (Property-Owner, Public Scorecard, §18).

**Activation seams** (need owner/BD input — NOT buildable now): F9 real model provider (M9+M11), Stripe (M6, deferred by owner), fuel payment-partner (M7), collection-partner (M3/M4), Mapbox (M1), IFTA data (M9), M10 economy params → F13, brand name.

**Recommendation for next session:** the highest-value no-owner-input item is the **active-load API** — it makes The Meter (the product's signature moment) real instead of fixture-backed, and unblocks the Load tab's Send-notice / Generate-claim CTAs end-to-end. After that, the **M10 handoff-relay UI** (the highest-novelty feature) and the **fleet-selection flow**.

## 4. Blockers / owner questions

Unchanged from HANDOFF-025 §4 — all **activation inputs**, none block the buildable backlog above:
1. Brand name. 2. F9 model provider + budgets (M9, M11). 3. Stripe (M6, **deferred by owner**). 4. Fuel payment-partner (M7). 5. Collection-partner + legal (M3/M4). 6. Mapbox (M1). 7. IFTA data (M9). 8. M10 economy params → F13. 9. Locale wording native review (F15) — completeness gate green at **148 keys**.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 → `/login` → Map (+voice, + **Where-do-I-sleep** in Tonight) · `/facility/:id` · `/book/:spotId` · `/fuel/:stationId` · `/load` · `/load/calc` · `/money` (DDD, + **Audit a settlement**, + **Draft a message**) · `/money/audit` · `/docs` · `/more` · `/fleet` (web-first). API http://localhost:8008 — 13 module/auth routers.
Suite: **pytest 268 · vitest 76 · 29 contracts · ruff clean**, migrations through `0023`.

## 7. Build progress

**Common Ground F1–F15 + Modules M1–M12: complete.** Post-build hardening in progress: 3 deferred UIs landed this session (M9 auditor, M11 ghostwriter, M8 sleep solver). Remaining backlog is §3 (deferred UIs + cross-cutting hardening + owner-gated activation).

## 8. Commits this session (local only, never pushed)

`b4b839b` HANDOFF-025 → `a6a1ed7` M9 auditor UI → `689f793` M11 ghostwriter UI → `74db0f8` M8 sleep-solver UI (+ this handoff). **76 commits** on `main`, never pushed.

*— End of session. Next: continue the backlog — suggested opener is the **active-load API** (makes The Meter live), then the M10 handoff-relay UI and the fleet-selection flow. Activation seams await owner/BD inputs (§4).*
