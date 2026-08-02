# HANDOFF-114 — the food half switched off for real, and what looking at the screen found

> Second half of the session that produced 113. **113 is A6** (the M13 flag split and the
> claimed-shop card) and is still accurate — read it for that work. This document covers
> everything after it, which turned out to be larger than the feature that started it.
>
> **Stack UP · one commit UNPUSHED (`f272c4a`) · nothing deployed.** haulmeter.online
> still serves 112's code, with one production CONFIG change made this session (§3).
>
> The owner asked for the food half to go. Executing that decision uncovered, in order:
> **the food flag was ON in production over demo data**; **`preset=food` had been
> answering 500 since the day the chip shipped**; **the chip row never consulted a flag
> at all**; and **A5's validation gate has never gated anything.** Three are fixed. The
> fourth is open and is §7.

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **1 commit ahead of `origin/main`** — `f272c4a` (the preset fix) |
| `origin/main` | `76c44c6` |
| Gates | **pytest 1366 · vitest 640 · layout 213 checks over 53 registered states · import-linter 30/30** |
| Migrations | dev and production both `0059_f13_config_decl`. Nothing this session needed one |
| Working tree | clean apart from untracked `collect_files.py` (pre-existing, not mine) |
| Local stack | **UP** |
| Deploy | **not run this session.** A6 and the preset fix are both absent from the box |

**A note on the layout number, because 112 and 113 both stated it loosely.** `make
ui-layout` reports **213 passed** — that is the CHECK count (each state runs at 360 dp,
`pa`, `xx-XL`, and a 200 % reflow pass). There are **53 registered states**. 112's "layout
209" was the check count, not states. Quote both or neither.

### Flags — dev

| flag | enabled | note |
|---|---|---|
| `a05_service_preset` | **true** | its gate was satisfied this session — see §7 |
| `m13_vendor` | **false** | food, per v2.0 §4 and the owner's 2026-08-02 decision |
| `m13_service_center` | **false** | A6's new flag; on only for the probes in 113 §5 |

### Flags — production (read from the box)

| flag | enabled | gate | satisfied |
|---|---|---|---|
| `m01_map` | true | — | — |
| `a05_service_preset` | **true** | `service_ingest_verified` | **FALSE** — §7 |
| `m13_vendor` | **false** | — | — changed by this session, §3 |
| `m13_service_center` | *absent* | — | A6 is not deployed |

## 2. The decision: food goes, by flag, not by deletion

The owner said the food section is not coming back any time soon. v2.0 §4 already said
`m13_vendor` stays OFF for food and — explicitly — **"do not delete the code; the cost is
sunk and the flag makes it free to carry."** Deleting it would therefore have been a doc
change needing a logged §17/§23 decision.

Offered three readings and the owner chose the flag. That is the cheapest correct answer
and **A6, built hours earlier in this same session, is the only reason it is available**:
before the split, switching food off would have taken the repair shops with it.

Measured before offering the choice, because "just delete the food part" is not a small
job and the estimate mattered:

- **Shared spine** (food and service both need it): vendor identity, the verification
  ladder, documents, promotions, reviews, moderation, portal shell, analytics,
  impersonation.
- **Food-only**: appearances/schedule, menu, halal, offerings, presence beliefs,
  follow-a-cook, the Food chip and badge.
- **Service-only**: claims, `VendorSite`.
- ~5,000 lines module + API, ~5,200 lines of tests, 10 vendor UI surfaces, plus
  touchpoints in Map, Load, More, FacilityProfile, CorridorStack and the admin console.

## 3. `m13_vendor` was ON in production, over DEMO DATA

**This is the finding of the session.** HANDOFF-113 §9 recorded "production's flag states
were never read" and I reasoned it was "almost certainly OFF" — no handoff records
enabling it, and 073 §115 still lists doing so as outstanding work. The owner asked me to
look. **It was ON**, and had been since M13 shipped, so v2.0 §4 was violated in
production the entire time with nothing recording when it happened.

What sat behind it was worse than an unwanted feature. **All 13 production vendors were
seed or probe residue**, none a real business:

```
Osh Express (demo) · Anas Tamales · Florida Food · Yusuf Kitchen · Gurpreet Dhaba
Gateway Truck Service 7a0397a3 / 17aaf63d / 2301839d · Wingfoot Tire Service 8f0ffbb3
Ana Tamales 5bc0fa / 46eef8 / 705c6b / d8d6e5
```

The hex suffixes are test-run artifacts from sessions 071/072. **31 appearances existed
and 18 were still live** (latest `ends_at` 2026-08-22), so a driver near those facilities
could see a cook called `Ana Tamales 46eef8` advertising invented menu items at invented
prices — wrapped in the full §11.7 honesty apparatus (verification rung, halal rung,
show-up ratio). **All of that machinery assumes the underlying data is real. None of it
defends against a demo row in a live box.**

**Switched OFF at the owner's word**, through the product's own mechanism rather than an
`UPDATE`, with an audit row — because a production flag change with no record of who or
why is exactly how this happened:

```
f13.feature_flag   m13_vendor  enabled=f  kill_switch=f
f14.admin_action   flag_disable  before={"enabled": true}  after={"enabled": false}
                                 2026-08-02 02:26:47+00
```

**Verified from OUTSIDE the box** rather than from the database just written:

```
/api/map/overlay          401   ← m01_map enabled: route exists, wants a session
/api/vendors/appearances  404   ← m13_vendor off: the gate fires BEFORE auth
```

The contrast is the proof. A 404 alone could be a routing artifact; a 401 from a live
module beside it makes it the module gate doing what §23 entry 105 designed.

**A first attempt failed and committed nothing** — `record_action` raised
`NoReferencedTableError` because a bare `python -c` does not register F1's model
metadata. The transaction rolled back, the flag was verified still `true`, and the retry
used `import app.main`. Recorded because the next person operating on the box from a
one-liner will hit the same wall.

**The demo rows are still there.** The flag hides them; nothing was deleted. That is §8.

## 4. The Food chip was still on the map, and it was hiding two real defects

The owner looked at the map and asked why the food icon was still in the chip row. It was
the right question, and the answer was not "a stale icon".

**`preset=food` has ALWAYS answered 500.** `food` is not a member of the `Preset` enum —
it is a client-side mode over the M13 endpoints — and `/map/overlay` called
`m1.Preset(preset)` bare. Measured on the running stack:

```
preset=drive   -> 200 (15 pins)
preset=service -> 200 (7 pins)
preset=food    -> 500          ← unhandled ValueError
preset=bogus   -> 500          ← any bad preset was a server error, not a 422
```

**And MapSurface's own `catch` absorbed it into the offline path** (`livePins = null` →
fixtures), so every tap on Food fell back to fixture pins and looked *merely empty*
instead of broken. It shipped that way with E-D2 on 2026-07-25 and survived every green
suite since. **A 500 that a client silently swallows is the hardest defect to see** — and
what surfaced it was a person looking at a screen, which is the standing warning in v2.0
§9 almost word for word.

**The chip row was a hardcoded array** that never consulted a flag, so switching the food
half off hid the DATA and not the CONTROL. §21.3: a control that leads nowhere is
decoration. §23 entry 415 made a vendor-portal rail item conditional on exactly this
reasoning.

### What was built

- **`GET /map/presets`** — the server's answer about what is live. Food's liveness is
  M13's flag, resolved at the composition layer because M1 may not import a later module.
  Returned as a LIST, not per-preset booleans, so a future preset rides along without
  another field — the same shape the vendor portal uses for `halal_claims_available`.
- **Unknown preset → 422** naming what IS known, instead of 500.
- **`PresetChips` renders only what the server names.** Not a food special case: Service
  follows its own `a05_service_preset` flag down the identical path.
- **The persistence trap, which is the part worth remembering.** The preset is remembered
  per driver state (§23 entry 82), so a driver whose last choice was Food would come back
  INTO a preset that no longer exists **with no Food chip left to press to escape it**. A
  remembered preset that is not live falls back to Drive, and the fallback writes itself
  to memory or the same dead state returns next visit.
- **Unknown resolves to ABSENT.** Offline, or before the fetch lands, the row shows only
  the four §11.3 originals, which ride M1 itself and cannot be wrong. A chip that is
  briefly missing costs one tap; a chip that answers nothing costs trust in the row.

### Verified on the running stack, all three states

```
food OFF (shipping):  presets = [drive, tonight, work, fuel, service]
                      preset=food -> 422 {"error":"unknown_preset","known":[...]}
food ON:              presets = [drive, tonight, work, fuel, service, food]
service OFF too:      presets = [drive, tonight, work, fuel]
```

## 5. The layout harness would have gone green on this

`/map/presets` was unmocked, so it 404'd in the harness, the row fell back to four chips,
and `map-preset-service` — which clicks the sixth chip — would have measured a row that
is not the one shipping. **HANDOFF-105 §9's warning, hit again.** Mocked now, returning
all six so the row is measured at its WIDEST, which is what 360 dp and the +40 %
pseudo-locale actually need to survive.

## 6. Every new assertion was proved RED

Six new tests (4 vitest, 2 pytest), each run against reverted code before being trusted —
a bare `Preset()` and an unfiltered chip row. All six bite. The seven existing chip tests
that assumed an unconditional six-chip row now **declare** what is live, which is the
honest shape: six chips is no longer a property of the component.

## 7. OPEN — A5's validation gate has never gated anything

Found by accident while restoring dev after a probe: disabling `a05_service_preset` made
it impossible to re-enable, because `enable()` refuses on an unsatisfied gate.

```
a05_service_preset   enabled=t   gate service_ingest_verified   satisfied=FALSE
```

**`register_flag(..., enabled=True)` bypasses `can_activate`.** The flag was created
already-on, so the gate it carries has never been consulted — in dev or in production,
where the same row reads the same way today.

I satisfied the gate in **dev** with a note, honestly: 111 did correct the OSM filter and
re-extract every covered state through it (repair 12 → 1,698 nationally), which is
precisely what the gate's own note requires. **Production's gate is still unsatisfied and
its flag is still on.** I did not touch it — that is a production state change nobody
asked for.

**The general defect is not A5's.** Any flag registered with `enabled=True` has the same
hole, and F13's whole promise is that "a flag cannot be enabled until all its gates are
satisfied". Worth its own fix and its own test; deliberately not done here, because it is
a foundation change and this session has already put one of those in front of the owner
(113 §8, the description refresh).

## 8. What I did NOT do

- **Nothing was deployed.** A6 and the preset fix are both absent from the box. The
  Food chip is therefore **still on the production map** until a deploy happens — the
  data behind it is dark, but the control is not.
- **The demo rows were not deleted.** 13 vendors, 31 appearances, 2 claims, 1 review,
  hidden by a flag. They remain indistinguishable from real vendor data to any future
  query, and **A6's own validation — "one real repair shop claims its facility" — stays
  unmeasurable while four fake `Gateway Truck Service` claims share the table.**
- **Production's `a05` gate was left as found** (§7).
- **`register_flag`'s gate bypass was not fixed** (§7).
- **No human has seen the corrected chip row.** The harness measures it and vitest
  asserts it; a push on a real handset is now **eight** sessions old.
- **How demo data reached production was not investigated.** The same path is open to
  every other module. This is a process gap, not an M13 bug.

## 9. Exact next task — production first, and it is not a feature

1. **Push `f272c4a`**, then decide on deploying. Until a deploy, the production map still
   renders a Food chip whose feature is dark — a control that answers nothing, which is
   the exact defect §4 fixed.
2. **Fix `register_flag`'s gate bypass** (§7) and re-check every flag registered with
   `enabled=True`. F13's central promise is currently unenforced.
3. **Decide about the production demo rows** (§8). Owner decision; deleting production
   rows was not taken here.
4. **Ask how demo data reached production**, because the answer governs every module.

Only then the v2.0 board, which has not moved: **A2←D5 · A4←D3 · A7←D1 · A8←D7 ·
A10←D4**, A11 gated on A2, all seven decisions D1–D7 still open, and the Phase DoD still
**2 of 8** (§7 items 5 and 7). A9's tail is TPIMS (a person and a date, not code) and D2/D6.
**The ODbL attribution line already exists** — `map.data_credit` in six locales,
rendered by `MapCanvas` when no basemap carries it — so only the share-alike stance is open.

## 10. Restarting

```
make up          # already up; idempotent
make test        # 1366 pytest + 640 vitest — do NOT pipe it
make lint        # ruff + import-linter (30 contracts)
make ui-layout   # 213 checks over 53 states, ~3–4 min
```

To see either half of M13, its flag has to be switched on: both are OFF in dev, and
`m13_service_center` does not exist in production until A6 deploys.

Nothing is waiting on a background job, an ingest, or a queue.
