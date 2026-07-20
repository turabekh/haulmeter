# HANDOFF-005 — Session 1 cont. (F6 Documents Service)

**Project:** LONGHAUL — Consolidated Trucker Platform
**Date:** 20 July 2026 · **State:** Common Ground F1–**F6** built, tested, green in Docker.
**Read order each session:** `HANDOFF.md` (Session 0) + PRD + design-prd, then the latest handoff (this file); earlier handoffs (001–004) for scaffold/F1–F5 context.

---

## 1. What now exists and passes (delta since HANDOFF-004)

Everything from HANDOFF-004 holds (scaffold, infra, tokens, i18n, CI, F1–F5). **New this session:**

### F6 — Documents Service (schema `f06`) — PRD §7.6
Depends on F1. Bytes live in object storage; typed metadata + extraction + expiry live in Postgres.
- **Typed documents:** `rate_con`, `bol`, `pod`, `lumper_receipt`, `cdl`, `med_card`, `insurance`, `permit`, `settlement`, `other` — with content-hash, byte size, account scoping, and a generic `subject_kind`/`subject_ref` link seam (to loads/stops/settlements later).
- **ObjectStorage adapter seam:** `InMemoryObjectStorage` (default, hermetic tests) and a real **`MinioObjectStorage`** (lazy `minio` import, targets the compose MinIO on 9018/9019). `default_storage()`/`set_default_storage()` for wiring; service methods accept an explicit `storage` override.
- **OCR/vision extraction via F9 = seam:** `apply_extraction()` / `mark_extraction_failed()` set structured metadata + status; the actual parse call wires to F9 when it lands.
- **Expiry engine (real, tested):** `active_reminder_offset()` implements **30/14/3-day** windows (exactly one reminder per window, so late first-checks don't fire all three); `due_reminders()` / `mark_reminder_sent()` are idempotent. The actual **send is an F8 seam**.
- Added `minio` dependency (api image rebuilt). Migration `0006`. 6 tests.

### Verified this session (in compose)
- `alembic upgrade head` clean (now through `0006_f06_documents`).
- `ruff` clean · `lint-imports` **29/29 KEPT** · **pytest 63 passed** (health 1, F1 12, F2 10, F3 13, F4 12, F5 9, F6 6) · **vitest 10 passed**.

## 2. Decisions made (append to Decision Log)

23. **Storage is an injected adapter, not a hard dependency.** F6 depends on the `ObjectStorage` protocol; `InMemoryObjectStorage` is the default so the suite is hermetic (no live MinIO needed). `MinioObjectStorage` is the dev/prod adapter, wired when the first upload flow lands (M5 wallet / F6 consumers). Same pattern any future byte-storage need should follow.
24. **Metadata/bytes split.** Only bytes go to object storage; all typed metadata, extraction results, and expiry state stay in Postgres (queryable, migratable). Content-hash stored for integrity/dedup.
25. **Expiry = one reminder per window.** `active_reminder_offset` returns a single offset for the window `(next_smaller, offset]` (30→(14,30], 14→(3,14], 3→[0,3]); expired docs return none. Prevents a late first check from firing 30+14+3 at once. Offsets live in `REMINDER_OFFSETS` — move to F13 config when F13 lands.

## 3. Exact next task

**Build F7 — Ledger & Payments** next (PRD §7.7), to its component test suite, Docker, tests alongside.
- **One double-entry ledger** for all value flows: booking payments, owner payouts, recovered claims, contingency fees, fuel transactions, and points. Model accounts + entries so **every transaction balances (sum of debits == sum of credits)** — that balance invariant is the DoD-critical, tested core.
- **Claim receivables as ledger objects** with a state machine: `invoiced → acknowledged → disputed → escalated → recovered / written_off`.
- **Points as a ledger currency** with a defined redemption rate **against parking bookings only** (no cash-out) — closed-loop; earned per F10 trust-weighted contributions (F10 seam).
- **Stripe / Stripe Connect are adapter seams** (card processing, owner/driver payouts) — structure so the platform never takes custody in a way that triggers money-transmitter licensing; build the ledger + receivable state machine now, stub the Stripe adapter (like MinIO/Twilio).
- Money in **integer cents** (reuse the F5 convention). Depends on F1 (accounts/orgs). Add `f07` to `db_registry.py` + `conftest` SCHEMAS, a `0007` migration, `tests/foundation/f07_ledger/`.
- Then F8 → F15 in order, then the §7.16 synthetic end-to-end (F1–F9 + F12) + six-locale shell render check to close the Foundation DoD. No module UI until then.

## 4. Blockers / owner questions

Unchanged and non-blocking for F7:
1. **Light-theme token values** — needed before any real screen; not invented.
2. **Locale wording** for pa/uz/so/ru/es pending F15 native review; CI completeness gate live.
3. Session-0 open items (brand, collection partner, external test creds, fuel-price route, TPIMS survey).
4. **External timestamping/anchoring (F4)** and **PDF render toolchain** — owner input before M3 activation; seams for now.
5. **MinIO** bucket naming / lifecycle expectations for the real F6 adapter (default: single `documents` bucket, per-account key prefixes) — confirm when convenient.
- **New (F7, will need owner input before M6/M7 activation):** Stripe/Stripe Connect account structure and the points redemption rate (F13 config) — building the ledger now with these as seams/config.

## 5. Port / env changes

**None.** LOCKED ports untouched; `infra/.env.example` unchanged. (F6's real MinIO adapter will use the already-allocated 9018/9019.)

## 6. How to run (all Docker)

```
make up · make migrate · make lint · make test · make ci · make down
```
Current suite: **pytest 63 · vitest 10 · 29 import contracts · ruff clean**, migrations through `0006`.

## 7. Common Ground progress

**F1–F6 of F15 done.** Remaining: F7 Ledger · F8 Notifications · F9 AI Gateway · F10 Crowd · F11 Map/POI · F12 Offline Sync · F13 Flags/Config · F14 Admin/Analytics · F15 Localization — then §7.16 e2e + six-locale shell check to close the Foundation DoD.

## 8. Commits this session (local only, never pushed)

… `c5d4be0` F4 → `1d40e71` HANDOFF-003 → `ed05daf` F5 → `b8e34ce` HANDOFF-004 → `292ec37` F6 (+ this handoff commit).

*— End of Session 1 (F6) handoff. First action next: read governing docs, then this file, then plan F7.*
