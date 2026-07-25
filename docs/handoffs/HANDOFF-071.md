# HANDOFF-071 — M13 Vendor Network Session A: E2 · E3.2 · FR1–FR4

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 25 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).
**State in one line:** F1–F15 + M1–M12 complete; **M13 Vendor Network Session A is built** —
E2 equipment registration, E3.2 service-center attributes, and M13-FR1..FR4 (vendor identity +
verification ladder, appearances/schedules, map & corridor discovery, crowd confirmation) behind
the F13 flag **`m13_vendor` (default OFF)**, with **zero payment code paths reachable** and every
§E1.9 quality law carrying a test.

**Read order each session:** `HANDOFF.md` (pointer → this file) → `docs/prd-extension-m13-vendor-network.md`
(**E1, now APPROVED**) → PRD §6/§17 → design-prd §11.7/§13/§18/§22/§23 → this file → HANDOFF-070
(fuel nudge · points cooldown · TPIMS) → 069 (live data + honesty).

---

## 0. Current data state (dev DB, live)

| Thing | Value |
|---|---|
| Facilities | **4153** — OSM 2321 · NTAD 1827 · TPIMS 54 (IL) · admin/DEV_SEED 10 |
| M13 vendors | **1** (DEV_SEED "Osh Express (demo)", `is_dev`) · 1 appearance · 3 offerings |
| Beliefs | 19 total, of which **1 `vendor_present`** (crowd, from the demo confirmation) |
| Flag `m13_vendor` | **not yet registered in the dev DB** — `register_module` runs on first use; it defaults OFF when it does |
| EIA regional baseline | 6 regions, week_of 2026-07-20 (unchanged) |
| Migrations | head now **0037_f10_source_width** (0032→0037 this session) |
| Tests | **pytest 505 · vitest 158 · ruff clean · import-linter 30/30** |

No ingest ran this session. The facility count moved 4154 → 4153 because `make purge-demo` was
exercised (see §6) and the re-seed plants one fewer admin facility than the pre-existing leftovers.

---

## 1. What this session built

### Part 1 — E2: F1 equipment registration (`b40a12d`)
`plate_state` · `plate_number` · `unit_number` · `vin` on `f01.driver_profile` (migration 0032),
`PATCH /auth/equipment`, and a **My equipment** section in More. The VIN is **format-validated only**
— ISO-3779 length, alphabet (no I/O/Q), and check digit — so a typo is caught at entry while nothing
is decoded and no vehicle fact is inferred. The honesty note ("Self-reported. We don't verify these.")
sits **above** the fields, and a valid VIN moves no verification state (asserted by test).

### Part 2 — E3.2: service-center granularity as ATTRIBUTES (`b40a12d`)
**Owner decision Q12 = attributes, not new facility kinds.** A wash / tire bay / repair yard rides as
a `services` list on the facility. The deciding argument was design-prd §11.1 — extra signals render
as badges on existing pins, never as more pins — reinforced by composites (a truck stop with a tire
bay keeps **both** facts, which a `tire_shop` kind would erase) and by M13-FR7 reading the same list
(one source of truth). OSM mapping covers `shop=tyres`, `amenity=car_wash`, `shop=truck_repair`,
`service:vehicle:*`; HGV-gated so neighbourhood car washes stay out. `services` **merges by union**
across sources — a deliberate exception to overwrite-by-priority, in the same spirit as the
NTAD-wins-capacity rule, so an OSM extract and an admin edit can't erase each other. **No migration.**

### Part 3 — Foundation seams (`b40a12d`)
- **F10 `subject_ref`** (migration 0034). A belief was keyed `(facility, signal)`, which is right for
  facility-wide readings and wrong the moment a signal is about something *inside* the facility: two
  cooks at one truck stop would tally against each other over one row. `subject_ref` names the
  subject and is an **empty string, never NULL** — PostgreSQL treats NULLs as distinct in a unique
  constraint, so a nullable column would have silently switched off uniqueness for every existing
  belief. Distinct-driver counting, decay and the award cooldown now all scope per subject. Plus
  `SignalType.vendor_present` / `.vendor_sold_out` with entries in every keyed table.
- **F8 opt-in notification classes** (migration 0035, §23 E-D1). A class is a bundle of interruption
  laws stricter than its tier: OFF until the driver turns it on (no preference row = **not** opted in
  — silence is never consent), its own daily cap on top of the §13.1 budget, quiet hours, one-tap
  per-subject mute. `vendor_alert` registered with its FR6 caps; Session A wires exactly one event.

### Part 4 — M13 core FR1–FR4 (`b61decf`)
Schema `m13`, package `api/app/modules/m13_vendor`, import-linter contract added (**30 kept**).
Composes foundation via `.public` only; corridor geometry via `m01.corridor_view`.

- **FR1** — `vendor` role through the F1 registry, multi-member accounts, F6 documents into the F14
  queue, ladder `unverified → documents_on_file → verified`. **Q-5** dedupe blocks on phone / owner
  account / normalized name + metro with `pg_trgm` similarity (the F2 pipeline pattern); duplicates
  **merge**, never coexist.
- **FR2** — a weekly schedule **materializes concrete occurrence rows** over a 28-day horizon rather
  than expanding a rule at read time, because **Q-1** marks occurrences lapsed and **Q-2** scores
  them and neither can act on a rule. **Q-4** publish floor: facility, window, ≥1 offering *with a
  price*, complete profile ("no halal claim" is a complete answer; blank is not).
- **FR3** — **Q-3** ranking is pure and has **no promotion term to reach for** (a test greps the
  function source for one). **Q-6** caps: 2 per card, 3 per corridor. **Q-7**: nothing renders nothing.
- **FR4** — driver reports run the standard F10 pipeline subject-scoped to the vendor; the vendor's
  own "I've arrived" is authoritative and attributed, and **cannot credit its own show-up rate**.

### Part 5 — Driver UI (`0520d27`)
Food badge (**first use of the §11.2 badge slot**), "Food" preset chip, facility-card vendor section,
`VendorSheet`, corridor food lines, More-tab equipment + opt-in food alerts. 360 dp first, tokens
only, six locales + pseudo. The §11.7 split is enforced by **shape**: `presenceLabel` cannot emit a
driver count for a vendor-sourced belief.

Also: F14 console vendor list + verify/suspend; DEV_SEED demo vendor on the `is_dev` pattern;
full-platform e2e extended with the vendor arc.

## 2. Decisions logged

**PRD §6** — module list extends to M13, own flag, own DoD, Phase A discovery-only.
**PRD §17** — Q9–Q13 appended. **Q12 RESOLVED: attributes, not kinds** (rationale above).
**design-prd §23** — five entries: E-D1 `vendor_alert` class · E-D2 food badge + Food chip ·
E-D3 vendor portal joins §18 · **§11.7 vendor-claim-is-never-a-driver-count** ·
**§16 C-1 `documents_on_file` renders neutral** (paperwork is not an endorsement).

Two implementation decisions worth flagging: notification **classes live in code** (like the tier
table) with only the per-driver choice as data; and the **corridor primitive is `m01.corridor_view`,
not M8** — the prompt said M8, but M8 exposes no corridor. Confirmed with you at plan approval.

## 3. §E1.9 quality-law coverage

| Law | Covered by | Where |
|---|---|---|
| **Q-1** no dead content | window→done · sustained "not here"→lapsed · lone report does **not** erase · 28-day dormancy · republish reactivates | `test_appearances.py` |
| **Q-2** reliability load-bearing | show-up rate = confirmed/published · no-history is neither trusted nor punished · 3 strikes suspend + queue F14 · one show-up clears the count · **vendor can't confirm itself** | `test_appearances.py`, `test_discovery.py` |
| **Q-3** deterministic ranking | all four buckets · each tiebreak in order · pure/repeatable · **no promotion input exists** | `test_discovery.py` |
| **Q-4** publish floor | each missing field named individually · "none" is a valid halal answer | `test_appearances.py` |
| **Q-5** one canonical vendor | phone · name+metro · different metro is different · one owner one profile · merge | `test_vendor_identity.py` |
| **Q-6** noise budget | 2/card + 3/corridor, server **and** client · `vendor_alert` ≤1/day | `test_discovery.py`, `vendor-ui.test.js`, `test_notification_class.py` |
| **Q-7** empty states | section absent · quiet line + working "suggest a cook" · empty viewport | `test_discovery.py`, `vendor-ui.test.js` |
| **Q-8** moderation SLA | **NOT covered — Session B** (reports/hide-pending/72h). Only the verification queue exists today. |
| Phase-A law | no ledger import · no order/charge symbol · no money table · no payment endpoint · `m13_orders` not created | `test_phase_a_law.py` |

## 4. Two real bugs found while testing (both fixed)

1. **Reliability read the shared belief row**, so yesterday's confirmation credited today's no-show.
   Now window-scoped to distinct drivers *within the appearance*, excluding the vendor's own report.
2. **`f10.submission.source` at 40 chars truncated `vendor:<uuid>`** (43). Widened to 80 (migration
   0037) rather than shortened — provenance is exactly what §11.7 rests on.

## 5. Exact next task — Session B (FR5–FR8)

**FR5** vendor reviews (M2 pattern scoped to vendors, one per driver per vendor per 7 days,
moderated) · **FR6** promotions (**labelled slots only — Q-3 forbids blending into organic order**;
the `vendor_alert` caps already exist and are tested) · **FR7** service-center claiming (reads the
E3.2 `services` list — one source of truth, already built) · **FR8** vendor portal (§18 fourth portal,
per E-D3). Close out **Q-8** moderation SLA there, and register the founding FL vendor through the
admin console against real consent.

## 6. Blockers / questions for you

- **Founding FL vendor** — deliberately NOT seeded. Registering them needs their real name, phone,
  metro and halal disclosure, plus consent to publish. Want me to prepare the admin call, or will
  you enter it?
- **PRD §17 Q10/Q11/Q13** are open and shape Session B: promotion economics, whether
  `property_approved` attestation is enough for ranked placement, and what opens Phase B.
- **`make ci` cannot run while the stack is up** — its preflight (correctly) sees our own containers
  holding the LOCKED ports. I ran `make lint` + `make test` (identical content, both green). For a
  true cold-start CI parity run: `make down && make ci && make up`.
- **Stray directories** (unrelated, from Session 0): two git-tracked dirs with space-joined names
  under `api/tests/foundation/` and `api/tests/modules/`, each holding an empty `__init__.py`.
  Harmless; say the word and I'll delete them in a one-line commit.

## 7. Working rules (unchanged — non-negotiable)

Docker-only (dev = CI parity) · **local commits only, NEVER push** · plan-first for non-trivial work ·
**tests with every change** · **live pulls never in CI** (fixtures drive tests) · **AI-CONTEXT
comments only** · maximum modularity (import-linter authoritative: core < foundation < modules,
`.public` only) · **design-prd governs ALL UI** (mobile-first 360dp, tokens only, §22.3 DoD) ·
session ends by writing the next HANDOFF.
Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

## 8. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-071 + PRD §6/§17 amendments + design-prd §23 (E-D1..E-D3 + 2 rulings)
0520d27 M13 driver UI: food badge, Food preset, vendor card section + sheet, corridor line, E2 equipment
b61decf M13-FR1..FR4: vendor network backend — identity, schedules, discovery, confirmation
b40a12d E2 + E3.2 + M13 foundation seams: equipment, service tags, subject beliefs, opt-in alert class
```

## 9. Key files touched (by area)

```
E2/F1      api/app/foundation/f01_identity/domain/{models,service,enums}.py · public.py
           api/app/api/auth.py · ui/src/surfaces/MoreSurface.vue
           api/tests/foundation/f01_identity/test_equipment.py · api/tests/api/test_equipment_api.py
E3.2/F2    api/app/foundation/f02_facility/domain/ingest/{adapters,pipeline}.py · public.py
           api/tests/foundation/f02_facility/test_ingest_services.py
           api/tests/fixtures/ingest/osm_services.geojson
F10        api/app/foundation/f10_crowd/domain/{models,service,enums}.py · public.py
           api/tests/foundation/f10_crowd/test_subject_beliefs.py
F08        api/app/foundation/f08_notifications/domain/{models,service,enums}.py · public.py
           api/tests/foundation/f08_notifications/test_notification_class.py
M13        api/app/modules/m13_vendor/** · api/app/api/m13_vendor.py · api/app/api/admin.py
           api/tests/modules/m13_vendor/** · api/tests/api/test_vendor_api.py
UI         ui/src/core/vendors.js · components/{VendorSheet,FacilityCard,MapCanvas,PresetChips,
           CorridorStack}.vue · surfaces/{MapSurface,MoreSurface}.vue · core/api.js
           ui/src/core/i18n/*.json (35 keys ×6) · ui/test/vendor-ui.test.js
SEED/E2E   api/scripts/{seed_demo,purge_demo}.py · api/tests/e2e/test_full_platform_e2e.py
DOCS       docs/prd-extension-m13-vendor-network.md (APPROVED) · trucker-platform-prd.md ·
           design-prd.md · docs/handoffs/HANDOFF-071.md · HANDOFF.md
INFRA      api/importlinter.ini · api/db_registry.py · api/tests/conftest.py · api/app/main.py
           api/migrations/versions/0032…0037
```

## 10. Ports / env

**No port or env changes.** Migrations 0032–0037 applied to the dev DB. Two new F13 config keys
(`m13_inactive_days` default 28, `m13_recurrence_horizon_days` default 28) are DB rows, unset by
default so the code defaults apply. `EIA_API_KEY` still required in `infra/.env` for live EIA pulls.
