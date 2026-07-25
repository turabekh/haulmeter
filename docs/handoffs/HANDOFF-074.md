# HANDOFF-074 — Admin Console 2.0b: settability boundary · Accounts · gates · vendor onboarding

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).
**State in one line:** the operator console gained an **Accounts** section (create / edit / credential
reset / deactivate, role management), **activation-gate control**, **admin-initiated vendor
registration** — and, first, a **constitutionally enforced settability boundary** that makes the
never-touchable classes unbuildable rather than merely unbuilt.

**Read order each session:** `HANDOFF.md` (pointer → this file) → design-prd §18/§16/§22/§23 →
PRD §7 F13/F14, §17 → this file → HANDOFF-073 (Console 2.0a) → 072 (M13 Session B).

---

## 0. Current state

| Thing | Value |
|---|---|
| Migrations | head **0042_f01_account_management** |
| Tests | **pytest 710 · vitest 220 · ruff clean · import-linter 30/30** |
| `make ci` | **PASSES COLD** |
| Console sections | **8** — Overview · Flags & Config · Vendors · Moderation · **Accounts** · Data & Ingest · Modules · Audit |

---

## 1. Scope: what this session did and did not do

The brief was largely last session's, with decisions 5–9 appended. **Decisions 1–4 and six of the
seven original sections were already shipped** on 26 July (HANDOFF-073); I did not rebuild them.
Per decision 9 I proposed a split, you approved it, and this session took **2.0b**:

| Approved for 2.0b (done) | Deferred to 2.0c (not started) |
|---|---|
| Settability sweep + carve-out tests | **E-D5 assisted edit + "view as vendor" impersonation** |
| E-D6 Accounts | **Decision 7 facility editor** |
| F13 gate exposure | Vendor **detail page** (list-level actions exist) |
| Admin-initiated vendor registration | |

Nothing was thinned silently — the deferred items are listed above and in §5.

## 2. Capability inventory — old → new home (nothing dropped)

Everything from HANDOFF-073's table still holds. This session's additions:

| Capability | Was | Now |
|---|---|---|
| Account directory / search | *did not exist* | **Accounts** — by email, name, MC/DOT, plate, role |
| Account create (phone onboarding) | *did not exist* | **Accounts** — returns a one-time temporary password |
| Account edit (profile, equipment, name) | *did not exist* | **Accounts** |
| Credential reset | *did not exist* | **Accounts** — temporary only, forces change |
| Deactivate / reactivate | *did not exist* | **Accounts** — kills live sessions |
| Role grant / revoke | attach only, in code | **Accounts** — with confirm on `platform_admin` |
| Per-account audit trail | *did not exist* | **Accounts** detail |
| Activation-gate satisfy/withdraw | domain only, unexposed | **Flags & Config** |
| Vendor registration by admin | *did not exist* | **Accounts** → vendor, and `POST /admin/vendors` |

## 3. The settability classification (decision 8)

Full table in the approved plan; the operative half is the **never-touchable** set, now enforced by
negative tests against the live OpenAPI schema:

| Never touchable | Why |
|---|---|
| F4 evidence, evidence log, artifacts, hash chain | An evidence record an admin could edit is worth nothing in a dispute, and a chain with an edit path is not a chain |
| F7 ledger postings, journal entries, receivables | Money is append-only; a correction is a new entry |
| F10 submissions, beliefs, contributor trust | A belief an operator can set is an opinion wearing crowd data's clothes (§11.7) |
| F3 geofence events, pings, presence | They are the evidence behind the money |
| F14 admin_action, analytics events | An editable audit log is not an audit log |
| Others' review / report **text** | Content is hidden or removed whole; the author's words survive the verdict |

**One gap the sweep found and closed:** `validation_gate` was settable in the domain and exposed
nowhere, so a gated flag could not be activated without a shell. Now in Flags & Config — and
**withdrawable**, because a precondition that only ever ticks is a one-way ratchet.

## 4. What the Overview shows (unchanged from HANDOFF-073 §3)

Job health from `f14.job_run` · facility counts from `f02.facility_source` · ingest freshness from
`f02.source_record.ingested_at` · vendor verification depth and moderation depth with the **overdue
count carried separately** · detention funnel from `f14.analytics_event` · vendor
appearance→confirmation from `m13.appearance` rows directly. Module numbers are composed in the **API
router**, not F14 — foundation importing `app.modules.*` would break the architecture spine.

## 5. Exact next task — my recommendation

**2.0c, as split and approved:** E-D5 assisted management (attributed on-behalf edits + scoped
"view as vendor" impersonation, **30-minute time-box**, "edited by Haulmeter support" derived from the
audit log via `target_ref` — both settled at plan approval), the decision-7 facility editor, and the
vendor detail page those two want to live on.

Impersonation is the most security-sensitive thing in the brief — a mechanism letting one human act as
another — which is exactly why it got its own session rather than riding alongside account creation.

**Alternative, and arguably now the higher-value one:** the founding-vendor onboarding is **unblocked
as of this session**. You can create the cook's account, register the vendor, and hand over a temporary
password without touching a shell. Doing that first would produce real data before more console is
built on assumptions about it.

## 6. Blockers / questions

- **Still no git remote.** Step 4 again asked to "push to the private remote only"; `git remote -v` is
  empty, so all four commits are local. Add a remote and I'll push.
- **Deactivation has a mechanism but no policy** (PRD §17 Q15, amended). What conduct warrants it, who
  decides, whether it is appealable, how the person is told. Using the mechanism without the policy is
  how support becomes arbitrary.
- **Hard delete is now §17 Q16** — needs counsel before code: what is erased vs. anonymised in place,
  what survives under legal hold, and how F4 chains stay verifiable when a party to them is gone.
- **Container clock** still reads a day behind the session date; harmless for relative freshness (SLA
  and decay use intervals) but worth knowing before comparing a stored timestamp to a wall clock.

## 7. Working rules (unchanged — non-negotiable)

Docker-only (dev = CI parity) · **local commits only, NEVER push** (no remote configured) · plan-first ·
**tests with every change** · live pulls never in CI · **AI-CONTEXT comments only** · import-linter
authoritative · **design-prd governs ALL UI** (§18 for portals, LAW 0 for the driver app, tokens only) ·
session ends by writing the next HANDOFF.
Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## 8. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-074 + design-prd §23 (E-D6, settability, gates) + PRD §17 Q15/Q16
c7db39a Admin Console 2.0b UI: Accounts section, gate controls, e2e phone onboarding
9cfd1d8 Admin Console 2.0b backend: settability boundary, account management, gates, vendor registration
```

## 9. Key files touched

```
F01         api/app/foundation/f01_identity/domain/{models,service}.py · public.py
            (active + display_name + must_change; search/create/reset/deactivate/roles;
             authenticate now fails CLOSED and distinctly on a deactivated account)
F13         api/app/foundation/f13_flags/domain/service.py · public.py (unsatisfy_gate, get_gate)
API         api/app/api/admin.py (accounts, gates, vendor registration)
TESTS       api/tests/api/test_settability.py (NEW) · test_accounts_api.py (NEW)
            api/tests/api/test_admin_console_api.py · tests/e2e/test_full_platform_e2e.py
UI          ui/src/surfaces/admin/AdminAccounts.vue (NEW) · AdminShell.vue · AdminFlags.vue
            ui/src/router.js · ui/src/core/api.js · i18n/*.json (23 keys ×6)
            ui/test/admin-console.test.js
MIGRATION   0042_f01_account_management
DOCS        design-prd.md · trucker-platform-prd.md · HANDOFF-074.md · HANDOFF.md
```

## 10. Ports / env

**No port or env changes**, as expected. Migration 0042 applied. No new F13 config keys this session.
