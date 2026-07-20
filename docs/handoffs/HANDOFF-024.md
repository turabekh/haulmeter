# HANDOFF-024 — M11 Voice Copilot & AI Communications (backend + API + UI)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–F15 complete (F1 has driver UI). **M1–M11 built** (backend + API + UI). Stack running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; HANDOFF-011 (Foundation DoD), 012–023 (M1–M10 + login UI).

---

## 1. What now exists and passes (delta since HANDOFF-023)

**New: M11 — Voice Copilot & AI Communications** (the AI-native UX layer) + the **map voice wake button + ask/answer sheet**. A **schema-less serving layer** (M8 precedent): no tables — it routes intents to the modules below and drafts through F9.

### M11 backend — `api/app/modules/m11_voice` (no schema, PRD §8.11)
Composes **F8 + F9 + M4 + M7 + M8 + M10**. 29 contracts KEPT. **No migration.**
- **Voice intents** (M11-FR1): `classify_intent` is a deterministic keyword router over **15 intents** (money owed, points, fuel savings, detention status/risk/start, parking/fuel/facility, dwell, best hour, sleep solver, book, next action, help) that dispatch to the module publics; `route`/`handle_utterance` add STT/TTS via the **F9 seam**. An eval fixture proves ≥15 intents at **100% routing accuracy** (DoD ≥95%).
- **Motion policy** (M11-FR2): `interaction_mode(driving)`; committing intents (`start_detention`, `book_parking`) **defer their confirmation** to on-screen-when-stopped while DRIVING, returning `needs_confirmation` + audio-first.
- **Comms ghostwriter** (M11-FR3): `draft_counterparty_message` via F9 drafting with **tone presets** (relationship → firm); outbound is **ALWAYS English** (F15), sent through F8 (`approve_and_send`).
- **Claim assistant** (M11-FR4): `claim_assistant` — what's owed + the **next action per receivable** over M3/M4 state.
- **Multilingual** (M11-FR6): utterances transcribe in any launch locale; the ghostwriter accepts any language and always outputs English.
- F13 flag `m11_voice`.

### M11 HTTP API + UI
- API: `POST /voice/ask` (text/intent routing + motion policy), `GET /voice/claims`, `POST /voice/draft` (English ghostwriter). F9 provider is the `FakeModelProvider` dev seam.
- **Map**: the copilot **wake affordance** (M11-FR5) — a mic chip in both IDLE and Corridor modes (bigger/centered while driving, no hotword) → **VoiceSheet**: ask in words, get the intent-routed spoken answer; while DRIVING the answer renders oversized (voice-first).

### Verified this session (in compose)
- No migration (schema-less).
- Backend: `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 258 passed** (was 246; +8 M11 module +4 M11 API).
- UI: **vitest 72 passed** (+3: VoiceSheet ask/answer, driving-hero, Map mic wake) · `vite build` clean · six-locale completeness at **117 keys**.
- **Live smoke:** authenticated `POST /voice/ask {"text":"what am I owed"}` returns 200 and routes to `money_owed`.

## 2. Decisions made (append to Decision Log)

93. **Intent routing is a deterministic keyword router, F9 classify is the upgrade path.** The DoD's ≥95% accuracy is met by explicit ordered rules over the app's own vocabulary (not open-domain), which is transparent, testable, and free; the F9 model is the seam for fuzzier phrasing later. Both target the same eval-fixture set (F9 registry).
94. **The motion policy never commits an action in motion.** `route(..., driving=True)` on a committing intent returns `needs_confirmation` + a spoken "confirm on screen when stopped" and does NOT execute — the on-screen surface finalizes it when parked (design-prd §5/§14, F8 safety).
95. **The ghostwriter always outputs English regardless of input language** (M11-FR6/F15): the drafting prompt enforces English, and F8's counterparty path is English-only. The driver can dictate in any launch locale; the counterparty always receives English.
96. **M11 is schema-less** (M8 precedent). Voice sessions and drafts don't need persistence for the DoD — F9 records calls, F8 records sent messages, F9's registry versions the prompts. No tables, no migration.
97. **Voice UI is the highest-value M11 slice; ghostwriter/claim-assistant UI deferred** (backend + `/voice/draft` + `/voice/claims` shipped). The map wake button + ask/answer loop is the headline UX; the approve-and-send ghostwriter screen and the conversational claim view are next-session follow-ups.

## 3. Exact next task

**Continue module order → M12 (the final module).** Plan **M12 — Fleet & B2B Layer** (PRD §8.12 — verify title/FRs against the PRD before building), plan-first:
- Foundation deps F1, F5, F7, F14; consumes M2/M3/M4/M6/M7/M9 interfaces. Likely: fleet accounts/seats (F1 roles/orgs), fleet reporting (dwell exposure, recovered $, fuel savings, IFTA rollups per driver + fleet-wide), and the B2B/data-product surfaces (web portals, design-prd §18).
- Backend `m12_fleet` (imports foundation + earlier module publics). F13 flag. Then UI — note the fleet workspace is a **web-first portal** (design-prd §18), not the driver phone app — the first non-mobile-first surface.

**Fold-in follow-ups (owner priority):** **Mapbox token**, active-load API, **offline read-cache (F12)**, **M11 ghostwriter approve UI**, **M10 handoff-relay UI**, **M9 settlement-auditor UI**, **M8 sleep-solver UI**, M5 capture flows, M6/M7 owner portals, **brand name**, **real F9 model provider + budgets** (now used by M9 + M11).

## 4. Blockers / owner questions

1. **Brand name** — "LONGHAUL" placeholder on login (§4 seam).
2. **F9 real model provider + per-module budgets** — M9 (settlement parse) and M11 (voice + ghostwriter) both run on the `FakeModelProvider` dev seam; a real STT/TTS/LLM provider + budgets are needed before those activate. The intent-routing DoD (95% in each language) needs the six-language eval fixtures populated in the F9 registry.
3. **M10 economy params → F13 config** (before activation). **Fuel payment-partner / Stripe / Mapbox / collection-partner / IFTA data** (prior modules' activation gates, unchanged).
4. **Locale wording** — new M11 strings (4 keys × 6) native review pending (F15); completeness gate green at **117 keys**.
5. Standing seams: timestamping/PDF (F4), Twilio/FCM/email (F8), MinIO bucket (F6).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker) — stack is UP

Driver app http://localhost:9008 → `/login` → Map (+ **voice mic**) · `/facility/:id` (dwell · risk · Q&A) · `/book/:spotId` · `/fuel/:stationId` · `/load` · `/load/calc` · `/money` (DDD) · `/docs` · `/more` (points). API http://localhost:8008 (`/auth/*`, `/map/*`, `/facility/*`, `/detention/*`, `/accessorial/*`, `/protection/*`, `/parking/*`, `/fuel/*`, `/intel/*`, `/money/*`, `/community/*`, **`/voice/*`**). Admin: `admin@longhaul.local` / `longhaul-admin-dev`.
Suite: **pytest 258 · vitest 72 · 29 contracts · ruff clean**, migrations through `0022`.

## 7. Build progress

**Common Ground F1–F15: complete.** Modules: **M1–M11 done.** Next: **M12** (the last module — fleet/B2B, first web-first portal). The driver can now ask the app anything hands-free and have it answer over its own data; the ghostwriter is ready to draft the firm-but-professional messages that unstick claims.

## 8. Commits this session (local only, never pushed)

`2d13745` HANDOFF-023 → `4cfceb5` M11 backend+API → `55f505e` M11 UI (+ this handoff). **69 commits** on `main`.

*— End of session. Next: plan M12 (Fleet & B2B — fleet reporting rollups + the web-first Fleet Workspace, design-prd §18), plan-first. This is the final module; after it, the M1–M12 sequence is complete.*
