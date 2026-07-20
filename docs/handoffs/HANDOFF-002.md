# HANDOFF-002 — Session 1 cont. (F3 Location & Geofence Engine)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1 + F2 + **F3** built, tested, green in Docker.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then the latest handoff (this file), then `HANDOFF-001.md` for scaffold context.

---

## 1. What now exists and passes (delta since HANDOFF-001)

Everything from HANDOFF-001 still holds (scaffold, infra, tokens, i18n, CI, F1, F2). **New this session:**

### F3 — Location & Geofence Engine (schema `f03`) — PRD §7.3
Consumes **F2 via its public interface only** (import-linter enforced).
- **Location pings:** server-authoritative `received_at`; per-ping `client_skew_ms` recorded; **GPS-time divergence flagged** when `gps_time` diverges from client `occurred_at` beyond 30 s (time-integrity requirement). Adaptive-sampling `mode` field (`significant_change` / `high_accuracy`) as the client-policy seam.
- **Geofence arming/disarming** per (account, facility) with optional radius override.
- **Presence state machine** emitting `ENTER` / `EXIT` / `DWELL_TICK` (default 15-min tick) against F2 geometries — **radius or lot polygon** (polygon authoritative when present).
- **Per-facility tuning** (`facility_geofence`) with a `confirmed_arrivals` feedback counter incremented on each ENTER (the tuning feedback loop toward the ±3-min arrival target).
- **Trace builder** (`ST_MakeLine` over ordered pings → LINESTRING WKT) and a **retention purge** seam.
- 13 tests.

### F2 additions (geometry owner exposes containment through its interface)
- `contains_point()` (polygon-authoritative, else geography radius) and `set_lot_polygon()` added to F2's public surface + 2 tests. **F3 asks F2; it never queries `f02` tables** (PRD §10 — cross-module reads via interfaces only).

### import-linter (now 29 contracts)
- Foundation modeled as a **DAG**: components may import each other via `.public` only. `allow_indirect_imports = True` on all domain-privacy/public-only contracts, so reaching a component through its `public.py` (which re-exports its own domain) is allowed, while a **direct** reach-in into another component's `.domain` still breaks. **Empirically verified both ways** (29 kept green; injected direct `f03→f02.domain` → 28 kept / 1 broken).

### Verified this session (in compose)
- `alembic upgrade head` clean (now through `0003_f03_location`).
- `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 36 passed** (health 1, F1 12, F2 10, F3 13) · **vitest 10 passed**.

## 2. Decisions made (append to Decision Log)

10. **Foundation is a dependency DAG, not an independent set.** F3→F2 is real; later F8→F9/F15 will be too. Spine puts `foundation` as one layer (below modules, above core); per-component domain-privacy forbidden contracts enforce public-only access. This supersedes HANDOFF-001 decision #8's "start independent."
11. **`allow_indirect_imports = True`** on all public-only/domain-privacy contracts — the correct setting so `X → Y.public → Y.domain` is legal while `X → Y.domain` direct is not (reach-ins are always direct in code).
12. **Geometry stays in F2.** Containment tests (`contains_point`) live on F2's interface; consumers never re-implement geometry or read `f02` tables. Pattern to reuse for all F2 keystone access.
13. **F3 geofence defaults:** radius 150 m, DWELL_TICK 15 min, GPS divergence threshold 30 s — constants in `f03` service, to be migrated to F13 runtime config when F13 lands (rate/geofence tuning tables, PRD §7.13).
14. **Geofence arming lives in F3** as a self-contained arm/disarm API (seam). F5 Load/Stop and M3 will drive arming from an active `stop` without changing F3's model.

## 3. Exact next task

**Build F4 — Evidence Engine** next (PRD §7.4), to its component test suite, Docker, tests alongside.
- **Append-only, hash-chained event log per `stop`:** each record's hash includes the previous record's hash (tamper-evident); chain heads periodically anchored to an external timestamping service (anchor = a stubbed adapter seam now, like the other externals).
- **Artifact capture:** photos with preserved EXIF + GPS + server-received timestamp; guided-capture metadata supplied per use case by modules (F4 stores, modules define prompts).
- **Evidence Pack Composer:** templated PDF (cover summary, event timeline, map-trace snapshot, artifact appendix, hash-chain verification block) — one composer, many templates. The actual PDF renderer can start as a structured-document builder + a seam; the **hash-chain must be real and verifiable** (that's the DoD-critical, testable core).
- Depends on F1 (account), and will consume F3 geofence events + F5 stop context. **F5 does not exist yet** — so this session, build F4's hash-chain log + artifact model + composer data structure against a minimal `stop_id` reference (uuid, no FK yet, or a lightweight F4-owned stop-ref), leaving the F5 wiring as a seam. Add `f04` to `db_registry.py` + `conftest` SCHEMAS, a `0004` migration, and `tests/foundation/f04_evidence/`.
- Continue F5 → F15 in order after F4, then the §7.16 synthetic end-to-end (F1–F9 + F12) + six-locale shell render check to close the Foundation DoD. No module UI until then.

## 4. Blockers / owner questions

Unchanged from HANDOFF-001 §4 (all non-blocking for F4):
1. **Light-theme token values** — still needed before any real screen; I will not invent them. (Backend F4–F15 unaffected.)
2. **Locale wording** for pa/uz/so/ru/es pending F15 native review; CI completeness gate is live.
3. Session-0 open items (brand, collection partner, external test creds, fuel-price route, TPIMS survey).
- **New (F4, non-blocking, flag for later):** the external **timestamping/anchoring** service for hash-chain heads (PRD §7.4) and the PDF render toolchain choice will need owner input before M3 claim activation — I'll build F4 with clean adapter seams and log a proposal when I reach the anchoring integration.

## 5. Port / env changes

**None.** All ports unchanged from HANDOFF-001; LOCKED ports untouched. `infra/.env.example` unchanged.

## 6. How to run (all Docker)

```
make up · make migrate · make lint · make test · make ci · make down
```
Current suite: **pytest 36 · vitest 10 · 29 import contracts · ruff clean**, migrations through `0003`.

## 7. Commits this session (local only, never pushed)

`29f3045` scaffold → `08cc452` tokens/UI/CI → `c932b2f` F1+F2 → `70e7daa` HANDOFF-001 → `dff2648` import-linter DAG → `5d42791` F3 (+ this handoff commit).

*— End of Session 1 (F3) handoff. First action next: read governing docs, then this file, then plan F4.*
