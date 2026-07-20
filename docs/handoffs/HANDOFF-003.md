# HANDOFF-003 — Session 1 cont. (F4 Evidence Engine)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1 + F2 + F3 + **F4** built, tested, green in Docker.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then the latest handoff (this file); earlier handoffs (001, 002) for scaffold/F1–F3 context.

---

## 1. What now exists and passes (delta since HANDOFF-002)

Everything from HANDOFF-002 holds (scaffold, infra, tokens, i18n, CI, F1–F3). **New this session:**

### F4 — Evidence Engine (schema `f04`) — PRD §7.4
Depends on F1; consumes nothing else yet (F3 events / F5 stops wire in later). Turns raw events into artifacts that survive a dispute.
- **Append-only, hash-chained record log per `evidence_log`.** `record_hash = sha256(prev_hash + seq + type + canonical(payload) + UTC(occurred_at))`. Serialization is canonical (sorted keys, UTC-normalized timestamps) so verification is **deterministic across DB round-trips**.
- **`verify_chain()`** recomputes every link and reports the **first broken seq + reason** — catches `tampered` payloads, `seq_gap`, and `broken_link`. This is the DoD-critical, fully-tested core.
- **Artifact capture:** EXIF + GPS + server timestamp + `content_hash`; attaching an artifact **appends a chain record binding its content_hash**, so photos are evidence-grade (mutating the bytes breaks the chain).
- **Chain anchoring:** head seq/hash recorded with an `external_ref` (external timestamping-service **adapter seam** — real TSA integration deferred to M3 activation).
- **Evidence Pack Composer:** `compose_pack()` returns the structured pack — cover/label, ordered event timeline, artifact appendix, and a **hash-verification block** (chain_valid, head, anchored). One composer, many templates (`detention_claim / tonu / on_time_proof / cargo_condition`). Actual **PDF byte rendering is a seam** (`render_pack_pdf` raises `RenderNotEnabled`; token-styled per design-prd §17, lands with the F4 template set).
- 12 tests (chaining, untampered-valid, empty-valid, tampered-payload, seq-gap, artifact→content-hash binding, artifact-requires-content, compose structure, compose-reflects-tamper, anchor, anchor-empty-raises, PDF seam).

### Verified this session (in compose)
- `alembic upgrade head` clean (now through `0004_f04_evidence`).
- `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 48 passed** (health 1, F1 12, F2 10, F3 13, F4 12) · **vitest 10 passed**.

## 2. Decisions made (append to Decision Log)

15. **Hash-chain determinism.** Record hashes are computed over canonical JSON with UTC-normalized ISO timestamps, so `verify_chain` is stable regardless of Postgres tz rendering or dict key order. Any future hash-material change is a breaking change to existing chains — version it if it ever changes.
16. **Artifacts are bound into the chain.** `attach_artifact` appends a chain record carrying the artifact's `content_hash`; the artifact row references that record. Evidence integrity therefore covers artifacts, not just events.
17. **F4 owns a lightweight `evidence_log`** with a nullable `stop_ref` (uuid) seam. F5's `stop` will populate `stop_ref`; no F4 rework needed when F5 lands.
18. **Externals are seams, consistently:** external timestamping/anchoring and the PDF renderer are adapter seams (like Stripe/Twilio/Mapbox/AI Gateway). The verifiable *structure* is built; the outbound integration is logged for owner input at M3 activation.

## 3. Exact next task

**Build F5 — Load & Stop Context** next (PRD §7.5), to its component test suite, Docker, tests alongside.
- **`Load` object:** broker/carrier counterparty, rate, per-stop appointment times, accessorial terms (detention rate, free time, TONU terms), reference numbers. Created three ways — rate-con upload parsed by F9 (primary), manual quick-entry, or fleet/TMS push (M12). F9 doesn't exist yet, so build **manual quick-entry** now and leave the **rate-con-parse** path as a seam (accepts a parsed-terms dict).
- **`Stop` object:** links a `load` to a `facility` (F2) with an appointment window — the unit around which geofencing arms (F3), evidence accrues (F4), and claims compute (M3). **This is where F3 arming and F4 `stop_ref` finally connect:** creating/activating a stop should be able to arm its F3 geofence and open an F4 evidence log — wire those via F3/F4 public interfaces (both already expose the needed calls: `arm_geofence`, `create_log`).
- **Counterparty registry:** brokers/shippers with contact channels + observed payment behavior + claim history (feeds M8/M12). Build the entity + basic CRUD now.
- Consumes F1, F2 (and F3/F4 publics for the stop wiring). Add `f05` to `db_registry.py` + `conftest` SCHEMAS, a `0005` migration, `tests/foundation/f05_load/`.
- Then F6 → F15 in order, then the §7.16 synthetic end-to-end (F1–F9 + F12) + six-locale shell render check to close the Foundation DoD. No module UI until then.

## 4. Blockers / owner questions

Unchanged and non-blocking for F5:
1. **Light-theme token values** — needed before any real screen; not invented. (Backend F5–F15 unaffected.)
2. **Locale wording** for pa/uz/so/ru/es pending F15 native review; CI completeness gate live.
3. Session-0 open items (brand, collection partner, external test creds, fuel-price route, TPIMS survey).
4. **External timestamping/anchoring service** (F4) and **PDF render toolchain** — owner input needed before M3 claim activation; built as seams for now.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker)

```
make up · make migrate · make lint · make test · make ci · make down
```
Current suite: **pytest 48 · vitest 10 · 29 import contracts · ruff clean**, migrations through `0004`.

## 7. Commits this session (local only, never pushed)

… `dff2648` import-linter DAG → `5d42791` F3 → `55bb288` HANDOFF-002 → `c5d4be0` F4 (+ this handoff commit).

*— End of Session 1 (F4) handoff. First action next: read governing docs, then this file, then plan F5.*
