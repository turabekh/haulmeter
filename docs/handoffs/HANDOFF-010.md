# HANDOFF-010 — Session 1 cont. (F11 Map & POI Serving)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–**F11** built, tested, green in Docker.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then the latest handoff (this file); earlier handoffs (001–009) for scaffold/F1–F10 context.

---

## 1. What now exists and passes (delta since HANDOFF-009)

Everything from HANDOFF-009 holds (scaffold, infra, tokens, i18n, CI, F1–F10). **New this session:**

### F11 — Map & POI Serving (schema-less) — PRD §7.11
A server-side **serving/query layer** composing F2 geometry + F10 beliefs. **Owns no tables** (no migration). Consumes F2, F10 via public.
- **POI overlay:** `overlay_pins()` returns pins carrying **shape** (from facility type — design-prd §11.2 taxonomy), **parking status + freshness** (from F10 belief), and **badges** (fuel price now; dwell/bookable are **module-badge-provider hooks** for M2/M6). Returns **semantic data only** — the client renders colors from design tokens; **no visual decision is made server-side**.
- **Server-side clustering:** `cluster_pins()` grid-buckets pins → count + dominant status (design-prd §11.5).
- **Corridor query primitive:** `corridor()` returns facilities within a **heading cone ahead** (bearing + half-angle), **distance-sorted**; behind/off-heading excluded. Shared by M1/M7/M8. No in-house routing (out of scope) — a heading-cone approximation over F2 geometry.
- Mapbox tiles + night/day styling are a **client seam**; no tile secret server-side.
- 7 tests.

### Verified this session (in compose)
- No new migration (F11 owns no tables); migrations still through `0010`.
- `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 112 passed** (health 1, F1 12, F2 10, F3 14, F4 12, F5 9, F6 6, F7 11, F8 12, F9 10, F10 10, F11 7) · **vitest 10 passed**.

## 2. Decisions made (append to Decision Log)

41. **F11 returns semantic data, not visuals.** Pins/clusters carry status/shape/badges/freshness; **all color and rendering is client-side from design tokens** (design-prd §6/§11). This keeps design decisions in the constitution's domain and off the server. Pin-shape mapping is transcribed from §11.2; unspecified POI types fall back to the generic `circle` (composing an existing shape, not inventing one).
42. **Badge layers are a provider-hook seam.** `DEFAULT_BADGE_PROVIDERS` currently = fuel price (from F10). Dwell-risk (M2/M3) and bookable-$ (M6) register as providers when those modules land — no F11 rework.
43. **Corridor ≈ heading cone.** With no proprietary routing (PRD §16 out of scope), the corridor primitive is a bearing+half-angle band over F2 geometry, distance-sorted. Good enough for "what's ahead"; a route-polyline buffer can replace the cone later if a routing provider is integrated, behind the same interface.

## 3. Exact next task

**Build F12 — Offline Sync & Outbox** next (PRD §7.12), to its component test suite, Docker, tests alongside. This is the last piece the **§7.16 synthetic end-to-end** waits on.
- **Server side of the offline outbox:** an **idempotent sync endpoint/service** — client writes every capture locally first (SQLite/IndexedDB, client infra) and later syncs queued items with **idempotency keys**; the server must **dedupe by idempotency key** (same key twice = one effect) and record both **`occurred_at`** (client, skew-corrected) and **`received_at`** (server). Several components already carry this shape (F3 pings, F4 records) — F12 provides the generic, tested **idempotent-ingest primitive** other components/modules route through.
- Model an `sync_envelope`/outbox-receipt table keyed by `(account_id, idempotency_key)` unique; a `sync(db, account_id, idempotency_key, kind, payload, occurred_at)` that returns the same receipt on retry (no double-apply) and a status (applied/duplicate).
- Read-side offline cache (last map region, active load, document wallet) is a **client concern** — server side is the sync/dedup contract; note the client cache as out-of-scope-for-server.
- Depends on F1. Add `f12` to `db_registry.py` + `conftest` SCHEMAS, a `0011` migration, `tests/foundation/f12_offline/`.
- **After F12:** F13 Flags/Config, F14 Admin/Analytics, F15 Localization — then the **§7.16 synthetic end-to-end** (F1–F9 + F12: rate-con → armed stop → evidence pack → sync → counterparty email + ledger receivable) and the **six-locale shell render check** to close the Foundation DoD (PRD §7.16). No module UI until then.

## 4. Blockers / owner questions

Unchanged and non-blocking for F12:
1. **Light-theme token values** — needed before any real screen; not invented.
2. **Locale wording** for pa/uz/so/ru/es pending F15 native review; CI completeness gate live.
3. Session-0 open items (brand, collection partner, external test creds, fuel-price route, TPIMS survey).
4. **Activation seams awaiting owner input:** timestamping/PDF (F4); Stripe/Connect + points rate (F7); Twilio/FCM/email (F8); model keys + cost budgets + embedding dim (F9); MinIO bucket (F6); Mapbox token + style (F11).
5. **Config consolidating into F13:** geofence tuning (F3), notification budget (F8), AI cost rates (F9), crowd half-lives + points earn-table (F10), corridor half-angle (F11).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker)

```
make up · make migrate · make lint · make test · make ci · make down
docker compose -f infra/docker-compose.yml exec api python -m scripts.seed_admin   # dev admin
```
Current suite: **pytest 112 · vitest 10 · 29 import contracts · ruff clean**, migrations through `0010`.

## 7. Common Ground progress

**F1–F11 of F15 done.** Remaining: F12 Offline Sync · F13 Flags/Config · F14 Admin/Analytics · F15 Localization — then §7.16 e2e + six-locale shell check to close the Foundation DoD.

## 8. Commits this session (local only, never pushed)

… `4e430d1` F9 → `00250d8` HANDOFF-008 → `fbbbd56` F10 → `603b670` HANDOFF-009 → `e1a9f82` F11 (+ this handoff commit).

*— End of Session 1 (F11) handoff. First action next: read governing docs, then this file, then plan F12.*
