# §23 PROPOSAL — the loading state

**Status:** **APPROVED 2026-08-08** by the owner, and **IMPLEMENTED in session 121** —
design-prd **§23 entry 131**, with the four-state rule added to the §22.3 DoD. U-06, U-09,
U-10, U-11 and U-12 are all closed. Both open questions below were settled in the entry:
the §18 portals lose their fixtures too, and `/dev` keeps none.

Kept as written, including the undercount the VERIFICATION section corrects, because what
the owner approved is part of the record.
**Category:** component pattern — a §22.2 never-improvise category.
**Blocks:** UI audit U-06, U-09, U-10, U-11 (three of eight criticals across both audits).
**Date raised:** 2026-08-07

---

## Why this is a proposal and not a fix

design-prd §8 has specified a loading state since v1.0:

> **Empty/loading:** skeletons mirror the real layout (no spinners for content); empty states = one
> line of what this is + one action to start (§15.3).

It has never been built. Measured across `ui/src/**`: **zero** skeleton components, and **two of
twenty-one** surfaces track loading at all.

The consequence is not cosmetic. A surface with two states — *data* and *no data* — must render
something the instant it mounts, before any fetch resolves. With no third state, `null` has to mean
one of the two, and the codebase chose *data*:

```js
const livePins = ref(null);
const rawPins = computed(() => livePins.value ?? SAMPLE_PINS.filter(...));
```

That is U-10: **every cold app open renders fabricated truck stops until `/map/overlay` returns.**
Five other surfaces do the same on failure, including the document wallet (a CDL that is not theirs)
and the Money tab (money the driver has not earned).

**So the fixtures cannot simply be deleted.** Removing them without a loading state trades a §11.7
violation for a §8 violation — a blank screen on every cold start. The loading state is the
prerequisite, and it is a component pattern, so §22.2 sends it here rather than to a session.

---

## The proposal

**A single static skeleton primitive, composed entirely from existing tokens, in three shapes.**

### It does not animate. That is the load-bearing decision.

§6.4 is explicit:

> Motion communicates state change only; **zero decorative animation, zero looping ambient motion.**
> The Meter's counting is the one living element per screen.

The industry-default skeleton is a looping shimmer. It is **forbidden twice over** — as looping
ambient motion, and because it would compete with The Meter for the one living element on a screen
where The Meter is the signature.

A static skeleton is also the right answer for this user, independently of the law. A driver glancing
at a phone in a bouncing cab does not benefit from a sweeping gradient; they benefit from shape
arriving before content, which a static block delivers and a shimmer only decorates.

Consequence worth stating: `prefers-reduced-motion` needs no branch here, because there is no motion
to reduce.

### Composition, not invention — no new token required

§6.3 says elevation is expressed by **surface step + hairline border**, not by shadow. A skeleton
block is therefore the existing card treatment with no content:

| Property | Token | Already used by |
|---|---|---|
| fill | `--ink-1` | every card (§8) |
| border | 1px `--line-1` | every card |
| radius (block) | `--r-card` | cards |
| radius (line) | `--r-control` | controls |
| radius (pill) | `--r-pill` | chips, pins |
| padding / gaps | `--s-2` … `--s-4` | everywhere |

**Nothing new is added to `tokens.scss`.** Per §22 this is a composition; the entry is required
because the *component pattern* is new, not because a token is.

### Three shapes, because the app has three layouts

Not a generic box — §8 says skeletons **mirror the real layout**, and a skeleton that does not match
what replaces it produces a visible jump, which is a state change communicated badly.

1. **`SkeletonCard`** — mirrors the §8 card: `--ink-1`, `--r-card`, hairline, 16 dp padding, a title
   line and a figure line. For Money, Load, Audit, Fleet.
2. **`SkeletonRow`** — mirrors a list row at ≥64 dp (§6.5): a leading square, two lines of unequal
   width. For Docs, Bookings, Packets, corridor entries.
3. **`SkeletonPin`** — a `--r-pill` puck at the §11.2 44 dp hit area, no badge, no status colour. For
   the map overlay.

Each takes a `count` prop so a surface renders the number of rows it expects, not a fixed three.

### Where it must NOT go

- **The Meter.** §9 and §23 entry 52 already specify the resting state — `--text-1`, no figure, no
  clock. The Meter at rest is not a loading state and must not gain one.
- **DRIVING.** A skeleton is a promise that content is coming, which is a reason to keep looking at a
  screen. At speed the surface withdraws (SM-3) and says so with the existing `driving.paused` line.
  No skeleton renders while DRIVING.
- **Anything under 200 ms.** A skeleton that flashes is worse than a brief blank. Render it only
  after a short delay, so a fast local response never shows one.

---

## What changes alongside it — the four-state rule

The proposal is not only a component. It is the state model the surfaces are missing.

Every surface that fetches must distinguish **four** states, and each has a law already written:

| State | What renders | Law |
|---|---|---|
| `loading` | the skeleton | §8 (this proposal) |
| `loaded` + data | the content | — |
| `loaded` + no data | one sentence of purpose + one action | §15.3 |
| `failed` | inline, specific, actionable | §15.4 |

The two that are conflated today are **`loading`** (missing entirely) and **`failed`** (currently
rendering fixtures). §15.4 already says what `failed` owes a driver — *"errors are inline, specific,
actionable; failed money-moving actions are always explicit and persistent until resolved"* — so no
new law is needed for it, only the state.

**"Can't reach the server" is a true sentence. A fixture is not.**

---

## Precedent this follows

`§23 entry 81 — the corridor is served, not invented` already made this exact call for one fixture,
deleted it rather than leaving it unused, and wrote a structural test to prevent its return:

> removed rather than left unused: **an exported placeholder is one import away from being back on
> the screen a driver cannot verify**

Nine fixtures remain in the same file, imported by five surfaces, including the same `MapSurface.vue`
that entry's test guards. This proposal is entry 81 applied to the rest — the reasoning is already
owner-approved, only the loading state was missing to make it actionable.

---

## What the owner is being asked to approve

1. **A new component pattern** (§22.2): a static skeleton primitive in three shapes, composed from
   existing tokens, no animation.
2. **The four-state rule** as a §22.3 DoD addition: every fetching surface declares all four states.
3. **The consequent deletion** of all driver-facing fixtures from `src/core/fixtures.js`.

## Open question for the owner

**Does `/dev` keep any fixtures?** The dev index legitimately needs demonstrable surfaces. If yes,
surviving fixtures must be unreachable from a driver route, and the burn-down test should assert by
*import path* rather than by symbol name. If no, `/dev` demonstrates against a seeded account and the
test is a simple name assertion. **Recommendation: no** — `make seed` already exists, and a fixture
that lives anywhere is one import from a driver's screen, which is entry 81's whole argument.

---

## If this is rejected

Say so explicitly rather than leaving it open, because the fixtures cannot be removed without it and
three criticals stay live. The alternative — a blank screen during load — is a knowing §8 violation
and would itself need an entry. There is no third option that keeps the fixtures and satisfies §11.7.

---
---

## VERIFICATION — session 119, 2026-08-08

*Appended by the agent before approval, not part of the owner's proposal. Every measurable claim
above was re-run against the tree, because approving a scope estimate that turns out to be half the
real size is how a session overruns.*

### Confirmed exactly

| Claim | Measured |
|---|---|
| Zero skeleton components | `grep -rli skeleton ui/src/` → no files |
| Two of twenty-one surfaces track loading | 21 surfaces; `loading` appears in **2** — `FleetWorkspaceSurface`, `StopPacketsSurface` |
| §8's skeleton sentence | verbatim in design-prd |
| §6.4's "zero decorative animation, zero looping ambient motion" | verbatim in design-prd |
| The U-10 fallback | `MapSurface.vue:352-354` — `if (livePins.value) return livePins.value;` then filters `SAMPLE_PINS` |
| Entry 81's precedent and its quote | verbatim in `ui/test/corridor.test.js:45-51`, which asserts `SAMPLE_CORRIDOR` is undefined **and** absent from the file |

### One claim is materially understated

> *"Nine fixtures remain in the same file, imported by five surfaces"*

**Measured: sixteen exports, imported by ten files.**

```
exports in ui/src/core/fixtures.js ......... 16
importing files ............................ 10
  driver-facing ............................  7   Money, More, Audit, Map, Docs,
                                                  FacilityProfile, SleepSheet (component)
  §18 portals ..............................  3   OwnerPortal, FleetWorkspace, PublicScorecard
```

Item 3 is therefore roughly **twice** the size it reads as, and it contains a scope question the
proposal does not settle: **it says "all driver-facing fixtures", and three of the ten importers are
§18 web-first portals.** A portal rendering `SAMPLE_OWNER` is not a driver reading a CDL that is not
theirs, so §11.7's driver-facing argument does not reach it on its own terms — but leaving them is
exactly the "one import away" condition entry 81 was written about.

**This does not weaken the proposal.** Nothing in the reasoning depends on the count, and the
direction of the error is the safe one — the case for a loading state is stronger with sixteen
fixtures than with nine. It changes the *session plan*, not the decision.

### Recommendation on the open question

Agreed: **no fixtures for `/dev`.** `/dev` already has one-click dev sign-in against a real seeded
account (`DevIndexSurface.vue`), so it needs no invented data, and a name-assertion test is the
simpler guard. Worth noting that this makes the portal question above the *only* remaining ambiguity
in item 3 — settle both together.
