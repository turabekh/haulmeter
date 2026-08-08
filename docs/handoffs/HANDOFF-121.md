# HANDOFF-121 — the loading state exists, and the fixtures are gone

> **Stack UP · thirty-seven commits UNPUSHED · nothing deployed.** haulmeter.online still
> serves 112's code.
>
> The owner approved `S23-PROPOSAL-loading-state.md`, PROPOSED since 2026-08-07, and said
> "do the loading-state work". It is **design-prd §23 entry 131**, and the four-state rule
> is on the **§22.3 DoD**. **Five findings closed — U-06, U-09, U-10 (criticals), U-11 and
> U-12** — which is every finding that decision was blocking.
>
> **Open findings 7 → 5. Criticals: 3 closed, 1 open (F-02), 1 blocked (F-01). Every High
> in both audits is now closed.**
>
> **Two things are worth reading over the rest: §4, where looking at a screenshot found a
> defect that six automated checks had passed over; and §5, where removing the fixtures
> revealed that nine unit tests and four harness states had been measuring them.**

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **thirty-seven** commits ahead of `origin/main` — 120's thirty-five plus this session's two |
| `origin/main` | `113327e`, still **not re-verified**. `git fetch` fails here: *"could not read Username for 'https://github.com'"*. The ahead-count is arithmetic. **Re-fetch before pushing** |
| Gates | **pytest 1538 · vitest 745 (39 files) · layout 271 · import-linter 30/30 · ruff clean** — all five measured on the final tree |
| Migrations | `0065_f14_job_schedule` (head) — unchanged, no migration this session |
| Working tree | clean |
| Local stack | **UP.** Seven containers, `/health` 200, UI 200 |
| Dev data | Tampa `27.9506,-82.4572` intact, four DEV facilities at 89–125 m |
| Email | **dev still points at live Gmail.** A send from dev is a real send |
| Deploy | **not run.** The box has none of 113–121 |

Baseline was vitest 714 / layout 257. **vitest +31, layout +14** (three skeleton states ×
four variants, plus the two observation tests).

**The stack was DOWN at session start despite 120 signing off "UP"** — no containers at
all, not stopped, absent. Something removed them after 120 ended. The named volumes and
all four images survived, so nothing was lost, and `make up` came back first try with no
registry retry. Worth knowing only because 120's header says otherwise.

## 2. What was closed, and what the decision actually cost

**All five were one defect.** Every fetching surface had TWO states — data and no-data — so
a null response had to mean one of them, and the codebase chose *data*:

```js
const rawPins = computed(() => livePins.value ?? SAMPLE_PINS.filter(...));
```

That is U-10, and it fired on **every cold open**, not only offline: the first thing a
driver saw, every single time, was fabricated truck stops they could route to. Five other
surfaces did the same on failure — a CDL that is not theirs, Driver Dollars Delivered they
have not earned, a settlement discrepancy no carrier owes, lots to sleep in that are not
there.

**The primitive.** `SkeletonCard` / `SkeletonRow` / `SkeletonPin`, static, composed only
from existing tokens — `tokens.scss` is untouched. It does not animate: §6.4 forbids
looping ambient motion and a shimmer would compete with The Meter for the one living
element on a screen, so `prefers-reduced-motion` needs no branch because there is no
motion to reduce. Asserted at the source, because "add a subtle shimmer" is the likeliest
edit anyone will ever make to these files.

**The 200 ms delay and the DRIVING guard live in ONE shared gate** (`core/skeleton.js`),
not at each call site. Both are easy to state and easy to forget in a copy-paste, and a
surface cannot opt out of either.

**The Meter gains no loading state**, which was the entry's one hard prohibition (§9,
entry 52). Money replaces the **card** until `ddd_cents` is known, so The Meter renders
once, with a real number. Rendering it against `0` would put a confident **$0.00 in Mono**
over the driver's month, which is worse than either alternative.

**Ten importers, not seven.** The proposal's two open questions were settled in the entry
rather than deferred: **the §18 portals lose their fixtures too**, because entry 81's
argument is about the *drawer*, not the screen — and this file proved it, because
`SAMPLE_FUEL_ANALYTICS` was exported and imported by **nothing**, a fixture already
halfway back. **`/dev` keeps none.**

**`fixtures.js` is kept as a tombstone.** Deleting the file would have been tidier and
worse: the next person needing placeholder data reaches for that drawer, and the reasoning
has to be there when they open it. It now lists what it held, why it went, and the five
things to do instead.

## 3. Two decisions inside the work that are not obvious

**`serviceEmpty` and `foodEmpty` were NOT rewritten.** The kickoff forbade it and was
right: their expressions were always correct and merely unreachable, because `rawPins`
guaranteed pins. But `preset === 'service' && pins.length === 0` is *equally true while a
fetch is in flight*, and telling a driver "None mapped here yet" before their request
comes back is the same false assertion in the other direction. So they are gated by
**chain position** — wrapped in `v-if="overlay === LoadState.LOADED"` — and their own
conditions are untouched. What was wrong was the state, not the condition.

**offline vs failed needed TWO signals, and one of them would have been wrong.** The
kickoff asked for the split. `apiGet` flips the shared `online` ref on a transport throw
and rethrows a 4xx/5xx untouched, so reading `online` looks sufficient — **but
`fetchOverlay` does not go through `apiGet`.** It calls `fetch` directly, never touches
`online`, and a dead zone on the map would therefore have reported a server error and sent
a driver looking for the wrong fix. A transport failure is now also identified at the
source, as a `TypeError`. Measured, not assumed.

## 4. The defect that six checks passed over, and how it was found

**This is the section to read.**

The kickoff says *"Throttle the network and look at the screen"* twice, and it is the
only reason this was caught.

`SkeletonPin` first filled with `--line-1`, matching the other two shapes. That is correct
on a **card** and wrong on a **map**: dark `--line-1` is `#2A3644` against a night basemap
of about the same value. So the observation was written, it **passed**, and the screenshot
showed **an empty map**. Six pucks were in the DOM, `visibility: visible`, with a correct
bounding rect at (32,168), counted by the layout harness — and invisible to a human.
`--ink-1` would have been worse (`#151C24`).

Everything green over it: 745 unit tests, 271 layout checks including three states whose
`ready` selector is `.skel__pin`, `token-discipline` (no literal — it is a token), and the
new "references only tokens that exist" check (it exists). **A colour can be a legitimate
token, correctly applied, and still be invisible where it is used**, and nothing in this
project could see that.

The fix is `--on-accent`, theme-invariant white, with the precedent it belongs to: §23
entry 130 recorded that invariance as load-bearing **for pins specifically**, because *"a
fill that darkened with the theme would make a stale pin read as a filled one."* It does
not collide with `.pin--stale`, which is a white puck with a **coloured** ring and a glyph;
this is a white puck with a neutral ring and nothing inside it.

**Guarded three ways, since no existing check could have caught it:** the fill token is
asserted to be `--on-accent`, both theme declarations are asserted to name the same
colour, and no status token may appear in the file. My first version of the second
assertion was wrong — it checked that the light mixin does *not* redeclare `--on-accent`,
and it does, with the identical value. It failed correctly and was rewritten to compare
values instead of asserting absence.

## 5. Removing the fixtures showed that thirteen checks had been measuring them

None of this was the fixtures. It is what the fixtures were hiding.

**Nine unit tests asserted on fixture data while naming an endpoint.**

- **Three Docs deep-link tests called `stubWallet()` and never `setToken`.** `fetchWallet`
  goes through `apiGet`, which throws `"no session"` **before** it calls fetch — so the
  stub was never consulted and every assertion landed on `SAMPLE_WALLET`. They passed for
  the wrong reason for as long as the fixture existed, and the fixture's ids happened to
  match the stub's.
- **Four more said `(fixture)` in their own titles**, including one whose `.pill` assertion
  read the fixture's two expiring documents against a stub whose `expiring` is empty.
- **Two portal tests were named "falls back to the fixture demo when unauthenticated"** and
  asserted on `$1,840.00` and `$396.00` — invented revenue. They were tests *of* the defect.

**And four harness states had been measuring an invented facility.** `facility`,
`facility-prompt-mute`, `sheet-ask`, `sheet-review` all went red, and their own comment
said why: *"deliberately renders from fixtures … the surface falls back to its fixtures
exactly as it does today."*

**The most useful of the four is `facility`, because it did NOT go red.** It had no `ready`
selector, so it kept passing while measuring §15.4's one-line error under the facility's
name. **A state with no `ready` cannot tell a screen from its own error message.** It has
one now (`.dwell__figure`).

## 6. Verified against the running system, not the suite

- **The throttled cold open, 4 s overlay, 360×800 dark:** 6 skeleton pucks, **0** real
  pins, no facility named — and no *"None mapped here yet"* either, which would have been
  a different lie. `docs/handoffs/assets/loading-map-360dp.png`.
- **Then the pins land:** skeleton count 0, the real pin present by `data-facility`.
  Asserted by attribute, not by name, because a loaded pin is a puck and its name only
  becomes page text when the card opens. `loaded-map-360dp.png`.
- **The failed overlay:** *"Could not load the places on this map."* + **Try again**, 0
  pins. `failed-map-360dp.png`.
- **`money.empty` was translated into all six locales and rendered by NOTHING** — a driver
  owed nothing got a bare heading over an empty list. Found by applying the four-state
  rule, which is that rule earning its place on the DoD. `system.loading` is the same
  shape: six locales, zero consumers, still unused (the skeletons carry no text).
- **The harness's `hang` guard was proved able to fail**, not assumed: pointing it at a
  path that does not match turns all four `map-loading` variants red with the right
  diagnosis.

## 7. Sabotage — nine restorations, every one caught

| Fix | Sabotage result |
|---|---|
| U-10 `livePins ?? SAMPLE_PINS` restored | **2 fail** |
| `AbortError` treated as a failure | 1 fail |
| empty lines speak before the overlay loaded | 2 fail |
| offline collapsed into server error | 1 fail |
| the 200 ms delay removed | 3 fail |
| the skeleton renders while DRIVING | 3 fail |
| `SkeletonPin` back to the invisible `--line-1` | 1 fail |
| harness `hang` pointed at a non-matching path | 4 fail (the layout states) |
| the burn-down, before any of it was true | 3 fail |

**No `0 fail` row.** The burn-down was written first and watched failing, and its third
assertion named all ten importers on the way down.

## 8. Exact next task

### 8.1 The owner decisions — three left, down from eight

119 §5.1's list is **half cleared**: items 5–8 were the loading-state proposal and are
done. What remains:

| | |
|---|---|
| **`--marker-500` at 2.04:1 in dark** | against a 3:1 floor. The "Some" parking pin and the **OPEN** weigh-station pin. Pinned in `contrast.test.js` so it cannot drift; a palette colour is §22.2 never-improvise. **§4 above is an argument for taking this seriously** — that was also a token that was legitimate and still wrong on this exact surface |
| **Two portal touch targets (40 dp)** | clearing it closes **U-04** and **U-05**'s remainders, and lets `FleetWorkspaceSurface` and `OwnerPortalSurface` into the harness |
| **`.cluster` hit area 36 dp** | below §6.5's 48 and below §11.2's 44 dp map exemption |

### 8.2 What is left in the queue

| | |
|---|---|
| **F-02 + F-12** | the `default_on` vs `enabled` decision. Must not be split, or M3's detention clock goes silent. **The last open critical** |
| **F-01** | one command on the box. No box credential here. Still the only *blocked* critical |
| **F-19** | no merge-review queue — needs a judgement about intended behaviour |
| **F-25** | the profit model assumes the product does not work — same |
| **F-27** | fleet N+1. Latent, and inherits F-23's `owed` definition |
| **U-04, U-05** | **PARTIAL**, both waiting on the portal touch-target decision above |

### 8.3 Still open and untouched

The **handset background-sensor test** (v2.0 DoD #8), **ON_SITE has still not been walked
in a browser** (117 §7), and **push, then decide on deploying**. A deploy needs production
`SMTP_*` on the VM, which is F-01's question again.

## 9. Things a later session will trip over

1. **`ui/src/core/fixtures.js` is deliberately empty and says so.** Do not add to it. The
   five alternatives are listed in the file.
2. **A new fetching surface must declare all four states** — it is on the §22.3 DoD now.
   `core/load-state.js` has `LoadState`, `Failure` and `failureOf(err)`.
3. **`failureOf` reads two signals** and the reason is in its own comment: `apiGet` callers
   flip `online`, direct-`fetch` callers (like `fetchOverlay`) do not.
4. **Never put a skeleton on The Meter** (§9, entry 52, entry 131). Replace the card.
5. **A layout state that holds a request open sets `hang: [fragments]`** and gets no
   networkidle wait. It MUST carry a `ready` selector naming the skeleton class.
6. **A layout state without `ready` cannot distinguish a screen from its error message.**
   `facility` proved it by passing.
7. **A stub returning `{}` where the endpoint returns `null` can crash a render.**
   `/vendors/service-center/{id}` returns null for an unclaimed facility;
   `serviceCenter.services.length` on a truthy `{}` throws and collapses every branch
   below it. It cost a debugging round here and is written into both the unit stub and the
   harness mock.
8. **`observe-loading.spec.js` runs inside `make ui-layout`** — deliberately, because an
   observation nobody re-runs decays into a screenshot in an old handoff. Its screenshots
   are opt-in behind `OBSERVE_SHOTS=1` so a sweep leaves the tree clean.
9. **`--on-accent` is the only fill that works over a basemap in both themes.** §4.
10. **`money.empty` is rendered now**; `system.loading` is still used by nothing, correctly
    — the skeletons are `aria-hidden` and carry no text.

## 10. Restarting

**`make ui-layout` is now 271 checks and ~2.7 min.** It runs ALONE.
`make ui-layout-only STATE=map-loading` measures one state in ~45 s.

```
make up                              # preflight, then the full stack
make seed-where                      # the Tampa origin — paste into Sensors
make test                            # 1538 pytest + 745 vitest — do NOT pipe it
make lint                            # ruff + import-linter (30 contracts)
make ui-layout                       # 271 checks, ~2.7 min, runs ALONE
make down
```

To refresh the observation screenshots:

```
docker compose -f infra/docker-compose.yml --env-file infra/.env run --rm \
  --entrypoint sh -v "$PWD/docs/handoffs:/repo-docs" ui \
  -c "npx --yes playwright install --with-deps chromium; \
      OBSERVE_SHOTS=1 npx playwright test layout/observe-loading.spec.js --workers=1"
```

**Do not run pytest while `make test` is running** — same database, phantom failures.

`infra/.env` carries the live Gmail block and is gitignored. **A send from dev is a real
send.**

No migration this session. Nothing is waiting on a background job, an ingest, or a queue.
