# HANDOFF-072 — M13 Vendor Network Session B: FR5–FR8 + Q-8 (module complete)

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).
**State in one line:** F1–F15 + M1–M12 complete; **M13 Vendor Network is now complete through Phase A** —
Session A's discovery core plus **FR5 reviews, FR6 promotions, FR7 service-center claiming, FR8 vendor
portal and Q-8 moderation SLA**, all behind `m13_vendor` (default OFF), with **zero payment code paths**
and the **§E1.9 quality-law table fully covered for the first time**.

**Read order each session:** `HANDOFF.md` (pointer → this file) → `docs/prd-extension-m13-vendor-network.md`
(**E1, APPROVED, both sessions BUILT**) → PRD §6/§17 → design-prd §11.7/§13/§16/§18/§22/§23 → this file →
HANDOFF-071 (Session A) → 070 (fuel nudge · points cooldown · TPIMS).

---

## 0. Current data state (dev DB, live)

| Thing | Value |
|---|---|
| Facilities | **4153** — OSM 2321 · NTAD 1827 · TPIMS 54 (IL) · admin/DEV_SEED 10 |
| M13 demo data | 1 vendor (`is_dev`) · 1 appearance · **1 review · 1 promotion** · 0 claims · 0 reports |
| Flag `m13_vendor` | registered, **OFF** (PRD §6: flags gate activation, never scope) |
| Migrations | head now **0038_m13_session_b** |
| Tests | **pytest 607 · vitest 181 · ruff clean · import-linter 30/30** |
| `make ci` | **PASSES COLD** (`make down && make ci && make up`) — preflight clean, all stages green |

---

## 1. What this session built

### Housekeeping (`fc27510`)
The two stray space-joined directories from a Session-0 `mkdir` are gone, in their own one-line commit.

### FR5 — Vendor reviews (`303c779`)
Rating 1–5 + short text, **one per driver per vendor per 7 days** (F13-tunable). Two deliberate
departures from the M2 pattern, both reasoned in the module docstring:

- **Publish immediately; queue on report.** M2 holds every facility review pre-publication because a
  facility scorecard carries defamation exposure (PRD §13). A driver's note about a meal does not, and
  holding every review would make the section read as dead.
- **No points.** M2 pays `REVIEW_POINTS` through the F7 ledger. Points are the M10 closed-loop economy
  funded against the M6 take; routing a reward through the ledger from M13 is precisely the
  money-adjacent path Phase A forbids — and would have tripped the no-`issue_points` assertion.

**Distinct-REVIEWER counting** is the §11.7 discipline: past the window a driver's new verdict
*replaces* their old one, so "12 drivers" always means twelve people.

### FR6 — Promotions (`303c779`, PRD §17 Q10)
Free, any tier, **labelled slots only**. **Q-3 holds structurally, not by vigilance:** promotions are
read by `promotions_for_facility`, a function the ranking path never calls; `rank_entries` takes no
promotion argument; the API serves them from a separate endpoint; the UI takes them as a separate prop.
The Session-A grep-test passes **unmodified**, and new tests assert the ranked list is identical with
and without a promotion live and that no promotion text appears inside a `.vendor` row in the DOM.
Push rides the existing `vendor_alert` caps — **no cap was loosened**. No price, bid, or budget column
exists anywhere.

### FR7 — Service-center claiming (`303c779`)
Gate: `service_center` vendor + a facility whose **E3.2 `services` list** is non-empty + business-name
match + document → F14. **Curated facts live on the claim row and are unioned on read**, so a claim is
physically incapable of erasing what ingestion recorded — the payoff of the Q12 decision, since FR7
reads the same list rather than keeping a rival copy. A second claimant becomes a **dispute** for a
human, because "who owns this business" is not a question code should answer.

### Q-8 — Moderation SLA (`303c779`) — the last quality law
Report severity is **asymmetric by blast radius** (owner-approved over the strict literal reading): a
reported review hides on the first report; a reported **vendor listing** needs reports from **N distinct
drivers** (default 3, F13-tunable), because one anonymous report must never be a competitor's kill
switch on a livelihood. The unique constraint on `(content_kind, content_ref, account_id)` is what makes
"distinct" mean anything. Repeat-offender suspension counts reports a moderator **upheld**, never
reports received. `MODERATION_SLA_HOURS = 72` lives in **F14**, not M13 — every module's queue makes the
same promise to the same people, and a per-module SLA would quietly become several different promises.

### FR8 — Vendor portal (`8e507c8`, `e39135b`)
`/vendor-portal`, the fourth §18 surface. Desktop-first, 1200 dp cap, tokens only, imports no driver
screen. Tenancy runs through **one gate** (`_my_vendor`); a second vendor attempting each write is
asserted to get a 404. Two rules it may not soften: the show-up pair the vendor sees is the **same
string** drivers see (test-asserted, no vanity variant), and a suspension is stated plainly at the top
rather than discovered when a publish fails. Promotion delivery reports what actually went out, because
the `vendor_alert` caps suppress some sends.

## 2. Decisions logged

**PRD §17 Q10 — RESOLVED:** promotions free in Phase A, labelled slots only, any tier. Paid placement
stays **open**; nothing was built toward it. Q-3 keeps pay-to-rank in discovery permanently out.
**PRD §17 Q11 — RESOLVED:** the `property_approved` self-attestation suffices for ranked placement, with
**no** consent-document requirement. That is only defensible because lying about it is actionable:
`ModerationReason.false_property_attestation` ships as a driver-selectable reason feeding Q-8, and an
upheld report counts toward suspension. **The boost and the consequence shipped together, deliberately.**
**design-prd §23** gained four entries: labelled promotion slots (§21.3 reconciliation), the
review-average-needs-its-denominator rule, the asymmetric report severity, and the portal's two
anti-vanity rules.

## 3. §E1.9 quality-law coverage — now complete

| Law | Covered by | Where |
|---|---|---|
| **Q-1** no dead content | appearance expiry · lapse · 28-day dormancy · **promotion expiry** | `test_appearances.py`, `test_promotions.py` |
| **Q-2** reliability load-bearing | show-up rate · no-history neutral · 3 strikes · vendor can't self-confirm | `test_appearances.py`, `test_discovery.py` |
| **Q-3** deterministic ranking | buckets · tiebreaks · pure · no promotion input (**grep-test unmodified**) · **ranked list identical with a promotion live** · **no promo text in a `.vendor` row** | `test_discovery.py`, `test_promotions.py`, `vendor-ui.test.js` |
| **Q-4** publish floor | each field named · "none" is a valid halal answer · portal shows the gaps | `test_appearances.py`, `test_vendor_portal_api.py` |
| **Q-5** one canonical vendor | phone · name+metro · cross-metro allowed · merge | `test_vendor_identity.py` |
| **Q-6** noise budget | 2/card · 3/corridor · `vendor_alert` ≤1/day **across promotions** · mute · quiet hours | `test_discovery.py`, `test_promotions.py`, `vendor-ui.test.js` |
| **Q-7** empty states | section absent · quiet line + working "suggest a cook" · portal empty states | `test_discovery.py`, `vendor-ui.test.js` |
| **Q-8** moderation SLA | **NOW COVERED** — report→hidden-pending (both kinds) · N-distinct threshold · one driver can't manufacture it · resolution restores/removes · 72h overdue flagging · repeat-offender suspension · suspension blocks publishing · false-attestation reason | `test_moderation.py`, `test_admin_api.py`, `vendor-ui.test.js` |
| Phase-A law | no ledger import · no money symbol · **allowlist + money-shaped-name net** · no payment endpoint · no `m13_orders` | `test_phase_a_law.py` |

## 4. Three real bugs found while testing (all fixed)

1. **Review cadence anchored on the DB clock**, not the injected timestamp — every other M13 timestamp
   is caller-supplied, so the window was untestable and inconsistent.
2. **Claims and promotions checked only `publish_suspended`** — an *admin*-suspended vendor still showed
   as facility owner and could still promote. Now one `is_presentable()` predicate both routes satisfy.
3. `test_phase_a_law.py`'s exact table allowlist fired on any new table. Per your approval it was
   extended **and made stricter**: a second net fails a table on a money-shaped **name**, so nothing
   slips through merely by being listed.

## 5. Exact next task — my recommendation, your call

**Recommended: founding-vendor onboarding readiness.** M13 is feature-complete for Phase A and the
portal now exists, so the blocking work is operational rather than code: activate `m13_vendor` in a
controlled way, walk the real FL vendor through registration in the F14 console with his consent, and
watch the first real appearance → confirmation → review loop. That is what turns this from a built
module into a working one, and it is the only path that produces the data §E1.10's metrics need.

Alternatives:
- **HANDOFF-070/071 leftovers** — TPIMS second-state activation still waits on reachable feeds or
  registration credentials (IA/KS/MI/WI gated; IN/OH unreachable from this network).
- **The §17 queue** — Q9 (truck routing) is the largest open product decision and is driver-requested;
  Q13 (Phase B trigger) is the largest open M13 one.

## 6. Blockers / questions for you

- **Founding FL vendor** — still not registered, per your instruction. When you are ready I can prepare
  the exact admin console steps; I will not enter any real-person data myself.
- **§17 Q9 and Q13 remain open**, and Q13 gates anything Phase B.
- **Promotion route-relevance is approximated.** The `vendor_alert` class declares `route_relevant_only`,
  but no live per-driver route context exists (M8 exposes no route feed), so the audience is "drivers who
  have confirmed this vendor before". That is documented in the code rather than claimed as route
  targeting. Closing the gap properly is a Q9-adjacent piece of work.
- **Review paging** — the sheet carries the 10 most recent reviews; there is no "see all". Fine at
  current volume, worth revisiting when a vendor passes a few dozen.

## 7. Working rules (unchanged — non-negotiable)

Docker-only (dev = CI parity) · **local commits only, NEVER push** · plan-first for non-trivial work ·
**tests with every change** · **live pulls never in CI** (fixtures drive tests) · **AI-CONTEXT comments
only** · maximum modularity (import-linter authoritative: core < foundation < modules, `.public` only) ·
**design-prd governs ALL UI** (mobile-first 360dp for driver surfaces, §18 for portals, tokens only,
§22.3 DoD) · session ends by writing the next HANDOFF.
Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## 8. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-072 + PRD §17 Q10/Q11 resolved + design-prd §23 (four entries)
e39135b M13 Session B UI: promoted slots, reviews, report affordance, vendor portal
8e507c8 M13 Session B API: review/report endpoints, vendor portal, admin SLA queue
303c779 M13-FR5/FR6/FR7 + Q-8 domain: reviews, promotions, claims, moderation SLA
fc27510 chore: remove two stray space-joined test directories from a Session-0 mkdir
```

## 9. Key files touched (by area)

```
M13 DOMAIN  api/app/modules/m13_vendor/domain/{reviews,promotions,claims,moderation}.py (NEW)
            api/app/modules/m13_vendor/domain/{enums,models,service}.py · public.py
            api/migrations/versions/0038_m13_session_b.py
F14         api/app/foundation/f14_admin/domain/service.py (MODERATION_SLA_HOURS,
            overdue_moderation) · public.py
API         api/app/api/vendor_portal.py (NEW) · api/app/api/m13_vendor.py · admin.py · main.py
TESTS       api/tests/modules/m13_vendor/{test_reviews,test_promotions,test_claims,
            test_moderation}.py (NEW) · test_phase_a_law.py
            api/tests/api/{test_vendor_portal_api.py (NEW),test_admin_api.py}
            api/tests/e2e/test_full_platform_e2e.py
UI          ui/src/surfaces/VendorPortalSurface.vue (NEW) · MapSurface.vue
            ui/src/core/components/{VendorSheet,FacilityCard}.vue
            ui/src/core/{vendors.js,api.js} · ui/src/router.js
            ui/src/core/i18n/*.json (42 keys ×6) · ui/test/vendor-ui.test.js
SEED        api/scripts/{seed_demo,purge_demo}.py
DOCS        docs/prd-extension-m13-vendor-network.md · trucker-platform-prd.md ·
            design-prd.md · docs/handoffs/HANDOFF-072.md · HANDOFF.md
```

## 10. Ports / env

**No port or env changes**, as expected. Migration 0038 applied. Five new F13 config keys, all DB rows
unset by default so the code defaults apply: `m13_review_cooldown_days` (7),
`m13_vendor_hide_reports` (3), `m13_repeat_offender_strikes` (3), `m13_claim_name_match` (0.55), and
Session A's two. `EIA_API_KEY` still required in `infra/.env` for live EIA pulls.
