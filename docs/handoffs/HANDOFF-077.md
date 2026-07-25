# HANDOFF-077 — Vendor portal: signup, sectioned portal, standing menu

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).
**State in one line:** a cook can now **sign themselves up, build a menu, and publish a week** — the
portal previously had no door of its own and could cancel an appearance but not create one.

**Read order each session:** `HANDOFF.md` (pointer → this file) → design-prd §18/§22/§23 → PRD §7 F13/F14
and extension §E1 → this file → HANDOFF-076 (weigh stations) → 075 (Admin Console 2.0c).

---

## 0. Current state

| Thing | Value |
|---|---|
| Migrations | head **0044_m13_menu_item** |
| Tests | **pytest 819 · vitest 287 · ruff clean · import-linter 30/30** |
| `make ci` | **PASSES COLD** |
| Portal sections | 6 — Overview · My week · Menu & prices · Promotions · Verification · Reputation |
| Vendor signup | **open, self-serve**, no approval queue (owner decision) |

---

## 1. What the audit found

The backend was well ahead of the UI. Three endpoints existed with **nothing calling them**:

| Endpoint | Shipped | Called by the portal |
|---|---|---|
| `POST /vendors/register` | M13 Session A | no |
| `POST /vendor/appearances` | M13-FR8 | **no** |
| `POST /vendor/documents` | M13-FR8 | no |
| `GET/POST/PATCH /vendor/claims` | M13-FR7 | no |

So the portal could **cancel** a cook's week but not fill it, and the way in did not exist at all.

## 2. What this session built

### The door — `/vendor-portal/join`

The auth gate sent every unauthenticated visitor to the **driver** login: mobile-first, asking for an
**authority number**, landing on `/map`. A cook had no way back but the URL bar.

The portal now has its own §18 door — desktop-first, never mentions a truck — with three states on one
route (sign in · create account · describe the business). The gate also learned a `next` redirect, so
nobody is dumped somewhere they were not going.

Per the owner decision, registration is **open**: a cook lands on **UNVERIFIED**, their pin says so, and
the gate is the machinery that already exists — the Q-4 publish floor, the tier ladder, Q-8 moderation.
The signup form asks for exactly what the floor will require, so "you cannot publish yet" is never
discovered afterwards.

### Structure — the rail, reused not invented

Six sections as router **children** under `/vendor-portal/*`, behind the rail approved for the admin
console (§23 E-D4). §22.2 makes navigation structure a never-improvise category; the resolution order's
"nearest analogous rule" points at a structure already approved for the same portal family.

**Two things live in the SHELL, not a section:** the impersonation banner and a publish suspension — a
cook must not have to be on the right page to learn either.

### Menu & prices — and the guarantee that makes it safe

`Offering` rows hung off `appearance_id` and nothing else, so every dish and every price was retyped for
every window. `menu_item` (migration 0044) is the list a cook keeps.

**It deliberately does not replace `offering`.** Publishing **snapshots** the menu, so:

> raising a price today changes what is advertised **next**, and never what a driver was shown last
> Tuesday.

That is not a schema convenience. The reliability record and the reviews both refer to past windows; a
menu that rewrote history would make both unauditable. The portal states it in one sentence above the
price table, because without it a cook assumes one of the two wrong things — that old listings silently
update, or that they must re-publish to correct a price going forward.

Verified against live data (§6): published $12.00 → menu raised to $13.50 → the published window still
reads $12.00.

### The rest

- **Publish an appearance** — facility picker, time window, weekly recurrence, offerings pre-filled from
  the menu. A refused publish renders the Q-4 gaps as **named fields**, not "something went wrong".
- **Verification** — upload a permit; the ladder is stated for what it is. `documents_on_file` means
  paperwork was received, an upload reads "pending", and the middle rung never wears the success token.
- **Full profile** — name, type, metro, phone, categories, plus the existing languages/halal.
- **Reputation** — reviews as written, the raw show-up pair, upheld reports and no-show count with the
  consequence beside them. No reply box and no takedown button: a vendor disputing a review goes through
  the same moderation queue as anyone else.
- **Promotions** — edit added; editing never re-sends, because the alert budget was spent at creation
  and an edit that pushed again would route around the one-per-driver-per-day cap.

## 3. The bug found on the way

**`/vendor/analytics` reported `sheet_views` from an unscoped count.** Every vendor was shown the
**platform-wide total** as their own traffic. The events already carried `properties.vendor_id`; the
counter simply ignored it. F14's `count_events` gained a `properties_match` filter and the figure is now
this vendor's. There is a test with two vendors asserting one sees 3 and the other 0.

This is the exact §11.7 failure the portal's own file header forbids — and it had been shipping since
FR8. Worth noting because it is the failure mode a portal is most prone to: the reader is the person
being described, and a flattering number is not questioned.

## 4. Phase A

Untouched. No order, basket, total or billing column; `price_cents` is information exactly as it already
was on `Offering`. `menu_item` was added to `test_phase_a_law.py`'s allowlist **as a deliberate decision
with its reasoning recorded in the file** — that allowlist exists precisely to force this, and the
money-word net still catches a table by name independently.

`test_phase_a_law.py` is green. The only change to it is the allowlist entry and its comment.

## 5. Decisions logged (design-prd §23)

Three entries: **portal navigation** (rail reused, and why that satisfies §22.2 rather than sidestepping
it), **open self-serve signup** (why the existing guards are the gate), and **menu-vs-offering prices**
(the snapshot guarantee, stated as a truthfulness rule rather than a schema note).

## 6. Verified live

A cook signed up, added two dishes, published both at a real ingested Pilot, then raised a price:

```
5. publish            -> appearance created
6. as advertised      Tamales (pork) $12.00 · Pozole $14.00
7. raise a price      Tamales (pork) now 1350
8. published window   Tamales (pork) $12.00 · Pozole $14.00   <- unchanged
   menu now           Tamales (pork) $13.50 · Pozole $14.00
9. sheet_views        0  (mine only, not the platform's)
```

## 7. Exact next task — recommendation

**Founding-vendor onboarding.** It has been the standing recommendation since HANDOFF-072 and the last
thing it was missing — a portal the cook can actually use — now exists. They can sign up themselves at
`/vendor-portal/join`, or you can register them from the console and hand over a temporary password.

**Then, the gap this session deliberately left:** the **service-center claim flow (FR7)** still has no
portal UI. `/vendor/claims` exists and is uncalled, exactly as `/vendor/appearances` was before today.
It was out of the approved scope; it is the obvious next slice.

**Alternatives:** the four remaining weigh-station states (HANDOFF-076 §6); §17 Q9 truck routing.

## 8. Blockers / questions

- **Still no git remote** — five sessions. Seven commits sit locally on `main`. Add one and I'll push.
- **`merge_facilities` may leave the survivor's attributes stale** (carried from HANDOFF-076 §5) — worth
  checking before relying on the console's facility merge.
- **A vendor cannot delete their own account or listing.** Consistent with §17 Q16 (no hard delete), but
  a self-serve signup makes self-serve *exit* a fair expectation. Worth a decision now that anyone can
  sign up, rather than after the first person asks.
- **Nothing rate-limits vendor registration.** Open signup with the tier ladder as the gate is the
  approved posture, but one account currently equals one vendor with no cooldown. If abuse appears, the
  fix is a rate limit, not a relaxation of the ladder.

## 9. Working rules (unchanged — non-negotiable)

Docker-only (dev = CI parity) · **local commits only, NEVER push** (no remote configured) · plan-first ·
**tests with every change** · live pulls never in CI · **AI-CONTEXT comments only** · import-linter
authoritative · **design-prd governs ALL UI** (§18 for portals, LAW 0 for the driver app, tokens only,
six locales) · session ends by writing the next HANDOFF.
Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## 10. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-077 + design-prd §23 (portal rail, open signup, menu prices)
499391a Vendor portal: a way in, a way to publish, and a menu that keeps its word
```

## 11. Key files touched

```
M13      api/app/modules/m13_vendor/domain/menu.py (NEW — the standing menu)
         .../domain/models.py (MenuItem) · public.py
API      api/app/api/vendor_portal.py (menu CRUD, documents, reputation,
         promotion edit, publish-from-menu, facility_name, scoped sheet_views)
F14      api/app/foundation/f14_admin/domain/service.py (count_events
         properties_match — the fix for the unscoped view count)
MIGRATION 0044_m13_menu_item
TESTS    api/tests/api/test_vendor_menu_api.py (NEW, the snapshot guarantee)
         api/tests/api/test_vendor_portal_features.py (NEW)
         api/tests/modules/m13_vendor/test_phase_a_law.py (allowlist + reasoning)
UI       ui/src/surfaces/vendor/ (NEW — Shell, Join, Overview, Week, Menu,
         Promotions, Verification, Reputation, Profile)
         ui/src/surfaces/VendorPortalSurface.vue (DELETED — fully superseded)
         ui/src/router.js (children + the join door + the redirect-aware gate)
         ui/src/core/api.js · ui/src/core/i18n/*.json (129 keys ×6)
         ui/test/vendor-portal.test.js (NEW) · vendor-ui.test.js · admin-console.test.js
DOCS     design-prd.md §23 ×3 · HANDOFF-077.md · HANDOFF.md
```

## 12. Ports / env

**No port or env changes.** Migration 0044 applied. No new F13 flags — the portal rides the existing
`m13_vendor` flag, which is **enabled in the dev DB**.

Operational note carried forward: `make ci` leaves Postgres running, so `make up` straight afterwards
fails preflight. `make down && make up` is the sequence.
