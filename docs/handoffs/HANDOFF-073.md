# HANDOFF-073 — Admin Console 2.0: sectioned operator portal

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).
**State in one line:** F1–F15 + M1–M13 complete; the F14 operator surface is **rebuilt as a
seven-section portal** with a real audit trail (before→after on every mutation), worker job
telemetry, and moderation integrity guards — and that telemetry immediately caught a **live ingest
job that had been silently failing since 25 July**.

**Read order each session:** `HANDOFF.md` (pointer → this file) → design-prd §18/§16/§22/§23 →
PRD §7 F13/F14, §17 → this file → HANDOFF-072 (M13 Session B) → 071 (Session A).

---

## 0. Current state (dev DB, live)

| Thing | Value |
|---|---|
| Facilities | **4153** · beliefs **19** (TPIMS parking beliefs updating again — see §4) |
| Job runs recorded | **9** across the three feeds, all `ok` |
| Audit entries | **25**, now carrying before→after |
| Migrations | head **0041_f14_audit_clock** (0039–0041 this session) |
| Tests | **pytest 667 · vitest 212 · ruff clean · import-linter 30/30** |
| `make ci` | **PASSES COLD** (`make down && make ci && make up`) |

---

## 1. Capability inventory — old → new home (nothing dropped)

| # | Capability | Was | Now |
|---|---|---|---|
| 1 | Flag list + gates | stacked panel | **Flags & Config**, grouped by family, searchable |
| 2 | Flag enable/disable | one button, label = action | **Flags & Config** — state pill + separate action button, confirm-on-disable for module flags |
| 3 | Runtime config | stacked panel | **Flags & Config** — + provenance and the value it replaced |
| 4 | Module admin-view registry | flat list of links | **Modules** — built vs. *labelled* not-built (see §3) |
| 5 | Moderation queue + SLA | stacked panel | **Moderation** — + report counts, three verdicts |
| 6 | Moderation item decide | stacked panel | **Moderation** — *and now audited; it recorded nothing before* |
| 7 | Report resolve | API only | **Moderation** — + frivolous verdict |
| 8 | Overdue queue | API only | **Overview** count (flare) + rail badge |
| 9 | Vendor list | API only | **Vendors** |
| 10 | Vendor verify/suspend | API only | **Vendors** — + API-layer audit with before→after |
| 11 | Claim disputes | API only | **Vendors** |
| 12 | Detention funnel | stacked panel | **Overview** |
| 13 | Audit log | stacked panel | **Audit** — + before→after, filters |
| 14 | Vendor documents | *did not exist* | **Vendors** (new endpoint) |
| 15–16 | Ingest flags + source URLs | inside flags/config | **Data & Ingest** (+ still in Flags) |
| 17 | Worker job health | **stdout only** | **Overview** + **Data & Ingest** (new `f14.job_run`) |
| 18–19 | Facility counts, ingest batches | *did not exist* | **Data & Ingest** |
| 20 | M13 appearance→confirmation | *did not exist* | **Overview** |

**Two capabilities §3.1 named that did not exist:** a fuel-network admin surface (registry row only)
and dedupe/merge review (`merge_facilities` is a service function with no admin surface). Both remain
gaps, now visible in **Modules** rather than implied.

## 2. Decisions logged

**design-prd §23** — four entries: **E-D4** (section rail; NAV-1 governs the *driver* app, a portal
rail is not a driver-app drawer; router children so a queue is bookmarkable); **state pill ≠ action
button**, with confirm-on-disable only where a change reaches every driver; **ops honesty** — "never
ran", "switched off" and "failing" are three facts no surface may collapse, and operator timestamps
are never localized; **a registered capability with no destination is labelled, never linked**.

**PRD §17** — **Q14** records the moderation guards; **Q15** opens account-level suspension/banning as
a deliberate non-goal: the guards withdraw *automatic* weight from an abusive account but never its
access, and a real banning policy needs its own decision about conduct, appeal, and what happens to
that driver's evidence, claims and money. Not something to answer incidentally inside a console rework.

**Moderation guards (decision 4), shipped:** a vendor reporting their own listing or reviews is
**recorded but carries no weight** — discarding it would hide the abuse from the only person able to
act; reports are rate-limited (`m13_reports_per_day`, default 5); **frivolous** is a third verdict
whose strike lands on the reporter, and at 3 strikes that account's reports stop carrying auto-hide
weight while still reaching a moderator. That is **not a ban**.

## 3. What the Overview shows, and where each number comes from

| Panel | Source |
|---|---|
| Job health (last run, ok/failing/off, streak, next attempt) | **`f14.job_run`**, new — one row per *attempt*; a flag-off tick is deliberately not recorded |
| Facility counts by source | `f02.facility_source` grouped by `source_kind` |
| Ingest freshness | `f02.source_record.ingested_at`, max + count per source |
| Vendor verification depth | `m13.vendor` where tier = `documents_on_file` |
| Moderation depth + **overdue** | `m13.queue_with_sla` against `F14.MODERATION_SLA_HOURS` (72) |
| Claim disputes | `m13.facility_claim` where status = `disputed` |
| Detention funnel | `f14.analytics_event` via `admin.funnel` |
| Vendor appearance→confirmation | `m13.appearance` rows directly — the rows *are* the record; an event stream would be a second source of truth that could drift |

**Architecture note:** module numbers are composed in the **API router**, not F14. F14 is foundation
and importing `app.modules.*` would break the architecture-spine contract. F14 owns only the generic
ops primitives (job runs, audit). §3.3 of the prompt asked for F14 aggregation; this is the same
result with the contract intact.

## 4. The bug the telemetry caught on its first run

`tpims_dynamic` had been raising `NoReferencedTableError` **on every tick since 25 July** — the IL
TPIMS parking beliefs had stopped updating and nobody knew, because the worker logged only to stdout.
That is exactly the gap the Overview was built to close, and it closed it within a minute of the
worker restarting.

**Confirmed pre-existing, not a regression:** reproducing the old import set fails identically. Cause:
a job touches only its own tables, but those carry cross-schema FKs (`f10.submission → f01.account`),
and SQLAlchemy cannot configure a mapper whose FK target was never imported. The worker imported a
subset; migrations and purge scripts already call `db_registry.import_all_models()`, and the worker now
does too. Beliefs verified updating again (42s old, `{"applied": 8}`).

**Also hardened:** `SessionLocal()` sat outside the startup guard, so a database a few seconds late
coming up killed the worker at boot instead of leaving it to retry.

The regression test asserts the *guarantee* rather than reproducing the failure — pytest's conftest
imports every model before any test runs, which is precisely why a green suite never caught this.

## 5. Exact next task — recommendation, your call

**Recommended: founding-vendor onboarding, now unblocked.** HANDOFF-072 recommended it and the console
was the missing piece — you now have a Vendors section with the verification queue, documents inline,
and an audit trail attributing every decision. The remaining work is operational: enable `m13_vendor`
deliberately, register the FL vendor with his consent, and watch the first real appearance →
confirmation → review loop.

Alternatives: **TPIMS second-state activation** (still gated on reachable feeds/credentials — and now
that job health is visible, a second state is safer to add); **§17 Q9 truck routing**, the largest open
product decision; **dedupe/merge review**, the one operator capability with no surface at all.

## 6. Blockers / questions

- **There is no git remote.** Step 4 asked me to "push to the private remote only" — `git remote -v` is
  empty, so everything is committed locally as usual. Add a remote and I'll push.
- **The three LOCKED ports and the container clock.** The DB clock reads 25 Jul while the session date
  is 26 Jul. Harmless for relative freshness (the SLA and decay all use intervals), but if you ever
  compare a stored timestamp against a human's wall clock, know they differ.
- **Founding FL vendor** — still not registered; no real-person data has been seeded, per instruction.
- **§17 Q9, Q13, Q15 remain open.** Q15 (account banning) is new and deliberately unanswered.

## 7. Working rules (unchanged — non-negotiable)

Docker-only (dev = CI parity) · **local commits only, NEVER push** (no remote configured) · plan-first ·
**tests with every change** · live pulls never in CI · **AI-CONTEXT comments only** · import-linter
authoritative · **design-prd governs ALL UI** (§18 for portals, LAW 0 for the driver app, tokens only) ·
session ends by writing the next HANDOFF.
Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## 8. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-073 + design-prd §23 (E-D4 + three rulings) + PRD §17 Q14/Q15
719e001 fix: worker registered a subset of models — tpims_dynamic failing since 25 Jul
ce01c04 Admin Console 2.0 UI: sectioned portal replacing the single stacked page
dc81c3c Admin Console 2.0 backend: audit before/after, job telemetry, moderation guards
```

## 9. Key files touched

```
F14         api/app/foundation/f14_admin/domain/{models,service}.py · public.py
            (AdminAction.before/after/target_key, JobRun, MODERATION_SLA_HOURS)
WORKER      api/app/worker.py (job telemetry + full model registration + boot hardening)
M13         api/app/modules/m13_vendor/domain/{moderation,models}.py · public.py
API         api/app/api/admin.py (7 new reads, audit on every mutation)
TESTS       api/tests/foundation/f14_admin/test_audit_and_jobs.py (NEW)
            api/tests/modules/m13_vendor/test_report_guards.py (NEW)
            api/tests/api/test_admin_console_api.py (NEW) · tests/ingest/test_worker_startup.py (NEW)
            api/tests/e2e/test_full_platform_e2e.py
UI          ui/src/surfaces/admin/** (NEW: shell + 7 sections + shared CSS)
            ui/src/surfaces/AdminConsoleSurface.vue (DELETED)
            ui/src/router.js · ui/src/core/api.js · i18n/*.json (61 keys ×6)
            ui/test/admin-console.test.js (NEW, replaces 5 removed assertions)
MIGRATIONS  0039_f14_audit_and_jobs · 0040_m13_report_guards · 0041_f14_audit_clock
DOCS        design-prd.md · trucker-platform-prd.md · HANDOFF-073.md · HANDOFF.md
```

## 10. Ports / env

**No port or env changes**, as expected. Migrations 0039–0041 applied. Two new F13 config keys, DB rows
unset by default so code defaults apply: `m13_reports_per_day` (5), `m13_frivolous_strikes` (3).

One migration worth flagging: **0041 changed the audit timestamp from `now()` to `clock_timestamp()`.**
In PostgreSQL `now()` is the *transaction* start time, so entries written in one transaction shared a
timestamp and "who touched this last" was non-deterministic — the one question an audit log exists to
answer.
