# KICKOFF — UI comprehension fixes (law violations only)

**Read first, in order:** `docs/handoffs/HANDOFF.md` (latest) · `docs/trucker-platform-prd.md` v1.0 ·
`docs/trucker-platform-prd-v2-amendment.md` (wins on conflict) · `docs/design-prd.md`.

**Scope discipline for this session.** Five items. Every one is a violation of a written law, not a
design opinion. **No redesign, no reordering, no new components, no navigation change.** The
comprehension rework waits on WATCH.md evidence and owner decision D4 — this session removes the
defects that are wrong regardless of what a driver tells us.

If you find yourself improving something not on this list, stop and put it in the handoff instead.

**Plan first.** Present a written plan and wait for approval before any code. Nine working rules
apply unchanged.

---

## Why these five and not a rework

A10 requirement 3 says *"Do not specify the document-portal work yet. 'Streamlined' is not
actionable."* That still holds. These five are actionable because each names a law and a measurable
outcome. They are also, independently, things that make screens harder to follow — so shipping them
is not a detour from the comprehension work, it is the part of it that does not need a driver.

Source: `UI-AUDIT-2026-08-07.md` (U-01…U-05).

---

## Item 1 — Load tab worst-case stack is unmeasured · `[U-04-adjacent]` · **do this first**

**Law:** PRD v2.0 §8 acceptance criterion 3 — every surface state registered in the layout harness.

`LoadSurface.vue` renders up to six independent blocks, each behind its own `v-if`: the
packet-waiting card, the Meter card, the location-degraded banner, the hint line, the context row,
and the evidence checklist. The harness registers `load`, `load-live`, `load-packet-ready` and
`load-checklist-capture` as **separate** states. **No entry combines them.**

A driver with an active stop, a packet waiting, and location permission denied gets three cards above
the Meter — the signature element — at 360 × 800. That configuration has never been rendered in the
harness.

**Do:**
1. Add a harness state `load-worst-case`: active stop + waiting packet + `locationDenied` + evidence
   checklist populated. Give it a `ready` selector proving all three cards rendered — a state that
   silently loses one of them is a second copy of `load-live`.
2. Run it at 360 × 800 and at +40% type, six locales.
3. **Report what you measure. Do not fix the layout in this session.** If the Meter falls below the
   fold, that is a finding for the owner and a candidate for the WATCH.md rework — not a
   reordering to improvise now. §22.2 covers layout hierarchy.

**Done when:** the state exists, is green or is red with a measurement, and the result is in the
handoff.

---

## Item 2 — `MapCanvas.vue` draws outside the token system · `[U-01]`

**Law:** design-prd §6 — tokens only. §23 entry 45 closed light theme on the argument that *"contrast
is verified from tokens in CI across both themes."* These six literals are the exception that
argument does not cover.

Six hardcoded colours in `ui/src/core/components/MapCanvas.vue`:

| Selector | Literal |
|---|---|
| `.pin__puck` | `color: #fff` · `border: 2px solid #fff` · `box-shadow: … rgba(0,0,0,0.35)` |
| `.pin--stale .pin__puck` | `background: #fff` |
| `.cluster` | `color: #fff` · `border: 2px solid #fff` · `box-shadow: … rgba(0,0,0,0.35)` |

Plus a scrim at `rgba(0, 0, 0, 0.4)` elsewhere in core.

**Why it is a comprehension bug, not a tidiness one.** These are **theme-invariant**. `--pin-color`
changes between themes; `#fff` does not. In light theme the pin's white ring sits on a light map and
loses its outline — and `.pin--stale` becomes a **white puck with a white border**, which is the
affordance §11.7 relies on to tell a driver a reading is old. A stale pin that looks fresh is the
honesty law failing silently.

**Do:**
1. Propose token names and both theme values in the plan **before** adding them. New tokens are a
   §22.2 never-improvise category — this needs a §23 entry. Expect two: a pin foreground and a pin
   elevation shadow. If you can compose from existing tokens instead, do that and log it as
   composition.
2. Replace all seven literals.
3. Verify the CI contrast check now covers them — that is the point of the change.
4. Screenshot `.pin--stale` in **both** themes at 360 dp and put both in the handoff. The bug is
   invisible in dark theme, so a dark-only screenshot proves nothing.

**Done when:** zero colour literals in `ui/src/**` outside `tokens.scss`, contrast green in both
themes, §23 entry written, stale-pin screenshots in the handoff.

---

## Item 3 — English is reaching non-English drivers · `[U-03]`

**Law:** PRD v2.0 §8 acceptance criterion 5 — *"no English fallback reaches a driver."*

`ui/src/core/i18n.js`:

```js
function resolve(key, catalog) {
  if (Object.hasOwn(catalog, key)) return catalog[key];
  const fallback = messages[DEFAULT_LOCALE];
  if (Object.hasOwn(fallback, key)) return fallback[key];   // English, silently, in production
  if (UNDER_TEST) throw new Error(`i18n: no string for "${key}" in any locale...`);
  return key;
}
```

The guard fires only when a key is missing from **every** locale. Present-in-English,
missing-in-Somali returns English text with no signal. The file documents its own blind spot: *"~45
dynamic `t(\`ns.${...}\`)` families whose vocabularies live in Python"* — server-driven vocabularies
(facility kinds, service types, claim states, notification categories) that a JS completeness test
cannot enumerate. Those are exactly the strings a non-English driver meets on Map and Money.

This is the most severe comprehension defect in the app and it needs no research to justify.

**Do — in this order, and stop after step 2 if step 2 is large:**

1. **Make the fallback loud.** In dev mode, `console.warn` on every cross-locale fallback naming the
   key and the locale. Increment a counter. Surface the counter in the dev index (`/dev`). An
   invisible gap becomes a measurable one — that is the whole fix at this stage.
2. **Sweep the six catalogues against the live app.** Set locale to each of `es pa ru uz so` in turn,
   walk the five tab roots plus Load-live, and record every warning. Put the raw count per locale in
   the handoff. **This number is the finding.** Do not fix the strings yet — knowing the size comes
   first.
3. **Only if step 2 is small (<20 keys):** fill them. If it is large, stop and hand the owner the
   list. Machine-translating forty strings into Punjabi in a session is how a driver ends up reading
   something worse than English.

**Do not** remove the English fallback. A raw key reaching a driver (design-prd §12.5, Forbidden #7)
is worse than an English word.

**Done when:** the warning fires, the counter is visible at `/dev`, and a per-locale count is in the
handoff.

---

## Item 4 — Touch targets below the glove floor · `[U-05]`

**Law:** design-prd §6.5 — minimum target 48 × 48 dp. Written for a gloved hand in a bouncing cab.

| Element | Height | File | Verdict |
|---|---|---|---|
| `.filters-chip` | 40 px | `MapSurface.vue` | **violation — fix** |
| `.cluster` | 36 px | `MapCanvas.vue` | §11.2 sets pin hit areas at 44 dp — **measure, then ask** |
| (fleet control) | 40 px | `FleetWorkspaceSurface.vue` | web-first portal — **ask** |
| `.spot__price-in` | 40 px | `OwnerPortalSurface.vue` | web-first portal — **ask** |

**Do:**
1. Fix `.filters-chip` to 48 dp. Its own comment says *"the same pill the preset row uses — no new
   component pattern (§22.2)"* — **check the preset row first.** If it is also 40 dp, the violation is
   the shared pattern and fixing the pattern fixes both. Fixing only the chip would fork a component,
   which §22.2 forbids more strongly than the original defect.
2. Verify at 360 dp that a 48 dp preset row still scrolls horizontally without pushing the map below
   its minimum.
3. `.cluster`: measure the actual hit area (it may exceed the visual 36 px). Report; do not change.
4. The two portal controls: **do not change.** §6.5 grants no portal exemption in writing, but
   applying the glove floor to a desktop form is a design decision, not a fix. Put the question in
   the handoff for the owner.

**Done when:** the driver-facing chip and its shared pattern are ≥48 dp, the harness is green at 360
dp, and the three unresolved cases are questions in the handoff rather than silent changes.

---

## Item 5 — Session hygiene across drivers · `[U-02]`

**Law:** the code's own stated intent — *"a new driver never sees the last one's cached reads"* /
*"nor inherits their unsynced writes."*

`clearCache()` removes keys prefixed `longhaul.cache.`. Two keys lack the prefix and survive logout:

- `longhaul.active_stop` — the previous driver's active stop id
- `longhaul.active_fleet` — the previous driver's fleet id

A phone passed between team drivers is the normal case in this product. The active stop is what the
Load tab, The Meter and the arrival prompt anchor to.

**Do:** bring both keys under `CACHE_PREFIX` rather than adding two `removeItem` calls. The prefix
convention is what failed; adding exceptions to it leaves the next key exposed the same way.

**Test:** sign in as A, set an active stop, log out, sign in as B, assert the Load tab shows B's
empty state. Assert it against the *rendered* state, not against `localStorage` — the audit found
several places where a test asserted the mechanism instead of the outcome.

**Done when:** the round-trip test passes and no un-prefixed per-driver key remains in `api.js`.

---

## Session Definition of Done

- [ ] Plan presented and approved before any code
- [ ] Items 1–5 addressed, or explicitly deferred with a reason in the handoff
- [ ] `make ci` green: pytest · vitest · layout harness · import-linter 30/30 · ruff
- [ ] Layout harness gains `load-worst-case` with a real `ready` selector
- [ ] Zero colour literals in `ui/src/**` outside `tokens.scss`
- [ ] §23 entry written for any new token (Item 2)
- [ ] Per-locale fallback counts recorded in the handoff (Item 3)
- [ ] Both stale-pin screenshots — dark **and** light — in the handoff
- [ ] Open questions (cluster hit area, portal targets, Item 1 measurement) stated as questions, not
      resolved unilaterally
- [ ] `docs/handoffs/HANDOFF-<n>.md` written

## What this session must NOT do

- Reorder, restructure or restyle any surface
- Add, remove or rename a tab — A8 / D7 is an open owner decision
- Change any label a driver reads, beyond adding missing translations
- Introduce a component pattern, spacing value, or navigation structure (§22.2)
- Fix Item 1's finding. Item 1 measures. The fix belongs to the WATCH.md rework.

## The standing warning

Carried from PRD v2.0 §9, because four of these five were invisible to a green suite for months:

> A suite proves the code does what it was written to do. It cannot tell you the code was written to
> do the wrong thing, and it cannot see the thing nobody built at all.

Item 3 in particular cannot be closed by a passing test. `locale-completeness.test.js` is green today
and a Somali driver may still be reading English. **Set the locale and look at the screen.**
