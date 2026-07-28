# HANDOFF-097 — the session the owner found everything by using it

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 28 July 2026 · **Stack:** UP (`make down` to stop).

**State in one line:** the owner ran **one real two-stop load end to end**, four times, and every
report they made was a real defect — including a detention clock that billed **$271.43 against
$0.53 owed**, an evidence pack containing three other loads' arrivals, and two buttons that had
never worked once since the day they were written.

> Read 096 for the import sheet's close-out. This session is what happened when the load
> those fixes made possible was actually *run*.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0052_m03_claim_clock_since** |
| Tests | **pytest 1048 · vitest 420 · layout 545 · ruff clean · import-linter 30/30** |
| §23 decision log | **80 entries** |
| Handoffs | 000 → 097 |
| Git | `main` local only, never pushed (HANDOFF §4.3) |
| Services | **running** |

## 2. What the owner found, in order

Every item below was reported by **running the app**, not by reading code. None was caught by
the suite, and three were invisible to a passing test *by construction*.

| # | Report | What it actually was | §23 |
|---|---|---|---|
| 1 | "the pack says an event occurred, not which" | events never written; API stripped the payload it did have | 70 |
| 2 | "export pdf does nothing" | `packKind()` called `useRoute()` **inside a click handler** — threw before the network. Export *and* Share had never worked | 71, 72 |
| 3 | "detention money is being calculated wrong" | the clock read the **dock's whole history**, not this visit. $271.43 billed, $0.53 owed | 73 |
| 4 | "two claims but past loads shows one" | every history figure read off `stops[0]` | 74 |
| 5 | "which stop is this pack for?" (4 ENTERs in one pack) | `accrue_events` — the **same unscoped read**, three lines above the one just fixed | 75 |
| 6 | "is this the same place?" showing two identical rows | two real facilities, no way to tell them apart; address discarded on create | 76 |
| 7 | broken-image glyph on a chosen PDF | capture preview always an `<img>` | 77 |
| 8 | "where are my 8 photos?" | 4 per stop; a per-stop export can only show a fragment of a route | 78 |
| 9 | "docs tab is messy" | wallet was **87% other loads' paperwork** (40 documents, 5 the driver's) | 79 |
| 10 | "clicking a doc shows nothing" | viewer's PDF branch keys off a `content_type` the wallet never sent | 80 |

## 3. The money defect, because it is the one that matters

`_arrival_departure` replayed **every geofence event ever recorded** for the account at that
facility and took the earliest ENTER and the latest EXIT. Measured on the owner's load:

| Stop | Real dwell | Billed | Owed |
|---|---|---|---|
| Pickup · Harvest Foods DC | 84 s | $83.67 | **$0.53** |
| Delivery · Metro Market | 53 s | $187.76 | **$0.00** |
| | | **$271.43** | **$0.53** |

Both `invoiced`, with receivables posted to F07.

**F3 had the right answer the whole time.** `GeofencePresence` has always recorded one row per
visit with `entered_at`/`exited_at`. M3 reimplemented visit detection from raw events and got it
wrong. `compute_detention` was never the defect — it is exact and does deduct free time. The
inputs came from the wrong visit.

Claims now carry an explicit `clock_since` (migration 0052) rather than inferring an anchor from
row metadata: the value the money depends on should be statable by a caller, testable without a
wall clock, and printable on the invoice beside the arrival and departure it bounds.

**Owner decision: fix forward.** The bad claims and receivables stay in the dev database.

## 4. Two recurring shapes, now with counts

**"A capability with nothing reaching it"** — five instances this session: the `stop` pack kind
(71), Export/Share both dead behind one throw (72), the next stop never armed (69, previous
session), `t()` ignoring its params so `{n}` reached a real vendor (74), and the viewer's PDF
branch keyed off a field never sent (80).

**"Fixing one dropped field never prompted a check of its neighbours"** — the address into
coordinates (67), the whole pickup stop (68), the route advance (69), history's rollup (74), the
address string itself (76), and worst of all **`accrue_events` (75), three lines above the
function fixed hours earlier in the same file.**

Still outstanding, and logged rather than assumed fine: **`rate_cents` and `accessorial_terms`
reach no load field.** Sixth and seventh in that pattern. Do not fix one without checking both.

## 5. Method notes — read these before trusting a green run

- **Three defects this session were found only by rendering the PDF to an image and looking at
  it.** A serialiser writing `valid` where the renderer reads `chain_valid` printed "HASH CHAIN
  BROKEN" over four intact records while the endpoint returned 200 and every assertion passed.
- **Two of three regression tests initially passed against the broken code.** One staged its
  "earlier visit" without arming a geofence, so it recorded nothing. Always run a new regression
  test against the *old* implementation before believing it.
- **`v-show` let seven about-to-be-wrong tests stay green** — a hidden element is still in the
  DOM and still answers `.text()`. `v-if` failed all seven honestly.
- **Do not run `make test` while `make ui-layout` is running.** Two Playwright workers competing
  with pytest+vitest produced 4 then 9 failures with 5 s selector waits and 30 s timeouts, and I
  wrongly reported them to the owner as possible flake. A contended run tells you nothing.
- **A test asserted the defect as correct:** `test_history_states_money_when_a_claim_was_filed`
  asserted `is not None` against an amount that was always **zero**, passing only because the
  endpoint returned a literal `0` — the value the row renders as "no money".

## 6. Exact next task — Session 18

The owner is mid-QA on the Load tab and finding roughly one real defect per screen. **Keep
running it**, but the two highest-value pieces of unforced work are:

1. **`rate_cents` and `accessorial_terms` reach no load field.** Sixth and seventh dropped parsed
   values. Fix together, and check every neighbour in `parsed` before declaring it done.
2. **Republish the QA checklist artifact** — it predates the evidence pack, the export, the
   route rollup, the Docs split and the load pack, so it no longer covers what exists.

## 7. Debt

- `rate_cents`, `accessorial_terms` — parsed, stored on no load field
- Per-stop detention terms exist in the schema and are not expressible in the UI
- **M2-FR4 does not exist** — needs an owner decision
- The meter caption looked absent in one owner screenshot right after arrival; `meterLabel`
  cannot return empty and all six locales carry `load.free_time`. **Unreproduced — do not
  "fix" it without seeing it.**
- Existing evidence logs polluted by defect 75 **stay polluted**: the chain is append-only, so
  those records cannot be removed without breaking the hashes that make a pack worth anything.
  Only stops recorded after `f3e6a86` are clean.

## 8. Commits since HANDOFF-096 (newest first)

```
<this handoff>
8bb4a2c  the route in one pack, the wallet split, collapsed by default   (78, 79, 80)
f3e6a86  scope the pack to its visit; two docks tell themselves apart    (75, 76, 77)
70bd042  bill the visit, not the dock's history; report the route        (73, 74)
c7fd870  name every event, and make the export button work at all        (70, 71, 72)
673be0e  a rate con is a route, and the route has to advance             (68, 69)
8e172d3  every dock was filed in Dallas, whatever the rate con said      (67)
```

## 9. Key files touched

```
API  m03/service.py       visit_window scoping for BOTH the clock and accrue_events
     f03/service.py       visit_window() — F3 finally asked which visit
     f04/service.py       compose_grouped_pack (route-wide packs, labelled sections)
     f04/render.py        per-stop headings in the timeline AND the artifact grid
     m05/service.py       load_pack, wallet split (credentials / paperwork / orphans)
     api/m05_protection   _parties, _route, _money — the pack finally names the broker
     api/load.py          history rollup + per-stop rows; address kept on create
     migrations           0052_m03_claim_clock_since
UI   LoadSurface.vue      route label, expandable history rows, whole-load export
     DocsSurface.vue      three collapsible sections, collapsed by default
     DocumentViewer       (unchanged — it was right; the wallet was not sending content_type)
     core/i18n.js         {placeholder} substitution, which never existed
     layout.spec.js       states open their disclosure first; docs-paperwork added
DOCS design-prd.md §23 entries 70–80
```

## 10. Restarting

```
make up          # preflight, then the full stack
make test        # 1048 pytest + 420 vitest
make ui-layout   # 545 mobile-first checks at 360 dp (~11 min) — RUN IT ALONE
```

**The standing warning, earned again.** Every completion claim in these handoffs is unverified
until you run it. This session, ten separate defects were found by an owner *using the app* that
1,048 tests and 545 layout checks could not see — and two of them were in code written hours
earlier to fix that exact class of problem. §23 entry 42 named it: *"the original sentence
recorded an intention as an accomplishment."*
