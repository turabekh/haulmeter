# HANDOFF-009 — Session 1 cont. (F10 Crowd Data Pipeline)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–**F10** built, tested, green in Docker.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then the latest handoff (this file); earlier handoffs (001–008) for scaffold/F1–F9 context.

---

## 1. What now exists and passes (delta since HANDOFF-008)

Everything from HANDOFF-008 holds (scaffold, infra, tokens, i18n, CI, F1–F9). **New this session:**

### F10 — Crowd Data Pipeline (schema `f10`) — PRD §7.10
Consumes F2 (facility), F3 (presence proof), F7 (points) — all via public interfaces.
- **Geofence-presence-gated submissions:** `submit()` proves presence via **F3 `is_present`**; **points are awarded (F7 closed-loop points ledger) only when presence is proven** (anti-gaming, PRD F10). Unproven reports are still recorded but weighted down and earn nothing.
- **Contributor trust scoring** (bounded 0.1–3.0): confirmed raises, rejected lowers.
- **Per-signal time decay** (half-lives: parking 1h, weigh 2h, fuel 24h, attributes 30d).
- **"Current best belief" aggregation** weighted by **trust × decay × presence**: categorical signals by weighted vote, fuel price by weighted average; **confidence + sample size + freshness** reported; belief persisted per facility+signal for serving (M1 pins). Stale-only data → no belief (honest "unknown").
- Points earn-table is a configurable default → F13 config.

### Enabling additions (both broadly useful, tested)
- **F3 `public.is_present(account, facility)`** — active geofence-presence check.
- **F7 `public.get_or_create_account(kind, name, currency, owner_ref)`** — idempotent per owner (per-contributor points balance + the shared points pool). Reusable by M6/M7/M10/M12.

### Verified this session (in compose)
- `alembic upgrade head` clean through `0010`; **up→down→up round-trip verified**.
- `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 105 passed** (health 1, F1 12, F2 10, F3 14, F4 12, F5 9, F6 6, F7 11, F8 12, F9 10, F10 10) · **vitest 10 passed**.

## 2. Decisions made (append to Decision Log)

37. **Points require proven presence.** Geofence-presence proof (F3) is the anti-gaming gate for paid contributions (PRD F10). Presence-unproven reports still inform belief but at reduced weight (×0.3) and earn no points.
38. **Belief is trust × decay × presence weighted; honesty over precision.** Categorical = weighted vote, numeric = weighted average; confidence is the winning-weight share (categorical) / a monotonic function of total weight (numeric). Stale-only → no belief (the UI shows "unknown", never fake confidence — design-prd §11.7).
39. **Half-lives and the earn-table are placeholder config** in F10 constants → migrate to F13 runtime config when F13 lands (rate/economy tables).
40. **Reusable ledger + presence helpers.** `F7.get_or_create_account` and `F3.is_present` were added as first-class public capabilities rather than F10-private queries, keeping cross-schema access through interfaces (PRD §10).

## 3. Exact next task

**Build F11 — Map & POI Serving** next (PRD §7.11), to its component test suite, Docker, tests alongside.
- **POI overlay API:** clustered facility pins (from F2) with **per-module badge layers** (live status from F10 beliefs, bookable, fuel price, dwell rating) composed **server-side** from the owning tables. Model the pin/badge composition + server-side clustering (grid or geohash-bucket) as real, testable logic.
- **Corridor query primitive:** "facilities of type X within Y minutes of my route/heading" — shared by M1, M7, M8. Since there is no in-house routing (out of scope), approximate the corridor as a heading-based/point-buffer PostGIS query (facilities within a distance band ahead) — real and testable with F2 geometries.
- **Tile provider (Mapbox) is an adapter seam** — styling/night-mode config is a client concern; server side is the overlay + corridor API. No tile secrets in repo.
- Consumes F2 (facilities/geometry), F10 (beliefs for badges). Add `f11` to `db_registry.py` + `conftest` SCHEMAS, a `0011` migration if it needs owned tables (may be mostly query-service over F2/F10 — a migration only if it introduces its own tables; otherwise skip the migration and note it), `tests/foundation/f11_map/`.
- Then **F12 Offline Sync** (client-infra outbox/idempotency — server side is the idempotent sync endpoint + occurred_at/received_at, which several components already model), **F13 Flags/Config**, **F14 Admin/Analytics**, **F15 Localization** — then the **§7.16 synthetic end-to-end** (F1–F9 + F12) + six-locale shell render check to close the Foundation DoD. No module UI until then.

## 4. Blockers / owner questions

Unchanged and non-blocking for F11:
1. **Light-theme token values** — needed before any real screen; not invented.
2. **Locale wording** for pa/uz/so/ru/es pending F15 native review; CI completeness gate live.
3. Session-0 open items (brand, collection partner, external test creds, fuel-price route, TPIMS survey).
4. **Activation seams awaiting owner input:** timestamping/PDF (F4); Stripe/Connect + points rate (F7); Twilio/FCM/email (F8); model keys + cost budgets + embedding dim (F9); MinIO bucket (F6); **Mapbox token + style (F11)**.
5. **Config that will consolidate into F13:** geofence tuning (F3), notification budget (F8), AI cost rates (F9), crowd half-lives + points earn-table (F10).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker)

```
make up · make migrate · make lint · make test · make ci · make down
docker compose -f infra/docker-compose.yml exec api python -m scripts.seed_admin   # dev admin
```
Current suite: **pytest 105 · vitest 10 · 29 import contracts · ruff clean**, migrations through `0010`.

## 7. Common Ground progress

**F1–F10 of F15 done** (⅔). Remaining: F11 Map/POI · F12 Offline Sync · F13 Flags/Config · F14 Admin/Analytics · F15 Localization — then §7.16 e2e + six-locale shell check to close the Foundation DoD.

## 8. Commits this session (local only, never pushed)

… `8a02530` F8 → `173b6ac` HANDOFF-007 → `4e430d1` F9 → `00250d8` HANDOFF-008 → `fbbbd56` F10 (+ this handoff commit).

*— End of Session 1 (F10) handoff. First action next: read governing docs, then this file, then plan F11.*
