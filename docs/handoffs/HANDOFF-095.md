# HANDOFF-095 — the Load tab closed out, and a type law that could not have held

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 28 July 2026 (session ran past midnight from the 27th) · **Stack:** UP (`make down` to stop).

**State in one line:** the **Load tab is complete to §10.2 and §5**, T-5's 200% font-scaling box is
retired for the first time honestly, and the two boxes that remain open are open because they need
hardware this machine does not have.

> A short increment on HANDOFF-094 — two commits. Read 094 for the day's substance (F3's sensor,
> FR5's carve-out, the state deriver, the DoD sweep); this covers what closed after it.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0051_f05_stop_appointment_source** |
| Tests | **pytest 1021 · vitest 399 · layout 545 · ruff clean · import-linter 30/30** |
| §23 decision log | **64 entries** |
| Handoffs | 000 → 095 |
| Git | 265 commits · `main` is **16 ahead of `origin/main`** (local only, HANDOFF §4.3) |
| Services | **running** |

## 2. T-5 was unsatisfiable, not merely untested (§23 entry 63)

**Every type token was declared in `px`, and `px` is immune to OS and browser font-scaling.** So
§22.3's box *"Font-scaling 200% reflow verified"* could never have been true in any build: a
driver who set their phone to large text got the same 13 dp captions as everyone else. §16 names
exactly that population — older eyes, a cab at night — as the accessibility case this product
exists in. The box had been ticked for months.

The scale is `rem` now, with the dp values kept in comments so it still reads as §6.2 states it.
**Space, radius and touch stay `px` deliberately:** §6.5's 48 dp glove minimum is about fingers,
not eyesight, and growing targets alongside the type would push a two-column row off a 360 dp
screen at 200%.

**The new assertion earned its keep on the first run**: `meter__figure` overflowed to **366 px**
at 200% on the Money tab. T-6 forbids truncating money and asks for "scale down within token steps
or wrap"; the Meter's figure is one unbreakable string, so wrapping is unavailable and scaling
down is the specified remedy. The ceiling is a **token** (`--type-meter-fluid-max`), because box 8
forbids hardcoded values even inside a fix, and it only bites once the type has outgrown a 360 dp
card. At 100% the normal and DRIVING steps are untouched.

Two assertions per surface, not the full matrix: **481 → 545 checks**.

## 3. ON_SITE, narrowed to the Load tab (§23 entry 64)

§5's ON_SITE row **had no reader** — the state was made derivable in entry 61 and then changed
nothing on any screen. Self-inflicted, but the same shape as the eight other "capability with
nothing reaching it" findings.

**The owner deliberately took less than §5 asks for.** §5 wants capture *"one tap from anywhere
via a persistent action chip"*; a chip above the tab bar on all five tabs is a **new component
pattern AND a navigation change**, both §22.2 never-improvise. So the benefit went inside a
surface that already exists: **cargo-condition capture is two taps everywhere else (More →
Capture) and one while parked at the dock** — the only place those photographs can be taken.

It is a **shortcut, not a move**: the More sheet still lists it, nothing became harder to find, and
it reuses `.rungs__item`, which the harness already measures on `load-live`.

## 4. The Load tab — closed

§10.2's anatomy and §5's states are complete and measured: Meter (resting / appointment countdown /
free time / accruing / filed), stop context with provenance **and correction**, four-row evidence
checklist including M5-FR1's verdict, next-stop preview, single-CTA ladder, empty state, history,
DRIVING glance, ON_SITE capture shortcut, §15.5 degraded card.

**Two boxes remain unclaimed, and will stay that way here:** Android back behaviour and §20's
performance budgets. §20.1 specifies a **≤$180 mid-range Android on throttled 4G** — "dev-machine
performance proves nothing (MF-6)" — so no amount of work on this machine closes them honestly.
They need a device build.

## 5. Exact next task — Session 15

1. **Choose the next module deliberately.** HANDOFF-088 set the precedent: M5 was chosen because
   its finish line was inside our control, not by numeric order. **M6 (parking) depends on booking,
   payment and refund posture** — F13-gated per PRD §295 — so it may not be that module. Worth a
   recommendation before code.
2. **Decide M2-FR4**, the micro-review prompt five handoffs cited as precedent and which does not
   exist. It now has a working EXIT hook available to it; what it lacks is a decision — build it or
   strike it from the PRD.
3. **The device build**, whenever hardware is available: it is the only way to retire Android back
   and §20, and the only way to calibrate the DRIVING thresholds against real GPS.

## 6. Debt — logged, not worked around

**New**

- **DRIVING thresholds are reasoned, not calibrated** — 2.5 m/s / 60 s / 90 s come from §5's
  wording, not from real traces. The first road test may move them.
- **§5's app-wide capture chip** and the "auto-foregrounds the Meter" clause read as *switching
  tabs* — both deliberately not taken (entry 64), both still §5 debt.
- **RESTING is still not derived.** §5 triggers it on "stationary >20 min at a **parking-type**
  facility"; the client has no facility type, and guessing would mute a waiting driver's
  notifications to P0 on a receiver's dock.

**Carried (unchanged from 094)**

- `make ci` needs a stopped stack; dead-zone pings dropped, not queued; `POST /load/{stop}/end`
  emits no EXIT; no in-app notification centre for `protection_gap`; map facility card + fuel-price
  sheet unmeasured (need a Mapbox pin tap); `make ui-layout` ~10 min; `API_BASE` hardcoded;
  **M2-FR4 does not exist**.
- M4/M9 send the model a `content_hash`, not the document; F9 required-keys tests presence not
  value; F9 on raw httpx; no ICU plurals; rate-con import not offline-capable; no geocoder; hard
  delete deferred (§17 Q16); no global voice affordance (M11); F2 geohash-boundary duplicate miss;
  `collect_files.py` untracked at the repo root and not ours to touch.

## 7. Commits since HANDOFF-094 (newest first)

```
606664d ON_SITE had no reader, so cargo capture stayed two taps at the dock
11380b6 T-5 was unsatisfiable, not merely untested
```

## 8. Key files touched

```
UI   core/tokens.scss (type scale px -> rem; --type-meter-fluid-max)
     core/components/TheMeter.vue (T-6 ceiling)
     LoadSurface.vue (ON_SITE capture shortcut)
TEST layout/layout.spec.js (the 200% dimension → 545)
     typography.test.js (token assertion now covers both min() operands)
     ui-components.test.js (ON_SITE shortcut, proven to bite)
DOCS design-prd.md §23 entries 63, 64
```

## 9. Ports / env / flags

**No port, flag, migration or env changes.**

## 10. Restarting

```
make up          # preflight, then the full stack
make test        # 1021 pytest + 399 vitest
make ui-layout   # 545 mobile-first checks at 360 dp, incl. 200% (~10 min)
make down && make ci   # all four gates from cold
```

**And the standing warning from 094, which has not stopped being true:** six documents in this repo
asserted something the code did not do, and every one was found by running the thing rather than
reading about it. §23 entry 42 named the failure mode — *"the original sentence recorded an
intention as an accomplishment."* Treat every completion claim in these handoffs as unverified
until you run it. **Including this one.**
