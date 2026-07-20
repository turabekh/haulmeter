# HANDOFF-006 — Session 1 cont. (F7 Ledger & Payments)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–**F7** built, tested, green in Docker. Local stack currently running.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then the latest handoff (this file); earlier handoffs (001–005) for scaffold/F1–F6 context.

---

## 1. What now exists and passes (delta since HANDOFF-005)

Everything from HANDOFF-005 holds (scaffold, infra, tokens, i18n, CI, F1–F6). **New this session:**

### F7 — Ledger & Payments (schema `f07`) — PRD §7.7
Depends on F1. Money is integer cents everywhere (BigInteger).
- **Double-entry ledger:** ledger accounts + journal entries + postings. `post_entry()` enforces the **balance invariant** — sum(debits) == sum(credits), ≥2 postings, positive amounts, **single currency per entry**. This is the DoD-critical, tested core.
- **Points are a closed-loop currency:** because an entry cannot mix `usd` and `points` (raises `CurrencyMismatch`), there is **structurally no points→cash path** — the "no cash-out" rule is enforced by the ledger shape, not by policy.
- **Receivable state machine:** `invoiced → acknowledged/disputed → escalated → recovered/written_off`, with terminal states; invalid transitions raise `InvalidTransition`.
- **`record_recovery()`** posts a balanced split (cash debit; driver-payable + platform-contingency credits), links the journal entry to the receivable, and marks it `recovered`.
- **Stripe / Stripe Connect = `PaymentGateway` seam** (`StubPaymentGateway` raises) — structured so the platform never takes custody triggering money-transmitter licensing.
- Migration `0007` (see decision #27). 10 tests.

### Local stack + admin (owner request)
- Full compose stack brought up; **`api/scripts/seed_admin.py`** creates an idempotent dev-only `platform_admin` (`admin@longhaul.local` / `longhaul-admin-dev`, override via env).
- Live URLs: API `http://localhost:8008` (`/health`, `/docs`), driver frontend `http://localhost:9008` (boot smoke page only), MinIO console `http://localhost:9019`, Mailpit `http://localhost:8038`.
- **There is no LONGHAUL admin panel yet — that's F14** (later in the foundation order). The admin account exists now so it's ready when F14/auth endpoints land.

### Verified this session (in compose)
- `alembic upgrade head` clean through `0007`; **up→down→up round-trip verified** for 0007.
- `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 73 passed** (health 1, F1 12, F2 10, F3 13, F4 12, F5 9, F6 6, F7 10) · **vitest 10 passed**.

## 2. Decisions made (append to Decision Log)

26. **Ledger is the source of truth; gateway is a seam.** The double-entry ledger is fully functional with no live payment provider. Stripe/Connect plug in behind `PaymentGateway` at M6/M7 activation. Points redemption rate (points→cents) is F13 config, not hardcoded.
27. **Shared-enum migration pattern.** In this SQLAlchemy/Alembic version, `op.create_table` emits a `CREATE TYPE` per native-enum column even with `create_type=False`, so a **shared** enum (`currency`, on 3 tables) collides. Fix: migration builds a **self-contained local `MetaData`** with one shared `Enum` object + a reference-only stub for the cross-schema FK target (`f01.account`) and calls `metadata.create_all(bind, tables=[...])`, which dedupes the enum. **Reuse this pattern for any future migration with an enum shared across tables** (F8+ likely).
28. **No cash-out is structural.** Enforced by single-currency-per-entry in `post_entry`, not by a policy check that could be bypassed.

## 3. Exact next task

**Build F8 — Notifications & Outbound Communications** next (PRD §7.8), to its component test suite, Docker, tests alongside.
- **Inbound-to-driver channels:** push (FCM/APNs), SMS (Twilio), email — all behind **adapter seams** (stub gateways that record "sent" for tests, real providers wired at activation). **Quiet-hours aware** and **safety-aware** (no interaction prompts while DRIVING — design-prd §13; voice summaries via M11). The **P0/P1/P2 tiering + 2-per-day interruption budget** (design-prd §13.1–13.2) is real, testable logic — build it now.
- **Outbound-to-counterparty:** transactional email with per-thread tracking (sent/opened), templated professional documents, reply-to routing. Counterparty templates are **always English** (F15) and **contract-citing / relationship-preserving** by default.
- **Template registry** versioned alongside the F9 prompt registry — model the registry; the render can start structural (like F4's pack composer). This is the natural home for the **F6 expiry reminders** and **M3 dunning** sends (both currently seams pointing at F8).
- Depends on F1; F15 localization is a hard dependency for driver-facing templates — F15 isn't built yet, so key templates by locale and leave the catalog wiring as an F15 seam. Add `f08` to `db_registry.py` + `conftest` SCHEMAS, a `0008` migration, `tests/foundation/f08_notifications/`.
- Then F9 → F15 in order, then the §7.16 synthetic end-to-end (F1–F9 + F12) + six-locale shell render check to close the Foundation DoD. No module UI until then.

## 4. Blockers / owner questions

Unchanged and non-blocking for F8:
1. **Light-theme token values** — needed before any real screen; not invented.
2. **Locale wording** for pa/uz/so/ru/es pending F15 native review; CI completeness gate live.
3. Session-0 open items (brand, collection partner, external test creds, fuel-price route, TPIMS survey).
4. **External timestamping/anchoring (F4)**, **PDF render toolchain**, **Stripe/Connect structure + points rate (F7)** — owner input before M3/M6/M7 activation; seams for now.
5. **MinIO** bucket naming / lifecycle for the real F6 adapter.
- **New (F8, before activation):** Twilio + FCM/APNs + transactional-email provider selection and credentials — building F8 with adapter seams; needs owner input when notifications go live.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged.

## 6. How to run (all Docker)

```
make up          # full stack (currently running)
make migrate     # alembic upgrade head (through 0007)
make lint        # ruff + 29 import contracts
make test        # pytest 73 + vitest 10
docker compose -f infra/docker-compose.yml exec api python -m scripts.seed_admin   # dev admin
make down
```

## 7. Common Ground progress

**F1–F7 of F15 done.** Remaining: F8 Notifications · F9 AI Gateway · F10 Crowd · F11 Map/POI · F12 Offline Sync · F13 Flags/Config · F14 Admin/Analytics · F15 Localization — then §7.16 e2e + six-locale shell check to close the Foundation DoD.

## 8. Commits this session (local only, never pushed)

… `ed05daf` F5 → `b8e34ce` HANDOFF-004 → `292ec37` F6 → `3e35ee3` HANDOFF-005 → `d8cd2d7` F7 (+ this handoff commit).

*— End of Session 1 (F7) handoff. First action next: read governing docs, then this file, then plan F8.*
