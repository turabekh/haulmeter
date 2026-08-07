# KICKOFF — the loading state, and the end of the fixtures

**Read first, in order:** `docs/handoffs/HANDOFF.md` (latest) · `docs/trucker-platform-prd.md` v1.0 ·
`docs/trucker-platform-prd-v2-amendment.md` (wins on conflict) · `docs/design-prd.md` ·
`S23-PROPOSAL-loading-state.md`.

**HARD PRECONDITION.** This session may not begin until the §23 proposal is **approved and logged**.
A skeleton is a §22.2 component pattern. If the entry is not in the log, stop and say so — do not
compose one and log it afterwards.

**Plan first.** Written plan, owner approval, then code. Nine working rules unchanged.

**What this session fixes:** UI audit U-06, U-09, U-10, U-11 — three of the eight criticals across
both audits. Every one is the same defect: **the product shows a driver something it does not know.**

---

## The order is the requirement

Do not reorder these. Removing fixtures before the loading state exists leaves a blank screen on
every cold start, which trades a §11.7 violation for a §8 one.

1. Skeleton primitive
2. Four-state model in `MapSurface` **only**, proven
3. The remaining five surfaces
4. Delete the fixtures
5. The burn-down test

If the session runs short, **stop after step 3 with the map correct and the other five untouched.**
Five surfaces half-converted is worse than one converted and five unchanged, because a half-converted
surface still has a fixture and now also has a skeleton that never shows.

---

## Step 1 — the skeleton primitive

Per the approved entry: **static, no animation.** §6.4 forbids looping ambient motion and The Meter
is the one living element per screen. If you find yourself reaching for a shimmer gradient, that is
the moment to stop and re-read the entry.

Three shapes — `SkeletonCard`, `SkeletonRow`, `SkeletonPin` — each taking a `count`. Composed from
`--ink-1`, `--line-1`, `--r-card` / `--r-control` / `--r-pill`, `--s-*`.

**Nothing may be added to `tokens.scss`.** If you believe a value is missing, STOP per §22 and put it
in the handoff. A hardcoded fallback hex is still a hardcoded colour — §23 entry 1197 caught exactly
that (`var(--on-accent, #fff)`) and it is the same mistake wearing a token's clothes.

**Delay before showing.** A skeleton that flashes is worse than a brief blank. ~200 ms, one shared
constant, not six copies.

**No skeleton while DRIVING.** The surface withdraws (SM-3) and says so with the existing
`driving.paused` line. A skeleton at speed is a reason to keep looking at a screen.

Register all three in the layout harness in **this commit** (v2.0 acceptance #3), with `ready`
selectors. A skeleton the harness cannot render is a skeleton that ships unmeasured at 360 dp.

---

## Step 2 — `MapSurface` first, and prove it

The map is chosen deliberately: it carries the **worst** instance (U-10 fires on every cold start,
not only on failure) and the **hardest** shape (clusters, presets, viewport refetch, abort on
supersede). If the model survives the map it survives the rest.

Replace:

```js
const livePins = ref(null);
const rawPins = computed(() => livePins.value ?? SAMPLE_PINS.filter(...));
```

with an explicit four-state model:

| State | Renders | Law |
|---|---|---|
| `loading` | `SkeletonPin` × expected count | §8 |
| `loaded` + pins | the pins | — |
| `loaded` + none | the honest empty line that **already exists** | §15.3 |
| `failed` | inline, specific, actionable — never data | §15.4 |

**Two traps specific to this surface.**

`AbortError` is **not** a failure. `loadOverlay` already returns early on it to keep the current pins
while a newer viewport is in flight. Preserve that exactly — an aborted fetch must not flip the
surface to `loading` or `failed`, or every pan flashes.

`serviceEmpty` and `foodEmpty` **already exist and are correct.** The comment above them is right —
*"'None mapped here yet' is a true sentence; a blank map is not."* They have simply been unreachable,
because `rawPins` guaranteed pins. **Do not rewrite them.** Removing the fixture is what makes them
fire; that is the whole fix.

**Prove it before moving on:** throttle the network in DevTools, cold-load the map, and confirm you
see skeleton pins and never a fabricated truck stop. Put a screenshot in the handoff. This is the
defect a driver could act on — it deserves an observation, not a passing test.

---

## Step 3 — the remaining five

Same model, no new thinking. In this order:

| Surface | Fixture | Note |
|---|---|---|
| `DocsSurface` | `SAMPLE_WALLET` | **highest driver risk.** M5's purpose is producing a credential at a roadside. A fabricated CDL is the §23 document entry's own worst case. |
| `MoneySurface` | `SAMPLE_OWED`, `SAMPLE_EARNINGS` | `ddd_cents` is the North Star. Never render a fabricated one. |
| `AuditSurface` | `sampleAudit()` | Not an empty state — a **result** the driver asked for. `failed` must say so plainly. |
| `FacilityProfileSurface` | `sampleProfile`, `sampleFacilityIntel`, `sampleQuestions` | three fetches, three independent states |
| `FleetWorkspaceSurface` | `SAMPLE_FLEET` | already has `view = ref("loading")` — align it, do not bolt a second model beside it |

**Every `catch` in this list is currently bare** and cannot tell offline from a 401 or a 500. Split
them: a network throw is offline; a non-ok response is failed. §15.4 wants an error a driver can act
on, and "you're offline" and "we couldn't load that" call for different next actions.

---

## Step 4 — delete, do not orphan

Remove the fixtures from `src/core/fixtures.js` **entirely**. §23 entry 81's reasoning is binding
here:

> removed rather than left unused: an exported placeholder is one import away from being back on the
> screen a driver cannot verify

If the owner answered the proposal's open question with "`/dev` keeps some," move those behind the
dev index and make the step-5 assertion path-based. Otherwise delete all of them and let `make seed`
be how `/dev` demonstrates.

---

## Step 5 — the burn-down test

Extend `ui/test/corridor.test.js` — the precedent already lives there — or add a sibling:

```js
it("ships no driver-facing fixture at all", () => {
  const src = read("src/core/fixtures.js");
  expect(src).not.toMatch(/^export (const|function) (SAMPLE_|sample[A-Z])/m);
});
```

**Write this test first, in step 1, and watch it fail.** It is the burn-down for steps 3–4 and it is
the thing that stops fixture number eleven appearing in six months. A guard nobody has watched fail
is the same species as the harness that could not fail (§23 entry 1197).

---

## Session Definition of Done

- [ ] §23 entry approved and in the log **before** any code
- [ ] Three skeleton shapes, static, zero animation, zero new tokens
- [ ] All three registered in the layout harness **in this commit**, with `ready` selectors
- [ ] `MapSurface` on the four-state model; `AbortError` still preserves current pins
- [ ] Throttled cold-load screenshot in the handoff — skeleton pins, no fabricated facility
- [ ] Five remaining surfaces converted, or explicitly deferred with the map left correct
- [ ] Bare `catch` blocks split into offline versus failed
- [ ] `src/core/fixtures.js` carries no driver-facing export
- [ ] Burn-down test green, and its failure observed before it went green
- [ ] `make ci` green: pytest · vitest · layout harness · import-linter 30/30 · ruff
- [ ] `docs/handoffs/HANDOFF-<n>.md` written

## What this session must NOT do

- Add a token, a colour, a spacing value, or a second component pattern
- Animate anything
- Rewrite `serviceEmpty` / `foodEmpty` — they are correct and were merely unreachable
- Touch The Meter's resting state (§9, §23 entry 52)
- Reorder, restyle or restructure any surface beyond swapping the state model
- Start the comprehension rework. WATCH.md runs **after** this, or it measures a driver reacting to
  invented data.

## Why this session matters more than its size suggests

Six of the eight criticals across both audits are one sentence: **the product asserts something it
does not know.** This session closes three of them, and it closes the ones a driver acts on — a lot
they drive to that is not there, a credential they show an officer that is not theirs, a figure they
take to a broker that was never real.

The standing warning applies with unusual force here, because every one of these was green:

> A suite proves the code does what it was written to do. It cannot tell you the code was written to
> do the wrong thing, and it cannot see the thing nobody built at all.

**Throttle the network and look at the screen.**
