# HANDOFF-075 — Admin Console 2.0c: impersonation · assisted edits · facility editor

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).
**State in one line:** the console gained **scoped "view as vendor" impersonation**, **attributed
assisted edits**, a **vendor detail page**, and **console-native facility management** — completing the
Admin Console 2.0 programme (2.0a HANDOFF-073 · 2.0b HANDOFF-074 · 2.0c here).

**Read order each session:** `HANDOFF.md` (pointer → this file) → design-prd §18/§16/§22/§23 →
PRD §7 F13/F14, §17 → this file → HANDOFF-074 (2.0b) → 073 (2.0a).

---

## 0. Current state

| Thing | Value |
|---|---|
| Migrations | head **0043_f01_impersonation** |
| Tests | **pytest 739 · vitest 229 · ruff clean · import-linter 30/30** |
| `make ci` | **PASSES COLD** |
| Console sections | 8 — Overview · Flags & Config · Vendors · Moderation · Accounts · Data & Ingest · Modules · Audit |

---

## 1. What this session built

### E-D5 scoped impersonation — safety by structure, not by procedure

The most dangerous mechanism in the console: one human acting as another. Every safety property is a
consequence of the shape rather than of anyone remembering a rule.

| Property | How it is guaranteed |
|---|---|
| Writes attribute to the **admin** | The session **belongs to the admin** and merely *names* the vendor. Nothing has to pass an actor. |
| Cannot reach a driver endpoint | `resolve_session` **refuses** any impersonation token. That is how E-D5's "vendors only" is enforced rather than intended. |
| Cannot reach the admin console | Same refusal — an impersonating admin is scoped *down*, not sideways. |
| Reads show the vendor's own screen | A `PortalActor` dep separates **subject** (scoping) from **actor** (attribution). A test compares the payload against the vendor's own token. |
| Expires | 30 minutes, endable immediately, both ends audited. |
| Never touches credentials | No code path reads or sets the vendor's password. |
| **No bypass** | A test publishes on an incomplete vendor's behalf while impersonating and gets the Q-4 floor's 422 with the same missing fields the vendor would see. |

Driver impersonation is refused **in the domain** (`start_impersonation` raises), not merely unrouted.

### Assisted edits, attributed and visible
`assisted_*` audit actions carry before→after naming the admin; the vendor sees "Edited by Haulmeter
support" on their own portal, **derived from the audit log via `target_ref`** (as approved) rather than
flags on three tables. A vendor's own edits record nothing — an entry for every ordinary edit would
bury the ones that matter.

### Vendor detail page
Profile, schedule, promotions, reviews, upheld reports, strikes, documents and this vendor's audit
trail on one endpoint, plus the view-as entry point.

### Decision 7 facility editor
**An admin edit is another SOURCE, not an overwrite** — it goes through the same F2 pipeline every
ingest uses, so feeds keep their provenance and the existing priority/union rules arbitrate. Create,
rename, curate services, mark `is_dev`, find duplicates with the pipeline's own matcher, merge. No
delete: facilities are referenced by claims, evidence and beliefs, and merging is the answer.

## 2. Decisions logged

**design-prd §23** — three entries: **E-D5 impersonation** (structural safety, 30-min box, no bypass),
**E-D5 assisted edits** (vendor-visible, derived from the log), **decision 7 facilities** (admin edit
as a source, with the one honest exception noted below).

## 3. Two things found while building

1. **The F2 pipeline has no NAME arbitration rule at all.** It sets the canonical name once at creation
   and never revisits it, so routing a rename through the pipeline changed nothing — my first version
   silently did not work. The name is now set directly, which is safe *precisely because* no ingest
   path renames an existing facility, and the admin source is still recorded so provenance stays
   visible. Commented in place rather than left as a surprise.
2. **My first impersonation client made the token override every request**, which would have broken the
   admin console the moment an operator entered "view as" — admin endpoints reject impersonation tokens
   by design. Now scoped to vendor-portal calls only.

## 4. Admin Console 2.0 — programme complete

| Session | Shipped |
|---|---|
| **2.0a** (073) | Sectioned portal (E-D4) · audit before→after · job telemetry · moderation guards |
| **2.0b** (074) | Settability boundary · Accounts (E-D6) · gate control · admin vendor registration |
| **2.0c** (here) | Impersonation + assisted edits (E-D5) · vendor detail · facility editor (dec. 7) |

Every decision in the brief is now built **except** those deliberately deferred as open questions:
hard delete (§17 Q16) and the deactivation *conduct policy* (§17 Q15).

## 5. Exact next task — recommendation

**Founding-vendor onboarding.** It has been the standing recommendation since HANDOFF-072 and every
tool it needed now exists: create the cook's account from Accounts, register the vendor, hand over a
temporary password, and — if he needs help setting up his schedule by phone — use "view as vendor",
with the assistance visible to him and attributable to you.

That is the first real data this platform will hold. I'd do it before building more console on
assumptions about it.

**Alternatives:** TPIMS second-state activation (job health is now visible, so a second feed is safer
to add); §17 Q9 truck routing, the largest open product decision.

## 6. Blockers / questions

- **Still no git remote** — three sessions running. Five commits sit locally on `main`. Add one and
  I'll push.
- **§17 Q15** — deactivation has a mechanism but no conduct policy. Using it without one is how
  support becomes arbitrary.
- **§17 Q16** — hard delete needs counsel: what is erased vs. anonymised in place, what survives under
  legal hold, how F4 chains stay verifiable when a party to them is gone.
- **Impersonation is powerful and now exists.** Worth deciding who at Haulmeter may hold
  `platform_admin`, since that role now implies the ability to act as any vendor.

## 7. Working rules (unchanged — non-negotiable)

Docker-only (dev = CI parity) · **local commits only, NEVER push** (no remote configured) · plan-first ·
**tests with every change** · live pulls never in CI · **AI-CONTEXT comments only** · import-linter
authoritative · **design-prd governs ALL UI** (§18 for portals, LAW 0 for the driver app, tokens only) ·
session ends by writing the next HANDOFF.
Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## 8. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-075 + design-prd §23 (E-D5 impersonation/assisted, decision 7)
5242930 Admin Console 2.0c UI: impersonation banner, vendor detail, facility editor
11cde42 Decision 7: console-native facility management with provenance-respecting writes
d5f0402 E-D5: scoped vendor impersonation and attributed assisted edits
```

## 9. Key files touched

```
F01         api/app/foundation/f01_identity/domain/{models,service}.py · public.py
            (AuthSession.impersonating_account_id + ended_at; start/end/resolve
             impersonation; resolve_session REFUSES impersonation tokens)
DEPS        api/app/api/deps.py (PortalActor: subject scopes reads, actor attributes writes)
API         api/app/api/admin.py (impersonate, end, vendor detail, facility CRUD/merge/dupes)
            api/app/api/vendor_portal.py (actor/subject scoping, assisted_* attribution)
TESTS       api/tests/api/test_impersonation.py (NEW) · test_facility_editor.py (NEW)
            api/tests/api/test_admin_console_api.py
UI          ui/src/surfaces/VendorPortalSurface.vue (banner + assisted note)
            ui/src/surfaces/admin/{AdminVendors,AdminData}.vue · ui/src/core/api.js
            ui/src/core/i18n/*.json (16 keys ×6) · ui/test/admin-console.test.js
MIGRATION   0043_f01_impersonation
DOCS        design-prd.md · HANDOFF-075.md · HANDOFF.md
```

## 10. Ports / env

**No port or env changes.** Migration 0043 applied. No new F13 config keys.

One operational note: `make ci` leaves Postgres running (its `compose run` starts dependencies), so
`make up` straight afterwards fails preflight. `make down && make up` is the sequence.
