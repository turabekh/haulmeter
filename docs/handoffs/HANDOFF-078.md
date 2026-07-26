# HANDOFF-078 — Food search & filters · consolidated platform state

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** a driver can now **search and filter food** — by dish, by language spoken, and by
the vendor's own halal answer — which closes the loop opened last session, when the vendor portal
started collecting exactly those facts and nothing on the driver side used them.

This handoff is **consolidated**: §§1–5 cover this session, §§6–11 are the whole-platform picture that
has been accumulating across 073–077 and deserves one place to live.

**Read order each session:** `HANDOFF.md` (pointer → this file) → `docs/trucker-platform-prd.md` (build
law) → `docs/design-prd.md` (design constitution, §22 protocol + §23 log) → this file → HANDOFF-077
(vendor portal) → 076 (weigh stations).

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0045_m13_halal_claim** |
| Tests | **pytest 838 · vitest 303 · ruff clean · import-linter 30/30** |
| `make ci` | **PASSES COLD** |
| §23 decision log | 31 entries |
| Handoffs | 000 → 078 |
| Git | **10 commits local on `main`, no remote configured** |

### Live data in the dev DB

| Facilities (4,278 live) | | M13 | |
|---|---|---|---|
| rest_area | 1,585 | vendors | 5 |
| truck_stop | 1,457 | appearances | 28 |
| parking_property | 563 | menu items | 7 |
| fuel_station | 549 | promotions | 2 |
| weigh_station | 106 | reviews | 1 |
| scale | 15 | reports / claims / documents | 0 |

### Flags ON in dev

`f01_authority_verification` · `f02_ingest_ntad` · `f02_ingest_osm` · `f02_ingest_tpims_static` ·
`f02_ingest_tpims_dynamic` · `m01_map` · `m01_weigh_stations` · `m07_ingest_eia` · `m11_voice` ·
`m13_vendor`

---

## 2. What this session built

### The §11.3 "More filters" sheet — specified in v1.0, never built

`PresetChips.vue`'s own header comment already referred to it. §11.3 reads *"presets over filters …
**one 'More filters' sheet exists**; presets are the interface."* So this was **finishing a commitment
the constitution had already made**, not a §22.2 improvisation — no new token, component pattern or
navigation structure. It is composed from the existing pill/chip shape and BottomSheet (NAV-3).

Scoped to the **Food preset only**, because no other preset has anything to narrow yet. Three
narrowings, all of them facts the **Q-4 publish floor already forces a cook to provide**:

| Filter | Matches |
|---|---|
| dish / name | vendor name **and** dish names, partial, case-insensitive |
| speaks | the six shipped locales |
| halal | the vendor's own closed answer (see §3) |

### The load-bearing property: a filter can only ever show LESS

Filters are applied **server-side**, to the output of the §E1.9 quality laws and the Q-3 ranking — never
in place of either. No combination can surface a lapsed appearance, an expired listing or a suspended
vendor, and none can reorder anything. There is a test that cancels every appearance and asserts that no
filter brings one back.

The client never filters locally. A client that held everything and hid some of it would be one bug away
from showing a driver a listing the server had already retired.

### Three smaller decisions that matter more than they look

- **Search is bounded by the viewport, and the sheet says so.** An empty result must read as "none in
  this view", never "none anywhere".
- **"No cooks here" and "your filter hid them" are different facts.** They call for different next
  actions, and telling a driver the first when the second is true makes them stop looking. The empty
  state distinguishes them and offers to clear.
- **The sheet never opens while DRIVING** (Forbidden #11 — no keyboard at speed). Filters set while
  stopped keep narrowing the corridor, which is the entire reason they persist.

## 3. The halal problem, and how it was solved

This is the part worth re-reading before touching any of it.

`halal_disclosure` is **free text** — "no halal claim", "we source from a halal butcher". Filtering that
text would have meant the platform **parsing a cook's sentence to decide who counts as halal**, which is
the platform making a halal claim. §23 had already settled that it does not: *"the vendor's own words,
verbatim — we make no halal claim of our own."*

So the cook answers a **closed** question as well as the open one. `halal_claim`, three rungs:

| Rung | Means exactly |
|---|---|
| `not_claimed` | the vendor does not claim halal. A complete, honest answer. |
| `self_declared` | the **vendor** says halal. Nobody has checked. |
| `certified` | an approved `halal_cert` document is on file. |

Four properties hold this together:

1. **The label always names who is speaking.** The chip and the sheet read "Vendor says halal", never a
   bare "Halal". A test asserts the string "Halal" alone never appears as a chip.
2. **The free-text sentence is still shown verbatim**, beneath the rung.
3. **`certified` is not self-awardable.** It requires an approved certificate; an unsupported claim is
   **downgraded to `self_declared` rather than refused**, because "vendor says halal" is still true and
   refusing would leave an honest cook unable to say anything at all.
4. **The portal offers only rungs the server will honour**, so the control never promises something
   taken back on save. Unavailable rungs are shown disabled rather than hidden — hiding `certified`
   would leave a cook wondering how anyone reaches it.

The filter sheet states plainly: *"This is what each cook says about their own food. We do not check it
ourselves."*

### One more: language chips are labelled in their own language

"ਪੰਜਾਬੀ", not "Punjabi" — identical across all six catalogues, deliberately. Someone scanning for a cook
who speaks their language is looking for their own script, whatever language the app happens to be in.
Translating those six keys would make the chip harder to find for exactly the person it exists for.

## 4. Also fixed this session (reported from the browser)

**`/auth/register` 409 said the wrong thing.** The vendor join route has one error handler across three
steps, and a 409 does not mean the same thing at each: at the **account** step it means that email
already has an account; at the **business** step it means Q-5, a vendor with these details already
exists. Every 409 was mapped to the second.

It never even reached that branch — `api.js` signals this case as the *message* `"email_taken"` rather
than a status, so the check fell through to a generic "that did not work", the least useful of the three
possible answers.

Both shapes are now checked, the step decides the wording, and because the fix is one tap the screen
**offers** it rather than describing it: a Sign in button carrying the typed email across. The message
was then corrected a second time — it had reused the driver app's `auth.error_taken`, which ends "Log in
instead" while sitting above a "Sign in" button. It now states the fact and lets the button carry the
action; a test asserts the message contains neither verb.

## 5. Verified live

Three cooks in one metro, then a driver searching:

```
Ana's Tamales    es/en   not_claimed     Tamales
Yusuf Kitchen    so/en   self_declared   Sambusa
Gurpreet Dhaba   pa/en   not_claimed     Samosa

no filter                 -> all three
q=samosa                  -> Gurpreet
q=SAMB (partial, any case)-> Yusuf
speaks Punjabi            -> Gurpreet
halal                     -> Yusuf
halal + speaks Somali     -> Yusuf
halal + speaks Punjabi    -> nobody   (correctly)
q=sushi                   -> nobody   (correctly)
```

**A note on how this was verified.** My first two attempts used a throwaway shell script that silently
picked facilities outside the search box and tripped the Q-5 duplicate-name guard, so everything came
back empty. That was the script, not the product. I rewrote the check as a Python script inside the
container rather than keep debugging shell — worth remembering, because a smoke script that fails
*quietly* is worse than no smoke script.

---

## 6. Where the platform stands

### Foundation F1–F15 — all present

| | LOC | | LOC |
|---|---|---|---|
| f01_identity | 1,046 | f09_ai_gateway | 702 |
| f02_facility | 1,308 | f10_crowd | 540 |
| f03_location | 481 | f11_map | 310 |
| f04_evidence | 537 | f12_offline | 128 |
| f05_load | 412 | f13_flags | 269 |
| f06_documents | 320 | f14_admin | 508 |
| f07_ledger | 479 | f15_localization | 226 |
| f08_notifications | 753 | | |

F11 and F12 own no tables by design (F11 is a schema-less serving layer; F12 is the offline seam).

### Modules M1–M13

| | LOC | Note |
|---|---|---|
| m01_map | 393 | + weigh-station layer (E3.1) |
| m02–m12 | 304–575 each | built to their DoD |
| **m13_vendor** | **3,122** | by far the largest — FR1–FR8, portal, menu, moderation, filters |

M1, M8 and M11 own no schema (composition-only over foundation).

### Portals (design-prd §18)

| Portal | Route | State |
|---|---|---|
| Admin console | `/admin/*` | 8 sections, rail (§23 E-D4) |
| Vendor portal | `/vendor-portal/*` | 6 sections + public join door |
| Fleet workspace | `/fleet` | single surface |
| Property owner | `/owner` | single surface |
| Public scorecard | `/scorecard` | unauthenticated |

## 7. Exact next task — recommendation

**Founding-vendor onboarding.** Standing recommendation since HANDOFF-072, and every excuse is now
gone: the cook can sign themselves up at `/vendor-portal/join`, build a menu, publish a week, and be
found by a driver searching for their dish, their language or their halal answer. That is the first real
data this platform will hold, and every further decision about the vendor network is currently being
made on assumptions about it.

**The obvious next slice after that:** the **service-center claim flow (FR7)** is the last endpoint set
with no UI. `/vendor/claims` exists and is uncalled, exactly as `/vendor/appearances` was before
HANDOFF-077. It was outside two approved scopes in a row; it should stop being.

**Alternatives:** the four remaining weigh-station states (KS, KY, MI, OH — need a fresh Geofabrik
download); §17 Q9 truck routing, still the largest open product decision.

## 8. Blockers

- **No git remote — six sessions running.** Ten commits sit locally on `main`. Add one and I'll push.
- **`merge_facilities` may leave the survivor's attributes stale.** Carried from HANDOFF-076 §5: the
  repair script calls `_recompute_canonical` itself, which means the admin console's own facility merge
  (decision 7) probably does not. **Worth checking before relying on it.** Not fixed because it touches
  the console's merge path and deserves its own change.
- **A vendor cannot delete their own listing or account.** Consistent with §17 Q16 (no hard delete), but
  self-serve signup makes self-serve *exit* a fair expectation. Worth deciding now that anyone can sign
  up, rather than after the first person asks.
- **Nothing rate-limits vendor registration.** Open signup with the tier ladder as the gate is the
  approved posture, but one account currently equals one vendor with no cooldown. If abuse appears the
  fix is a rate limit, not a relaxation of the ladder.
- **`categories` is collected and unused.** The portal edits it; nothing on the driver side reads it. It
  would hit the same free-text problem halal had, so a cuisine filter needs the same structured
  treatment before it can exist.
- **One OSM false positive, known:** a `weighbridge` named "Tractor Pull Weigh Scale". One in 103; no tag
  rule would catch it.

## 9. Open questions (PRD §17)

**Still open:** Q1 claim-recovery rate · Q2 collection partner · Q3 fuel payment partner · Q4 commercial
fuel-price feed · Q5 marketplace damage insurance · Q7 points redemption calibration · Q8 TPIMS
per-state survey · **Q9 truck routing (largest)** · Q13 Phase B trigger · **Q15 deactivation *conduct
policy*** (mechanism built, policy absent — using it without one is how support becomes arbitrary) ·
**Q16 hard delete / retention** · Q6 trademark + domain clearance.

**Resolved recently:** Q10 promotion economics (free, labelled slots) · Q11 property attestation
(self-attestation suffices, backed by an actionable report reason) · Q12 service-center taxonomy
(attributes, not kinds) · Q14 moderation integrity · Q15 deactivation mechanism.

## 10. Working rules (unchanged — non-negotiable)

Docker-only (dev = CI parity) · **local commits only, NEVER push** (no remote configured) · **plan
first**, owner approval, then code · **tests with every change** · live pulls never in CI (fixtures drive
tests) · **AI-CONTEXT comments only**, no other code comments · import-linter authoritative on
boundaries · **design-prd governs ALL UI** (LAW 0 mobile-first for the driver app, §18 for portals,
tokens only, six locales + pseudo) · §22.2 never improvises a token, component pattern, navigation
structure or notification class · session ends by writing the next HANDOFF.

Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

`test_phase_a_law.py` is green and its only edit remains the `menu_item` allowlist entry with its
recorded reasoning. **Phase A holds: no order, basket, total, checkout or billing column anywhere.**

## 11. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-078 — food search + consolidated platform state
3444208 Food search: the §11.3 filters sheet, and a halal claim the platform doesn't make
351ee06 Vendor join: state the fact, let the button carry the action
ebe419c Vendor join: a 409 means two different things, and it was saying the wrong one
```

## 12. Key files touched

```
M13      api/app/modules/m13_vendor/domain/enums.py (HalalClaim)
         .../domain/models.py (Vendor.halal_claim)
         .../domain/service.py (apply_filters, allowed_halal_claim, filter args on
         appearances_in_bbox + corridor_vendors) · public.py
API      api/app/api/m13_vendor.py (q/language/halal params; halal_claim on the
         entry and the sheet)
         api/app/api/vendor_portal.py (halal_claim + halal_claims_available)
MIGRATION 0045_m13_halal_claim
TESTS    api/tests/api/test_food_search_api.py (NEW, 19 tests)
UI       ui/src/core/components/MoreFiltersSheet.vue (NEW — the §11.3 sheet)
         ui/src/surfaces/MapSurface.vue (chip, persistence, two empty states,
         DRIVING lockout)
         ui/src/core/components/VendorSheet.vue (the rung, above the words)
         ui/src/surfaces/vendor/VendorProfile.vue (the closed question)
         ui/src/surfaces/vendor/VendorJoinSurface.vue (the 409 fix)
         ui/src/core/api.js (withFilters) · ui/src/core/i18n/*.json (22 keys ×6)
         ui/test/food-filters.test.js (NEW, 15 tests) · vendor-portal.test.js
DOCS     design-prd.md §23 ×3 · HANDOFF-078.md · HANDOFF.md
```

## 13. Ports / env

**No port or env changes.** LOCKED: postgres **5438** · api **8008** · ui **9008**. Migration 0045
applied. No new F13 flags — food filters ride the existing `m13_vendor` flag.

Operational note, carried forward and still true: `make ci` leaves Postgres running (its `compose run`
starts dependencies), so `make up` straight afterwards fails preflight. **`make down && make up`** is the
sequence.
