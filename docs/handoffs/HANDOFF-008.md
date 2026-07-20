# HANDOFF-008 — Session 1 cont. (F9 AI Gateway)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–**F9** built, tested, green in Docker.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then the latest handoff (this file); earlier handoffs (001–007) for scaffold/F1–F8 context.

---

## 1. What now exists and passes (delta since HANDOFF-007)

Everything from HANDOFF-007 holds (scaffold, infra, tokens, i18n, CI, F1–F8). **New this session:**

### F9 — AI Gateway (schema `f09`) — PRD §7.9
Depends on F1. The single wrapper for every model call — **no module calls a model API directly** (import-linter enforces public-only access; the provider lives inside F9).
- **`ModelProvider` seam:** all completion / structured-parse / embedding / STT / TTS go through it. `FakeModelProvider` is **deterministic** (hash-derived vectors, no randomness) for tests; `StubModelProvider` fails loudly. The real adapter targets the **latest Claude models** — code notes to consult the `claude-api` skill when wiring (don't hardcode model ids from memory).
- **Versioned prompt registry** (latest active version per key) + **per-task evaluation fixtures**.
- **Per-module cost tracking** (`ai_call`: tokens + `cost_micros`) and **budget enforcement**: once a module's budget is consumed, further calls raise `BudgetExceeded`; budgets are **per-module isolated**. Cost rate is a placeholder constant → F13 config.
- **pgvector embeddings + cosine similarity search** (`embed_and_store` / `search_similar`); `EMBED_DIM=16` is a placeholder until the real model dimension is chosen (a migration).
- **Structured-output enforcement** (`parse_structured` validates required keys) — the seam **F5 `create_load_from_parsed_terms`** and **F6 extraction** will call.
- Added `pgvector` dependency; the test harness now enables the `vector` extension. Migration `0009` (shared-enum MetaData pattern, decision #27). 10 tests.

### Verified this session (in compose)
- `alembic upgrade head` clean through `0009`; **up→down→up round-trip verified**.
- `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 94 passed** (health 1, F1 12, F2 10, F3 13, F4 12, F5 9, F6 6, F7 10, F8 12, F9 10) · **vitest 10 passed**.

## 2. Decisions made (append to Decision Log)

33. **All model access is F9-only, provider-agnostic.** The gateway logic (registry, budgets, structured output, similarity) is fully tested against a deterministic fake; the real LLM/STT/TTS adapter is a single seam. When wiring it, use the latest Claude models via the `claude-api` skill.
34. **Cost in micro-dollars (`cost_micros`), integer.** Same no-floats-for-money discipline as F5/F7. Token→cost rates are placeholder constants moving to F13 config; per-module budgets are a hard ceiling (BudgetExceeded), mirroring the platform's budget semantics.
35. **Embedding dimension is a placeholder (16).** Real embedding model + dimension is chosen at F9 activation and is a migration + a pgvector index (ivfflat/hnsw) at that point. No ANN index yet (small data; exact cosine scan is fine).
36. **F9 is the parse/draft/embed backbone for later components.** F5 rate-con parsing, F6 OCR extraction, M2 semantic review search, M3/M11 drafting, and M11 voice all call F9 public — never a model SDK.

## 3. Exact next task

**Build F10 — Crowd Data Pipeline** next (PRD §7.10), to its component test suite, Docker, tests alongside.
- **Submission API** for statuses (parking fullness, weigh-station open/closed, fuel-price confirmations, facility-attribute corrections) with **source, location proof (submitter's F3 geofence presence), and timestamp**. The geofence-presence gate is real, testable logic (reuse F3 `public` — a submission without proven presence at the facility is rejected or flagged low-trust).
- **Trust scoring per contributor** + **time-decay functions per data type** (parking status decays in hours; amenities in months) + **aggregation jobs producing the "current best belief" per facility per signal** — these are the DoD-critical, testable cores (given N submissions with ages and trust, compute the aggregated belief).
- **Points issuance hooks into F7** — a trust-weighted contribution earns points via F7's points ledger (closed-loop). Wire through F7 `public`.
- Consumes F2 (facility), F3 (presence proof), F7 (points). Add `f10` to `db_registry.py` + `conftest` SCHEMAS, a `0010` migration, `tests/foundation/f10_crowd/`.
- Then F11 → F15 in order, then the **§7.16 synthetic end-to-end** (F1–F9 + F12) + six-locale shell render check to close the Foundation DoD. No module UI until then.

## 4. Blockers / owner questions

Unchanged and non-blocking for F10:
1. **Light-theme token values** — needed before any real screen; not invented.
2. **Locale wording** for pa/uz/so/ru/es pending F15 native review; CI completeness gate live.
3. Session-0 open items (brand, collection partner, external test creds, fuel-price route, TPIMS survey).
4. **Activation seams awaiting owner input:** external timestamping/anchoring + PDF toolchain (F4); Stripe/Connect + points rate (F7); Twilio/FCM/email providers (F8); **model provider keys + per-module cost budgets + embedding model/dimension (F9)**; MinIO bucket naming (F6).
- **New (F10):** points earn-table calibration (how many points per contribution type) — F13 config; building F10 with a configurable default + seam.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker)

```
make up · make migrate · make lint · make test · make ci · make down
docker compose -f infra/docker-compose.yml exec api python -m scripts.seed_admin   # dev admin
```
Current suite: **pytest 94 · vitest 10 · 29 import contracts · ruff clean**, migrations through `0009`.

## 7. Common Ground progress

**F1–F9 of F15 done.** Remaining: F10 Crowd · F11 Map/POI · F12 Offline Sync · F13 Flags/Config · F14 Admin/Analytics · F15 Localization — then §7.16 e2e (now that F9 exists, only F10–F12 stand between here and the e2e's dependencies) + six-locale shell check to close the Foundation DoD.

## 8. Commits this session (local only, never pushed)

… `d8cd2d7` F7 → `d8148fb` HANDOFF-006 → `bf5a159` ui boot fix → `8a02530` F8 → `173b6ac` HANDOFF-007 → `4e430d1` F9 (+ this handoff commit).

*— End of Session 1 (F9) handoff. First action next: read governing docs, then this file, then plan F10.*
