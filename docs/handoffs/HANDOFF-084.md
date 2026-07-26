# HANDOFF-084 — LAW 0 becomes a check (M5 session 3 of 4)

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** the product's first law is now mechanically verified — and it found five real
defects in its first two runs, including one in itself.

**This session did NOT complete its planned scope.** §6 states exactly what landed and what did not.
The harness was sequenced first deliberately, it took the session, and it was worth it.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0048_m05_on_time_consent** (none added) |
| Tests | **pytest 922 · vitest 345 · layout 72/72 · ruff clean · import-linter 30/30** |
| §23 decision log | 42 entries (none added — see §7) |
| Handoffs | 000 → 084 |
| Git | **27 commits local on `main`, no remote configured** |

## 2. Step 4 verification — two of the brief's assumptions were wrong, usefully

| Claim | Verdict |
|---|---|
| §10.4 specifies the Docs tab | **Confirmed — and `DocsSurface.vue` already implements the whole anatomy**: inspection button, expiring strip in marker pills, grid by type, capture chip, inspection sheet |
| §10.2 specifies FR5's home | **Confirmed — and `LoadSurface.vue` already renders an evidence checklist card** |
| §15.1 offline treatment | Confirmed — thin `text-2` banner, pending glyph, silent completion |
| §8 camera capture | Confirmed |
| M5 locale sweep size | **26 keys**, smaller than feared |

So B and D were largely built. The genuine gaps are narrower than the brief assumed and are itemised
in §6 — **plus three defects nobody had noticed**, now fixed:

- **The Docs capture chip is dead** — `<button class="capture">` with no `@click`. Still dead; §6.
- **The checklist card has no denominator.** §10.2 specifies "photos **2/4**"; the code renders
  `photos · 2`. The denominator *is* FR5 — "2" cannot tell a driver whether they are done.
- **The BOL row asserts ✓ unconditionally**, regardless of state.

## 3. What was built — the LAW 0 harness

`make ui-layout` (own target; `make ci` runs it, `make test` deliberately does not). Playwright,
**four assertions × six surfaces × two themes × ±xx-XL = 72 checks**, ~1.7 min.

1. no horizontal overflow at 360 dp — LAW 0 / MF-2
2. no computed font below the 13 dp floor — §6.2 "Nothing smaller exists"
3. every interactive element ≥ 48 dp — §6.5 glove spec
4. all of it again under `xx-XL` +40% — §12.5

Not visual-regression, on purpose: screenshot diffing fails on every intentional change and teaches
everyone to re-baseline without looking, which is worse than no check.

**Two exemptions, both established by reading the constitution *after* the harness flagged them:**
§11.2 sets map pins at **44 dp** deliberately ("regardless of visual size") — the specific rule beats
§6.5's general 48; and `mapboxgl-ctrl-*` is third-party furniture whose attribution button and logo are
required by Mapbox's licence and are not ours to resize.

## 4. What looking caught that the tests did not

**Five defects, one of them in the harness itself.**

| Found | Was | Now |
|---|---|---|
| `.auth__dev` | 328×**19** | 48 dp min |
| **`.chip` preset chips** | **40 dp** | 48 dp |
| `.relay-banner` | 44 dp | 48 dp |
| `.strip__mic` | declared 48, **rendered 47** | `flex: 0 0 48px` |

The chips are the one to notice: they have shipped at 40 dp since M1 and were **re-approved in a §23
entry** (the Food chip, 2026-07-25) that explicitly says "reusing `.chip`" — nobody measured them, in
review or in approval, for the entire life of the project.

`.strip__mic` is the one a code reader could never catch: the CSS says `width: 48px` and is correct. A
flex parent was shrinking it. Only a browser knows.

**And the harness's own worst failure mode, caught on its first run.** Unauthenticated, the router
guard sends every route to `/login` — so run one tested the login screen six times while reporting six
surfaces, and 48 of its 72 checks were green for the wrong reason. A harness that silently checks one
page while naming six would have gone green over anything. It now plants a session in storage, and
plants it directly rather than driving the login form, so a failing backend cannot read as a layout
defect.

## 5. Verified live

```
72/72 passed (1.7 min) — map · load · money · docs · more · login
                        × {dark, light} × {en, xx-XL}
```

## 6. What did NOT land — carried to Session 4

Everything downstream of the harness. Stated plainly rather than half-shipped:

1. **Prompt attribution** (Step 3) — the row still renders `Photo  seals`, which reads as the platform
   asserting image content in its own voice. **Decided:** `prompted: seals`. Not implemented.
2. **FR5's two gaps** — the `2/4` denominator and the unconditional BOL ✓.
3. **Export/share affordances** — still no button for the session-2 API.
4. **FR1's judged window and verdict**, visible.
5. **The dead Docs capture chip**, and inspection mode **measured**.
6. **Gurmukhi** — §6.2's claim remains false: not vendored, `--font-gurmukhi` applied to nothing, no
   metrics verification. `pa` still renders in Plex Sans, which has no Gurmukhi coverage.
7. **The locale sweep** — nothing new to sweep yet, since 1–5 did not land.

Plus the previously-scheduled Session 4 items: the **F6 expiry dispatcher**, the **FR5 EXIT carve-out**,
and the **share-link lifetime** question (90 days may be shorter than a dispute; M3's dunning alone runs
21 days before escalation).

**This is now a five-session program.** The honest split: session 4 takes items 1–5 plus the locale
sweep (the driver surface); session 5 takes what fires unattended plus the M5 DoD close-out.

## 7. M5 FR status — end to end vs server only

| FR | Server | Driver app |
|---|---|---|
| **FR1** on-time proof | ✅ complete, tested | ❌ no visible window or verdict |
| **FR2** condition protocol | ✅ capture + export + share | ⚠️ capture exists; **no export/share button** |
| **FR3** wallet | ✅ reads; ❌ **dispatcher unbuilt** | ✅ §10.4 anatomy present, capture chip dead |
| **FR4** incident | ✅ complete, tested | ⚠️ capture exists; **no export/share button** |
| **FR5** summary | ✅ complete | ⚠️ card exists, missing denominator + real BOL state |

**No FR is complete end to end.** FR1, FR2 and FR4 have been half-shipped since session 2 and this
handoff says so, as instructed, until they aren't.

No §23 entries this session: the harness implements existing law rather than deciding anything new, and
the two exemptions are the constitution's own text. The **prompt-attribution wording is decided
(`prompted: seals`) and unimplemented** — it should be logged when it ships, not before.

## 8. Blockers and open questions

- **No git remote — twelve sessions.** Twenty-seven commits local on `main`.
- **The harness needs a browser in the image.** `make ui-layout` installs chromium on first run
  (~111 MB). Fine locally; a CI image should pre-bake it or the first job pays the download.
- **The harness tests six surfaces with a planted session.** Surfaces behind live data (evidence
  detail, condition capture, facility profile) are not covered yet — worth extending as session 4's UI
  lands, so the new work is checked as it arrives.
- Carried, untouched: the F2 geohash-boundary duplicate miss and `merge_facilities` staleness.

## 9. Commits this session

```
(this commit) docs: HANDOFF-084 — LAW 0 becomes a check
647b43b LAW 0 becomes a check instead of a claim
```

## 10. Key files touched

```
HARNESS  ui/layout/layout.spec.js (NEW) · ui/playwright.config.js (NEW)
         ui/package.json (+@playwright/test, `layout` script) · Makefile (ui-layout, ci)
FIXES    ui/src/surfaces/AuthSurface.vue (.auth__dev 19 -> 48)
         ui/src/core/components/PresetChips.vue (.chip 40 -> 48)
         ui/src/surfaces/MapSurface.vue (.relay-banner 44 -> 48)
         ui/src/core/components/StatusStrip.vue (.strip__mic flex 0 0 48)
DOCS     HANDOFF-084.md · HANDOFF.md
```

## 11. Ports / env / flags

**No port, env, migration, flag or config changes.** One new dev dependency (`@playwright/test`) and one
new make target (`ui-layout`). `make ci` now runs lint → test → ui-layout.
