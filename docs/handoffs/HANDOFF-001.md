# HANDOFF-001 — Session 1 (Scaffold + F1/F2)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Scaffold complete; Common Ground F1 + F2 built, tested, green in Docker.
**Previous:** `HANDOFF.md` (Session 0, initial). Read that + PRD + design-prd first, then this file.

---

## 1. What now exists and passes

**Everything below was verified green inside Docker Compose (dev = CI parity). Nothing runs outside containers.**

### Repo scaffold (HANDOFF §5)
- `api/app/foundation/f01_identity … f15_localization` and `api/app/modules/m01_map … m12_fleet` — every one a bounded context with a `public.py` interface surface (27 total). Modules m03–m12 are still empty contexts.
- `api/app/core/` (config, db, main, worker), `db_registry.py` (Alembic/test model glue, deliberately outside the `app` package so it doesn't break the core/UI-split contract).
- `ui/` (Vite/Vitest + tokens + i18n + boot smoke), `infra/`, `scripts/`, `docs/`, tests mirroring packages.
- `CLAUDE.md` — governing docs, the two laws, working rules, LOCKED port table, "design-prd governs all UI."

### Infra & tooling
- `infra/docker-compose.yml` — postgres (PostGIS 16 + pgvector, built image), redis, api, worker, minio, mailpit, ui. **All ports from `.env`; nothing hardcoded.** `infra/.env.example` committed; `infra/.env` gitignored.
- `scripts/check_ports.sh` — compose preflight; **fails loud naming the conflicting PID** (both pass/fail paths verified on host). Wired ahead of `docker compose up` via `make up`.
- `Makefile` (env, preflight, up, down, migrate, test, lint, ci) — all via Docker.
- `.github/workflows/ci.yml` — compose-based: preflight → build → migrate → lint → pytest → vitest → teardown.
- **import-linter** (`api/importlinter.ini`, 14 contracts): core < foundation < modules spine; later-modules-above-earlier ordering; core imports nothing upward; modules reach foundation via `.public` only; per-module domain privacy (reach-in bans). **All 14 KEPT.** Run with `lint-imports --config importlinter.ini`.

### Design tokens & i18n
- `ui/src/core/tokens.scss` — seeded **verbatim from design-prd §6** (colors, type scale, spacing, radius, elevation, motion, touch, icons), mirrored to CSS custom properties, DRIVING-state type bump. **No values invented.**
- `ui/src/core/quasar.variables.scss` — Q-1 brand-var mapping FROM tokens (seam for when Quasar is added).
- Six launch-locale packs `en/es/pa/ru/uz/so` + `xx-XL` pseudo generator. Vitest stubs enforce **design-prd §12.5**: six-locale string completeness + xx-XL +40% inflation.

### F1 — Identity, Access & Organizations (schema `f01`)
- **Pluggable auth-method registry (owner-LOCKED):** one account → many `AuthMethod`s. Launch = **email/password only, argon2id, NO activation/verification step**. `oauth / otp_email / otp_sms` are registered as clean `NotImplemented` seams — they slot in later with **zero account/session-model rework**.
- Accounts, sessions (records `client_skew_ms`), role attachments (`driver/fleet_admin/property_owner/platform_admin`), organizations (`fleet/property_business`) + memberships, driver profile (truck/trailer dims, equipment, `authority_type`, home tz). `can_invoice()` gates claim-invoicing platform-wide (own_mc/leased = yes, company = no).
- 12 tests (register, no-activation login, dup-email reject, wrong/unknown auth, session roundtrip + expiry, registry seams, method linking, roles/orgs, invoicing gate).

### F2 — Canonical Facility Registry / keystone (schema `f02`)
- Canonical `facility` (PostGIS Point + optional lot Polygon, geohash blocking key, attributes/hours JSON, merge pointer) + `facility_source` provenance.
- Check-in creates a **candidate** that stays candidate until a **second independent signal** confirms it. Dedup = geohash prefix block + `pg_trgm` name similarity. Admin `merge` reassigns sources and **preserves the canonical id**. Radius/nearest via geography casts.
- 8 tests (create/read, radius in/out + type filter, candidate lifecycle, second-signal confirm, dedup match/ignore, merge preserves id + reassigns sources).

### Verified this session (in compose)
- `alembic upgrade head` clean (migrations `0001_f01_identity`, `0002_f02_facility`).
- `ruff check` clean · `lint-imports` 14/14 KEPT · **pytest 21 passed** · **vitest 10 passed**.
- Full stack boots: `api /health` → 200 `{"status":"ok"}`, `ui` → 200 on 9008, worker alive, extensions `postgis/vector/pg_trgm` present.

## 2. Decisions made (Decision Log entries)

1. **Git:** repo initialized on `main`; small local commits (3 this session). **Never pushed.** (Owner-confirmed.)
2. **Password hashing:** `argon2-cffi` (argon2id). (Owner-chosen.)
3. **Postgres image:** `postgis/postgis:16-3.4` + `postgresql-16-pgvector` via a thin derived image; `pg_trgm` also enabled (F2 fuzzy matching). (Owner-chosen.)
4. **Schema-per-module:** F1 → `f01`, F2 → `f02` (PRD §10). Enum types live in each component's schema.
5. **Model registry glue** (`db_registry.py`) lives **outside** `app` so importing every component's models for Alembic/tests does not violate the core/UI-split import contract.
6. **Test isolation:** pytest uses a dedicated `longhaul_test` database (created on demand), never the migrated dev DB; each test runs in a rolled-back savepoint.
7. **Migrations hand-written** (not autogenerated) so PostGIS geometry + GiST indexes are explicit and reliable.
8. **Foundation components start import-independent** of each other (siblings in the layered contract). When a real F-to-F dependency appears (e.g. F8 templates → F15), add a narrow layered sub-contract and log it — do not relax the spine.
9. **`importlinter.ini`** kept per HANDOFF §5 naming; invoked with `--config` (import-linter does not auto-discover that filename).

## 3. Exact next task

**Continue the Common Ground in order — build F3 (Location & Geofence Engine) next** (PRD §7.3), to its component test suite, in Docker, tests alongside.
- Server-side geofence evaluation emitting `ENTER / EXIT / DWELL_TICK` against F2 facility geometries (schema `f03`); PostGIS trace storage (timestamped linestrings) with retention config.
- **Server time authoritative; per-event client clock-skew recorded** (F1 session already carries `client_skew_ms` — reuse the pattern).
- Consume F2 via `f02_facility.public` only (import-linter will enforce). Add `f03` to `db_registry.py` + a `0003` migration + `tests/foundation/f03_location/`.
- Then proceed F4 → F15, then the §7.16 synthetic end-to-end (F1–F9 + F12) and the six-locale app-shell render check, which together close the Foundation DoD. No module UI until then.

## 4. Blockers / owner questions (non-blocking for F3)

1. **Light-theme token values.** design-prd §6.1/C-3 requires a light theme (bright-sun) but gives only qualitative derivation ("invert surface/text ramps; accents darken one step"), no hex. I did **not** invent values. **Need:** either approve me deriving the light ramp (I'll log exact hex as a §23 proposal for your sign-off) or supply the values. Required before any real screen ships; not needed for F3–F15 backend.
2. **Locale translations** for the seeded app-shell strings (nav tabs, offline banner, money-empty) are best-effort pending the F15 native-speaker review pipeline. The CI **completeness** gate is real; the **wording** for pa/uz/so/ru/es needs native review before launch.
3. Standing Session-0 open items remain: brand name, collection-partner shortlist (M3), Mapbox/Stripe/Twilio/FCM test creds (needed when integration work starts), fuel-price data route, TPIMS per-state survey (F2 ingestion spike, when F2 ingestion adapters are built).

## 5. Port / env changes

**None to the LOCKED ports.** All proposed ports were verified free 2026-07-20 and adopted as-is:

| Service | Port | Status |
|---|---|---|
| PostgreSQL (PostGIS + pgvector) | 5438 | LOCKED |
| API (FastAPI) | 8008 | LOCKED |
| Quasar dev | 9008 (fallback 3008) | PRIMARY |
| Redis | 6438 | in use, free |
| MinIO API / console | 9018 / 9019 | in use, free |
| Mailpit SMTP / UI | 1038 / 8038 | in use, free |

`infra/.env.example` is the committed source of truth; `infra/.env` is generated by `make env` and gitignored. No secrets in the repo.

## 6. How to run (all Docker)

```
make up        # preflight (fails loud on port conflict) → full stack
make migrate   # alembic upgrade head
make lint      # ruff + import-linter (14 contracts)
make test      # pytest (21) + vitest (10)
make ci        # preflight + lint + test
make down
```

*— End of Session 1 handoff. First action of Session 2: read HANDOFF.md + PRD + design-prd, then this file, then plan F3.*
