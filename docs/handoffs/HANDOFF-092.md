# HANDOFF-092 — the session the harness stopped agreeing with us

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 27 July 2026 · **Stack:** UP (`make down` to stop).

**State in one line:** the Load tab was rebuilt where it was lying, and the LAW 0 harness went
from **136 to 466 checks** — it now opens **eighteen sheet states** and renders surfaces in the
state that has the bug, which is how **thirteen defects** were found in one session.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0050_f06_document_archive_reason** (unchanged) |
| Tests | **pytest 999 · vitest 366 · layout 466 · ruff clean · import-linter 30/30** |
| §23 decision log | **54 entries** (see §9 — the count in HANDOFF-091 was wrong) |
| Handoffs | 000 → 092 |
| Git | 252 commits · `main` is **3 ahead of `origin/main`** (local only, per HANDOFF §4.3) |
| Services | **running** |

## 2. What this session was

No new features. One question — *does the screen say what is true?* — asked of the Load tab,
then of every sheet in the app. **Every defect below was green in CI when it was found**, which
is now the fourth consecutive session that sentence is true.

## 3. The Load tab (§23 entry 52)

**The empty state ran a fixture load.** A driver with no work saw a ticking **$37.52 of
detention** in the largest type on the screen, over a facility, a broker and an evidence
checklist that were also invented — and the checklist and stop row sat *outside* the dashed
card, carrying no mark at all. The Meter now **rests**: §9's own `--text-1`, an em dash, no
status line, one sentence of purpose, one action. The owner chose that over marking the sample
more loudly.

**`SAMPLE_STOP` was deleted, not corrected, because its SHAPE was the defect underneath.**
`appointment` was `"07:00"` — a preformatted display string — where `GET /load/{stop}/meter`
returns ISO. So §10.2's stop context row rendered a tidy `07:00 · Acme Brokerage` in every demo
and **`2026-07-27T04:10:50.993277+00:00 · TQL` for every live driver.**

> **A fixture whose shape does not match its endpoint does not preview that endpoint — it hides it.**

Also: `"BOL captured"` was a label that could only read as done (§16 wants color *and* icon *and*
label); §10.2's single CTA was four full-bleed buttons again, listed against the ladder's own
order; `View all evidence` was an 18 dp target against a 48 dp floor.

## 4. The harness (§23 entries 53–54) — the fix that matters

`load` had only ever rendered the tab's **empty** state. The planted token is a string, not a
session, so the meter call 401s and the surface falls back. Four sessions of 136/136 green said
nothing about the ladder, the evidence link or the context row.

Now: **18 sheet states** across Load, Docs, Money, Evidence, Facility and Map, plus a live Load
tab. **136 → 466.**

Three rules the harness now enforces on itself, each of which caught a real mistake this session:

1. **Every mocked surface carries a `ready` selector** that must attach before a single
   measurement. Verified by drifting the mock origin — the surface fails at `ready` instead of
   quietly measuring the empty state twice.
2. **Steps are CSS, never labels.** Every surface runs under en, xx-XL and pa; a label step
   would stop matching in two locales out of three and the surface would go green having opened
   nothing.
3. **Mock payloads are copied from the endpoint's own return shape** — the §3 lesson, applied to
   the thing doing the measuring.

## 5. The thirteen defects

| # | Where | Defect |
|---|---|---|
| 1 | Load, live | Stop context row printed a **raw ISO timestamp** |
| 2 | Load, live | Appointment rendered **twice** |
| 3 | Load, empty | A ticking **$37.52** meter for a load that did not exist |
| 4 | Load, empty | Fake facility, broker and evidence checklist, unmarked |
| 5 | Load, live | `"BOL captured"` could only ever read as done |
| 6 | Load, live | Four full-bleed CTAs; §10.2 specifies one |
| 7 | Load, live | Passed-over rungs listed **against** the ladder's order |
| 8 | Load, live | `.card__link` an **18 dp** target |
| 9 | **Evidence** | **`.cta`, `.field__input` and seven more classes had NO styles at all** |
| 10 | Docs capture | `.cap__chip` **42 dp wide** in Punjabi |
| 11 | Incident | `.chip` 44 dp |
| 12 | Map / Handoff | `.sleep-cta` 44 dp · `.claim` 44 dp |
| 13 | Voice | `.voice__send` declared `56px`, rendered **32** |

**#9 is the one to read twice.** `EvidenceSurface`'s template names `.cta`, `.cta--secondary`,
`.field`, `.field__label`, `.field__input`, `.field__hint`, `.pending`, `.shared` and
`.sheet__lead`. Its scoped block defined **none of them**, and `scoped` means no other
component's `.cta` could reach in. Export PDF, Share, the recipient field and Create link
rendered as **bare 24 dp text with no fill, no border and no target** — on the surface that
produces the pack a driver hands a broker. It survived because the harness only ever loaded that
route at an id with no evidence, where the whole block sits inside a `<template>` that never
renders.

**`44` is a tell.** §11.2's 44 dp is a **map-pin** exemption and it has been leaking into
ordinary controls for three sessions (PresetChips at 40, now three more). Each site now says so
in a comment.

## 6. Two things worth carrying forward

**A declared width is not a floor.** `.voice__send` had `width: 56px` and rendered 32 as a flex
child. And **the fix broke its neighbour**: `flex: none` stopped the collapse and made the row
overflow 360 dp, because `.voice__input` carried flex's default `min-width: auto`. `min-width: 0`
is what makes the pair work — and **the harness caught that regression in the same run that
confirmed the fix.** That is the argument for measuring states rather than reviewing diffs, and
it applies to our own changes first.

**Two bugs in the harness setup were caught by its own `ready` guard**, not by luck:
`/load/active` answering a stop for *every* Load surface (so two empty-state sheets never
opened), and `.audit-cta` matching two controls where the first routes away. Both would have
been silent passes.

## 7. Exact next task — Session 12

1. **FR5's EXIT carve-out** — still not started across four sessions. Verify M2-FR4's
   micro-review prompt really fires on geofence EXIT **before** relying on it as precedent.
2. **The M5 DoD close-out** — the §22.3 sweep. HANDOFF-089 §4's caveat is now **partly
   discharged**: the harness evidence has been re-earned at 466 checks, and the sheets are in it.
   What remains is the non-layout half of §22.3 (six locales, offline, DRIVING-state, a11y).
3. **Then M6.**

## 8. Debt — logged, not worked around

**New this session**

- **The map facility card and the fuel-price report sheet are still unmeasured.** Both open from
  a Mapbox pin tap; the harness has no token, so pins never render. Reaching them needs a token
  in CI or a seam to inject a selected pin — a design decision, not a mechanical addition.
- **`make ui-layout` went 4.3m → 8.7m.** It is CI-only (`make ci`, not `make test`), so the tight
  loop is untouched, but it is now the long pole in CI. Worth a decision if coverage keeps
  growing.
- **`API_BASE` is hardcoded to `http://localhost:8008`** in `ui/src/core/api.js`, so the app only
  works when served to a browser on the host. Fine as a dev seam; it will not survive a device
  test.
- **Four probe accounts and two loads** are in the dev database from creating real loads to look
  at. Harmless; purge whenever.

**Carried (unchanged from 091)**

- M4 and M9 still send the model a `content_hash`, not the document.
- F9's required-keys check tests presence, not value; F9 talks raw httpx, not the SDK.
- No ICU plurals; the rate-con import is not offline-capable; no geocoder.
- Hard delete for a mis-capture — the §17 Q16 carve-out the owner deferred.
- F5 has no path to correct a parsed appointment window.
- No global voice affordance (M11); the status-strip mic stays disabled and labelled.
- F2 geohash-boundary duplicate miss; `merge_facilities` staleness.
- `collect_files.py` sits untracked at the repo root and is not ours to commit or delete.

## 9. A correction to HANDOFF-091

**§23 has 54 entries, not 48.** HANDOFF-091 §1 reported 48 and numbered its own three as 46–48;
the actual count before this session was 51. This session's three are therefore **52, 53 and
54**, and the `§23 entry` references in `LoadSurface.vue` and `fixtures.js` were corrected to
match. The three commit messages below say 49–51 and are wrong on that one number — history was
not rewritten. Count with
`awk 'NR>370' docs/design-prd.md | grep -c '^- 20'` rather than trusting a handoff.

## 10. Commits this session (newest first)

```
e5dc17f A screen that produces broker evidence had no styles for its buttons
64a3096 The workhorse component had never been measured
933a014 The Load tab's empty state was a load nobody had
```

## 11. Key files touched

```
UI   LoadSurface.vue (empty state, stop context, BOL label, CTA hierarchy + order)
     EvidenceSurface.vue (nine style rules that never existed)
     VoiceSheet.vue · IncidentSheet.vue · HandoffSheet.vue
     DocumentCaptureSheet.vue · MapSurface.vue (§6.5)
     core/fixtures.js (SAMPLE_STOP deleted)
     core/i18n/*.json ×6 (+load.empty_title, +load.empty_hint, +load.bol_missing;
                          -load.sample, -load.sample_hint)
     layout/layout.spec.js (live surfaces, 18 sheets, ready/open/upload/nth,
                            label-aware glove spec for radio + checkbox)
     test/ui-components.test.js (empty-state, ladder order, raw-timestamp guard)
DOCS design-prd.md §23 entries 52, 53, 54
```

## 12. Ports / env / flags

**No port, flag, migration or env changes.** `ANTHROPIC_API_KEY` still live in `infra/.env`, so
`/load/import` still makes real model calls under module key `f05`.

## 13. Restarting

```
make up          # preflight, then the full stack
make test        # 999 pytest + 366 vitest
make ui-layout   # 466 mobile-first checks at 360 dp (~9 min)
```
