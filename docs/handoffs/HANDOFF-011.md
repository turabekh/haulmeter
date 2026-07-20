# HANDOFF-011 — Session 1 close (COMMON GROUND COMPLETE · Foundation DoD met)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** 🎯 **Common Ground F1–F15 built, tested, green in Docker. Foundation Definition of Done (PRD §7.16) MET.** Local stack running from a fresh install.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then this file; earlier handoffs (001–010) for per-component detail.

---

## 1. Milestone: the Common Ground is done

All fifteen foundation components are built to their component test suites, behind mechanically-enforced boundaries, green in Docker-composed CI. **The build law now moves to modules M1 → M12, in order** (PRD §6).

| # | Component | Schema | Notes |
|---|---|---|---|
| F1 | Identity, Access & Orgs | `f01` | pluggable auth-method registry; email/password only, no activation; roles/orgs/profile (+`locale`); `can_invoice` |
| F2 | Canonical Facility Registry | `f02` | PostGIS point/polygon, candidate→confirmed, geohash+trgm dedup, merge, `contains_point` |
| F3 | Location & Geofence Engine | `f03` | pings (server time + skew + GPS-divergence), ENTER/EXIT/DWELL, tuning feedback, trace, `is_present` |
| F4 | Evidence Engine | `f04` | append-only hash chain (tamper-evident, verified), artifacts bound in, anchoring seam, pack composer |
| F5 | Load & Stop Context | `f05` | loads (manual + rate-con-parse seam), counterparties, stops; `arm_stop` wires F3+F4 |
| F6 | Documents Service | `f06` | typed docs, ObjectStorage seam (InMemory + MinIO), OCR-via-F9 seam, 30/14/3 expiry engine |
| F7 | Ledger & Payments | `f07` | double-entry balance invariant, closed-loop points, receivable state machine, Stripe seam |
| F8 | Notifications & Outbound | `f08` | P0/P1/P2 + 2/day budget + quiet hours + DRIVING/RESTING safety; counterparty English; template registry |
| F9 | AI Gateway | `f09` | ModelProvider seam, prompt registry, per-module cost budgets, pgvector embeddings, structured-output |
| F10 | Crowd Data Pipeline | `f10` | presence-gated submissions, trust, time decay, belief aggregation, points into F7 |
| F11 | Map & POI Serving | *(schema-less)* | server-side pins/badges/freshness, clustering, corridor primitive; Mapbox client seam |
| F12 | Offline Sync & Outbox | `f12` | idempotent ingest (dedupe by account+key), occurred_at/received_at |
| F13 | Flags, Gates & Config | `f13` | kill-switch flags, activation gates, runtime config registry |
| F14 | Admin & Analytics | `f14` | event instrumentation, funnels, audit log, moderation queue, admin-view registry |
| F15 | Localization | `f15` | 6 launch locales, counterparty-English + imperial rules, message catalog, glossary |

### Foundation DoD checklist (PRD §7.16) — all met
- **(a)** All fifteen components pass their suites in Docker-composed CI. ✅
- **(b)** Synthetic end-to-end runs green (`tests/e2e/test_common_ground_e2e.py`): rate con → parsed (F9) → armed stop (F5→F3/F4) → hash-chain-valid evidence pack → offline sync (F12) → counterparty email (F8) + ledger receivable (F7), exercising F1–F9 + F12. ✅
- **(c)** Flag registry (F13), admin console + analytics (F14) operational. ✅
- **(d)** Module scaffolds M1–M12 exist as empty bounded contexts with enforced import boundaries (29 import-linter contracts KEPT). ✅
- **(e)** App-shell strings externalized; six launch-language packs + `xx-XL` pseudo-locale render (vitest §12.5 gate). ✅

## 2. Verified this session (in compose)

- **Fresh install from wiped volumes:** all **14 migrations** (`0001`→`0014`) apply cleanly to head; schemas f01–f10, f12–f15 created (F11 schema-less); all 7 services up; API `/health` 200; admin seeded.
- `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 136 passed** · **vitest 10 passed**.
- Per-migration **up→down→up** round-trips verified for every migration as built.

## 3. Decisions made (cumulative Decision Log — key entries)

See HANDOFF-001…010 for the full log. Load-bearing ones:
- **1–9** (H-001): git local-only, argon2id, PostGIS+pgvector image, schema-per-module, `db_registry` outside `app`, isolated test DB, hand-written then MetaData-pattern migrations, `importlinter.ini` via `--config`.
- **10–11** (H-002): foundation is a **DAG** — components import each other via `.public` only (`allow_indirect_imports=True`); direct `.domain` reach-ins still break.
- **27** (H-006): **shared-enum migration pattern** — local `MetaData` + `create_all(tables=[…])` + reference-stub FKs (`use_alter`) whenever an enum is shared across tables. **Reuse for any future such migration.**
- **33–36** (H-008): all model access is F9-only; cost in `cost_micros`; embedding dim is a placeholder (16) set at activation.
- **41–43** (H-010): F11 returns semantic data (colors are client-side from tokens); corridor ≈ heading cone.

## 4. Exact next task — START THE MODULES

**Build M1 — Road Intelligence Map** (PRD §8.1), the first module and the daily-open surface. **This is the first module UI work** — so the design constitution is now fully in force on every screen (design-prd LAW 0 mobile-first, §22.3 DoD).
- **Backend M1** (module `m01_map`, may reuse F11 serving): FRs M1-FR1..FR9 — truck-aware POI layers (F2 types, rig-filtered from F1 profile), live parking status (F10 beliefs), status prediction (heuristic until M8), weigh-station layer, fuel layer, corridor mode (F11), one-tap status contribution with geofence proof (F10, points via F7), deep-link handoff to external nav, full offline (F12). Behind an F13 flag `m01_map`.
- **Frontend M1** (first driver surfaces): the **Map tab** (design-prd §10.1) at 360×800 dp first. **BLOCKER — before any real screen ships you need the light-theme token values (§4 below).** The five-tab shell (design-prd §4) is built as part of the first module UP work.
- import-linter already permits `m01_map` → foundation `.public`. Add module tests under `api/tests/modules/m01_map/` and UI tests.
- **Plan-first still applies:** next session opens with a written plan for M1 (backend FRs + which screens, mobile-first) → owner approval → build.

## 5. Blockers / owner questions

**Now blocking (module UI starts next):**
1. ~~Light-theme token values.~~ **RESOLVED 2026-07-20 (owner-approved derivation).** Light theme derived + locked in `ui/src/core/tokens.scss` (`@mixin longhaul-light`, system + manual-override toggles), all §16 contrast ratios verified in both themes by `ui/test/contrast.test.js` (CI), logged in design-prd §23. **M1 driver screens are unblocked.**
2. **Locale wording** for pa/uz/so/ru/es (native-speaker review, F15 pipeline) — the CI completeness gate is live; the *translations themselves* need review before launch (not before building M1 in EN). (Non-blocking for M1 build in EN.)

**Activation seams awaiting owner input (not blocking build):** timestamping/PDF (F4); Stripe/Connect + points rate (F7); Twilio/FCM/email (F8); model provider keys + cost budgets + embedding dim (F9); MinIO bucket (F6); **Mapbox token + style (F11/M1)**; collection partner (M3); fuel data route (M7); brand name.

**Config to consolidate into F13** as modules land: geofence tuning (F3), notification budget (F8), AI cost rates (F9), crowd half-lives + points earn-table (F10), corridor half-angle (F11).

## 6. Port / env changes

**None all session.** LOCKED ports untouched; `infra/.env.example` unchanged. All proposed ports (redis 6438, minio 9018/9019, mailpit 1038/8038) in use and free.

## 7. How to run (all Docker) — stack is UP

| Surface | URL |
|---|---|
| API | http://localhost:8008 (`/health`, `/docs`) |
| Driver frontend (dev boot page) | http://localhost:9008 |
| MinIO console | http://localhost:9019 (`longhaul` / `longhaul_dev_only`) |
| Mailpit | http://localhost:8038 |

Admin (dev): `admin@longhaul.local` / `longhaul-admin-dev` (`platform_admin`).

```
make up · make migrate · make lint · make test · make ci · make down
docker compose -f infra/docker-compose.yml exec api python -m scripts.seed_admin
```
Suite: **pytest 136 · vitest 10 · 29 import contracts · ruff clean**, migrations through `0014`.

## 8. Session 1 commits (local only, NEVER pushed) — on `main`

Scaffold → tokens/CI → F1+F2 → (handoffs) → F3 → F4 → F5 → F6 → F7 (+admin seed) → ui boot fix → F8 → F9 → F10 (+F3/F7 helpers) → F11 → F12 → F13 → F14 → F15 (+F1 locale) → §7.16 e2e. ~30 commits, each with tests green. Latest: `e6edc52`.

*— End of Session 1. The Common Ground is complete. Next session: read the governing docs + this handoff, resolve the light-theme tokens, then present the M1 plan for approval before building the first module and its mobile-first screens.*
