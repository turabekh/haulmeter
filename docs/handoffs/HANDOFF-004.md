# HANDOFF-004 — Session 1 cont. (F5 Load & Stop Context)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–**F5** built, tested, green in Docker.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then the latest handoff (this file); earlier handoffs (001–003) for scaffold/F1–F4 context.

---

## 1. What now exists and passes (delta since HANDOFF-003)

Everything from HANDOFF-003 holds (scaffold, infra, tokens, i18n, CI, F1–F4). **New this session:**

### F5 — Load & Stop Context (schema `f05`) — PRD §7.5
Consumes F1, F2, **F3, F4** (all via public interfaces; foundation DAG). This is where the Common Ground starts wiring together.
- **Counterparty registry:** brokers/shippers/receivers/carriers with contacts, `mc_number`, observed **payment behavior** (running `avg_days_to_pay`), and `claim_count` — the data that feeds M8 pricing and M12 analytics.
- **Load:** `create_load()` manual quick-entry now; **`create_load_from_parsed_terms()` is the F9 rate-con-parser seam**. Carries rate, accessorial terms (detention rate / free time), reference number, `source` (manual/rate_con_parse/tms_push), and a status lifecycle (draft→active→completed/canceled).
- **Stop:** links a load to an **F2 facility** with an appointment window; per-stop term overrides; `effective_detention_terms()` resolves **stop-over-load** fallback. The Stop is the unit around which geofencing arms, evidence accrues, claims compute.
- **`arm_stop()` wires the foundation together:** opens an **F4 evidence log** (`stop_ref` set) and arms the **F3 geofence** for the load's account+facility. `disarm_stop()` reverses it. All through public interfaces — no reach-ins.
- **Integration test proves the wiring end-to-end:** after `arm_stop`, the F4 log exists with `stop_ref == stop.id`, and an F3 ping inside the facility emits `ENTER`.
- 9 tests.

### Verified this session (in compose)
- `alembic upgrade head` clean (now through `0005_f05_load`).
- `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 57 passed** (health 1, F1 12, F2 10, F3 13, F4 12, F5 9) · **vitest 10 passed**.

## 2. Decisions made (append to Decision Log)

19. **F5 is the wiring layer.** `arm_stop`/`disarm_stop` are the single place that arms F3 and opens an F4 log for a stop. Modules (M3) drive arming through F5, not by calling F3/F4 directly for stop lifecycle — keeps the "stop is the unit" invariant in one owner.
20. **What accrues where:** F5 owns stop/load/counterparty context and the arm/disarm action. **Turning F3 geofence events into F4 evidence records ("evidence accrues") is M3's job**, not F5's — F5 stops at establishing context + arming. Seam noted.
21. **Money stored in integer cents** (`rate_cents`, `detention_rate_cents_per_hour`) — no floats for money, anywhere. Reuse this for F7 Ledger.
22. **Stop→facility FK is `RESTRICT`** (a facility referenced by a stop can't be hard-deleted); facilities are merged, not deleted (F2 keystone invariant).

## 3. Exact next task

**Build F6 — Documents Service** next (PRD §7.6), to its component test suite, Docker, tests alongside.
- **Object storage (S3-compatible)** with **typed documents:** `rate_con`, `bol`, `pod`, `lumper_receipt`, `cdl`, `med_card`, `insurance`, `permit`, `settlement`, `other`. MinIO is already in the compose topology (ports 9018/9019) — use it via an adapter; keep the storage client behind a seam so tests don't require live MinIO (store key + metadata rows; a fake/local storage adapter for tests, real MinIO adapter for dev).
- **OCR/vision extraction via F9 on upload** — F9 doesn't exist yet, so store an `extraction` metadata structure and leave the extract call as a seam (accepts a parsed dict, like F5's rate-con seam).
- **Expiry engine:** documents with validity dates emit reminders at **30 / 14 / 3 days** through F8 — F8 doesn't exist yet, so compute due reminders and expose them; the send is an F8 seam. This is testable now (given a doc with an expiry date and a "now", which reminders are due).
- Depends on F1 (account). Add `f06` to `db_registry.py` + `conftest` SCHEMAS, a `0006` migration, `tests/foundation/f06_documents/`.
- Then F7 → F15 in order, then the §7.16 synthetic end-to-end (F1–F9 + F12) + six-locale shell render check to close the Foundation DoD. No module UI until then.

## 4. Blockers / owner questions

Unchanged and non-blocking for F6:
1. **Light-theme token values** — needed before any real screen; not invented.
2. **Locale wording** for pa/uz/so/ru/es pending F15 native review; CI completeness gate live.
3. Session-0 open items (brand, collection partner, external test creds, fuel-price route, TPIMS survey).
4. **External timestamping/anchoring (F4)** and **PDF render toolchain** — owner input before M3 activation; seams for now.
- **New (F6, non-blocking):** confirm MinIO bucket naming / lifecycle policy expectations when the real storage adapter lands (defaulting to a single `documents` bucket + per-account key prefixes; will log a proposal if you want otherwise).

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged. (F6 will use the already-allocated MinIO ports 9018/9019.)

## 6. How to run (all Docker)

```
make up · make migrate · make lint · make test · make ci · make down
```
Current suite: **pytest 57 · vitest 10 · 29 import contracts · ruff clean**, migrations through `0005`.

## 7. Common Ground progress

**F1–F5 of F15 done.** Remaining: F6 Documents · F7 Ledger · F8 Notifications · F9 AI Gateway · F10 Crowd · F11 Map/POI · F12 Offline Sync · F13 Flags/Config · F14 Admin/Analytics · F15 Localization — then the §7.16 synthetic e2e + six-locale shell check to close the Foundation DoD.

## 8. Commits this session (local only, never pushed)

… `5d42791` F3 → `55bb288` HANDOFF-002 → `c5d4be0` F4 → `1d40e71` HANDOFF-003 → `ed05daf` F5 (+ this handoff commit).

*— End of Session 1 (F5) handoff. First action next: read governing docs, then this file, then plan F6.*
