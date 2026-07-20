# HANDOFF-007 — Session 1 cont. (F8 Notifications & Outbound Comms)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–**F8** built, tested, green in Docker.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then the latest handoff (this file); earlier handoffs (001–006) for scaffold/F1–F7 context.

---

## 1. What now exists and passes (delta since HANDOFF-006)

Everything from HANDOFF-006 holds (scaffold, infra, tokens, i18n, CI, F1–F7). **New this session:**

### F8 — Notifications & Outbound Communications (schema `f08`) — PRD §7.8 + design-prd §13
Depends on F1. The interruption logic is real and fully tested (not a seam).
- **Inbound-to-driver tiering (design-prd §13.1–13.4):**
  - **P2** = digest-only, never pushed (in-app).
  - **P0** = always sent — bypasses quiet hours, budget, and RESTING.
  - **P1** respects, in order: **RESTING** (mute to P0), **quiet hours** (default 22:00–06:00 local, tz-aware via `tzdata`), and the **2-per-day unprompted interruption budget** (rolling 24h). Each suppression records its reason (`budget`/`quiet_hours`/`resting`).
  - **DRIVING safety:** P0/P1 delivered as one-line **audio** (`channel=audio`), never interactive (§13.4). **Every notification requires a `deep_link`** (§13.5, enforced).
  - Channels (push/SMS/email) behind a **`NotificationGateway` seam**: `RecordingNotificationGateway` for tests, `StubNotificationGateway` (FCM/Twilio/email) fails loudly.
- **Outbound-to-counterparty:** threads with per-message **sent/opened tracking** + inbound reply routing.
- **Versioned template registry:** latest active version per `key`+`locale`; **counterparty templates are always English** (F15) — enforced (non-en rejected); `{placeholder}` rendering (full ICU deferred to F15).
- Added `tzdata` dependency. Migration `0008` (shared-enum MetaData pattern, decision #27). 12 tests.

### Verified this session (in compose)
- `alembic upgrade head` clean through `0008`; **up→down→up round-trip verified**.
- `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 84 passed** (health 1, F1 12, F2 10, F3 13, F4 12, F5 9, F6 6, F7 10, F8 12) · **vitest 10 passed**.

## 2. Decisions made (append to Decision Log)

29. **Interruption budget is real, provider-agnostic logic.** The tier/quiet-hours/budget/state decision lives in F8 and is fully tested with a recording gateway — no live FCM/Twilio needed. Budget = 2 unprompted P1/day (design-prd §13.1); constants move to F13 config when F13 lands.
30. **Driver state is passed in, not owned.** F8 receives `DriverState` (derived by F3/UI, design-prd §5) as a parameter to `dispatch()`; it does not compute state. Same seam pattern as F5→F3 arming.
31. **F8 is the send-home for other components' notifications.** F6 expiry reminders and (future) M3 dunning call `dispatch()` / `send_counterparty_message()`. Those callers own *when*; F8 owns *whether/how* (budget, quiet hours, safety, tracking).
32. **Counterparty English is enforced at registration**, not just convention — `register_template` rejects non-en counterparty templates (F15 rule, PRD §7.15).

## 3. Exact next task

**Build F9 — AI Gateway** next (PRD §7.9), to its component test suite, Docker, tests alongside.
- **Single service wrapping ALL model calls** — no module ever calls a model API directly. Capabilities: document parsing (rate cons, settlements, receipts), drafting (counterparty comms), STT/TTS (for M11), embeddings (pgvector) for facility/review search, structured-output enforcement.
- **Provider is an adapter seam** (all LLM/STT/TTS behind it, stubbed locally per the fixed stack) — build a `ModelProvider` protocol with a deterministic **fake/echo provider** for tests and a real-provider seam. **All LONGHAUL LLM work targets the latest Claude models** — when wiring the real adapter, load the `claude-api` skill first (it is the source of truth for model ids/params); do not hardcode model strings from memory.
- **Prompt/version registry with evaluation fixtures per task** + **per-call cost tracking and budgets per module** (PRD §7.9) — model these as real, testable structures (register prompt version, record a call with token/cost, enforce a per-module budget).
- **Embeddings:** pgvector is already installed (F0 infra). Store embeddings on a vector column; a similarity-search helper (used by M2 semantic review search later). Keep the embedding vectors coming from the provider seam (fake provider returns deterministic vectors for tests).
- **Structured-output enforcement:** a helper that validates a provider response against an expected schema (used by rate-con/settlement parsing). This is the seam F5 `create_load_from_parsed_terms` and F6 extraction will call.
- Depends on F1 (budgets per module/account). Add `f09` to `db_registry.py` + `conftest` SCHEMAS, a `0009` migration, `tests/foundation/f09_ai_gateway/`. Note pgvector column type via `pgvector.sqlalchemy.Vector` — add the `pgvector` python package to deps (rebuild api).
- After F9: F10 → F15 in order, then the **§7.16 synthetic end-to-end** (F1–F9 + F12 in one flow — now within reach once F9/F12 exist) + six-locale shell render check to close the Foundation DoD. No module UI until then.

## 4. Blockers / owner questions

Unchanged and non-blocking for F9:
1. **Light-theme token values** — needed before any real screen; not invented.
2. **Locale wording** for pa/uz/so/ru/es pending F15 native review; CI completeness gate live.
3. Session-0 open items (brand, collection partner, external test creds, fuel-price route, TPIMS survey).
4. **External timestamping/anchoring (F4)**, **PDF render toolchain**, **Stripe/Connect + points rate (F7)**, **Twilio/FCM/email providers (F8)** — owner input before activation; seams for now.
5. **MinIO** bucket naming for the real F6 adapter.
- **New (F9, before activation):** confirm the model provider account/keys for the real F9 adapter (LLM/STT/TTS) and per-module cost budget defaults — building F9 with a fake provider + budget structures now.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker)

```
make up · make migrate · make lint · make test · make ci · make down
docker compose -f infra/docker-compose.yml exec api python -m scripts.seed_admin   # dev admin
```
Current suite: **pytest 84 · vitest 10 · 29 import contracts · ruff clean**, migrations through `0008`.

## 7. Common Ground progress

**F1–F8 of F15 done.** Remaining: F9 AI Gateway · F10 Crowd · F11 Map/POI · F12 Offline Sync · F13 Flags/Config · F14 Admin/Analytics · F15 Localization — then §7.16 e2e + six-locale shell check to close the Foundation DoD.

## 8. Commits this session (local only, never pushed)

… `292ec37` F6 → `3e35ee3` HANDOFF-005 → `d8cd2d7` F7 → `d8148fb` HANDOFF-006 → `bf5a159` ui boot fix → `8a02530` F8 (+ this handoff commit).

*— End of Session 1 (F8) handoff. First action next: read governing docs, then this file, then plan F9.*
