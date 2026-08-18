# KICKOFF — Roadside Ready becomes a bottom-nav tab

**Owner-directed, 2026-08-18.** Slot and scope chosen by the owner in session; this
document is the plan those choices need before any code, per working rule 1.

**Chosen:** Roadside Ready takes the **4th tab slot, displacing Docs**. Docs becomes a
More row plus a Load cross-link. **Scope: navigation + a program home**, not the unbuilt
module features.

---

## 1. What this reverses — decision 207, logged as a reversal

Three written positions say the opposite of this instruction. D7 is explicit that
whatever is chosen here "reverses a §23 entry and must be logged as a reversal", so
entry **207** carries all of it or none of it.

| document | what it says today | after 207 |
|---|---|---|
| **E3.1.6** | "**No new bottom-nav tab** — tab changes remain the standing A8/D7 owner decision (D16 folds into it)." Entry is "a plain **row** on More". | reversed for M15; the row becomes a tab |
| **D16** | CONFIRMED (default): "Entry point: More **row** + fleet-portal Readiness section at Phase A" | superseded; the fleet-portal half is untouched |
| **design-prd §4 tab table** | Tab 4 = **Docs** (M5, F6, M9 exports) | Tab 4 = **Roadside** (M15); Docs moves to More |
| **design-prd §10.4** | Docs anatomy: "Inspection mode button (top, 56 dp, works offline in **≤2 taps from cold start**)" | amended — see §2, this is the one real problem |

**NAV-1 is NOT reversed.** The bar stays at exactly 5 tabs, no hamburger, no drawer.
That is why this option was chosen over the six-tab one, and it is why the D7
measurement (a throwaway six-tab bar through the full layout sweep in six locales and
xx-XL) is **not** owed here. If the tab count ever moves, that measurement comes back.

**What this spends:** D7 reserved the next free slot for **Parking (A8)**. Roadside
taking it answers A8 by exclusion. A8 is not thereby resolved — it returns to the queue
with one fewer option, and 207 should say so rather than let it look settled.

## 2. The §10.4 problem, and the fix

This is the part of the chosen option that does not work as stated, found before
building rather than after.

§10.4 requires inspection mode to be reachable in **≤2 taps from cold start**. It is the
screen a driver opens with an officer at the window; the tap budget is the whole point
of the law. Today:

```
cold start -> Map        tap 1: Docs tab      tap 2: Inspection mode    = 2  OK
```

Nesting the wallet under More breaks it:

```
cold start -> Map        tap 1: More   tap 2: Documents   tap 3: Inspection   = 3  VIOLATION
```

**Fix: inspection mode stops being nested behind the wallet and gets its own entry.**
It is not a new component pattern — it is the existing 56 dp primary button and the
existing `BottomSheet` inspection sheet, composed at a second entry point (§22 allows
composition; the placement change is what 207 records).

```
tap 1: Load tab          tap 2: "Inspection mode"     = 2  OK   <- at a stop you are on Load
tap 1: More tab          tap 2: "Inspection mode" row = 2  OK   <- discoverability
tap 1: More tab          tap 2: "Documents" row       = 2  OK   <- the wallet itself
```

Load is the right primary home for it: ON_SITE is precisely when it is needed, and §5's
state machine already foregrounds Load then. More carries both rows so nothing is
reachable only from a state.

**If the owner would rather not touch Load,** the More-row-only variant still satisfies
§10.4 at 2 taps. It is worse at the moment of use and better as a smaller diff. Flagged,
not decided.

## 3. What gets built

### 3.1 The tab

- `TabBar.vue`: slot 4 becomes `{ to: "/roadside", key: "nav.roadside", icon: Mic }`.
  Lucide `Mic` — already imported elsewhere in the app, no new icon (§6.6 forbids
  one-off icons without a decision entry; this is not one).
- `nav.roadside` string in **six locales** (en, es, ru, uz, pa, so) + pseudo-locale.
  **The label is the risk at 72 dp.** "Roadside Ready" does not fit; the tab label is a
  separate, shorter string from `more.roadside`. Candidates go through the layout
  harness at 360 dp in all six before one is chosen — Somali and Russian decide it, as
  they already do for `nav.docs`.
- `nav.docs` is retired from the bar, kept as a More row label.

### 3.2 The program home — `RoadsideHomeSurface.vue` at `/roadside`

The current `/roadside` is a hub with one CTA and a drill button. A tab root implies the
program E3.1.1 describes (check → diagnostic → drill plan → reassessment → record), so
the root becomes that program's home. Four sections, S3 density, all four load states
each (loading / data / empty / failed — a fixture is never one of them, per entry 131):

1. **Your readiness** — band from the latest completed session, carrying the
   **"provisional"** label everywhere until Q-8's calibration gate is met. Empty state
   is the acquisition state: "Start your Roadside Check", primary CTA.
2. **Today's practice** — due count / done, deep-links `/roadside/drill`. Survives an
   empty catalogue, as the current drill button already deliberately does.
3. **Your progress** — the per-skill strip FR6 names (heard ✓ / understood ✓ /
   answered ✓), aggregated from `skill_state`.
4. **Past stops** — session history, each row deep-linking `/roadside/result/:id`.

The existing `RoadsideSurface.vue` is **replaced**, not kept beside the new home — two
front doors to one module is the thing this change exists to remove.

### 3.3 Two new endpoints

Both **account-scoped from the first line** — the list hands out session ids, so its
scoping is load-bearing.

- `GET /roadside/progress` → band, provisional, checked_at, skill aggregate, drill state.
- `GET /roadside/sessions` → the caller's sessions (id, mode, started_at, completed_at,
  band, provisional). Practice-mode and org visibility rules per Q-3 are not in play
  here (this is the driver's own view), but the query takes an account and nothing else.

No new tables, no migration. `skill_state`, `session` and `drill_plan` already carry
every field these read.

### 3.4 Navigation pass over the seven existing surfaces (NAV-2, NAV-4)

`consent → session → result → transcript → coach → drill` were built as a linear flow
reached from a hub. As a tab they need: every surface ≤2 taps from the tab root, back
always landing somewhere sensible (NAV-4), and no dead ends — `result` currently ends
without an obvious way back into the program.

### 3.5 Paperwork, same commit (v2.0 acceptance #3)

- Layout harness states for the new home (4 states) and the moved Docs entry.
- `DRIVE.md` gains the Readiness journey.
- Decision **207** in `docs/decisions/117-current.md`.
- design-prd §4 table, §10.4 and §10.5 amended to match.

## 4. Tests

| what | test |
|---|---|
| tab renders Roadside, not Docs | vitest on `TabBar` |
| §10.4 tap budget | vitest asserting inspection mode ≤2 taps from a tab root — **red first**, against today's 3-tap path |
| progress endpoint scoping | pytest: account A cannot read account B's progress or sessions |
| home's four states | vitest per state |
| six locales complete | `i18n-auditor` sweep before commit |
| nothing regressed | full `make ci` |

Every claim above gets the sabotage treatment (TRAPS §2): break the thing, watch the
test go red, before trusting green.

## 5. Explicitly NOT in scope

Sign practice (`sign_item` has **0 rows**), FR7 reassessment (no engine), the training
record PDF and `/verify/{token}` (a public edge route — TRAPS §3, its own session).

## 6. The content reality, stated rather than discovered later

Production, measured 2026-08-18: **1** released scenario, **3** intents, **17** released
phrase variants, **0** sign items, 45 sessions run. The E3 DoD wants **≥40 intents
released**. This plan builds a program home to the full shape over 3 intents of content.
That is a content-authoring problem, not a navigation one, and it is the owner track —
but a tab promises a program, and the promise is currently ahead of the content.

## 7. Open questions for the owner

1. **Inspection mode on Load, or More-row only?** (§2). Recommendation: Load + More.
2. **`/session/{id}/result` and `/coaching` still have no ownership check** — anyone
   with a session id reads its band (HANDOFF-139 §5, deliberately left). This change
   builds a list that hands out session ids to their own owner, which does not widen the
   hole. Close it in this change, or leave it? Guest sessions are why it is open, so it
   is not a one-liner. Recommendation: close it in a separate change, not this one.
