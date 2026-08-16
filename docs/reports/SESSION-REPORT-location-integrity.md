# SESSION-REPORT — location integrity

2026-08-11 · branch `main` · nothing pushed, nothing deployed, stack left running.
Baseline commit `0eec79f`; six commits, one per task (T4 and T5 committed together — see §4).
Third of three; `SESSION-REPORT.md` and `SESSION-REPORT-wedge-delivery.md` are unmodified.

**No `.env` change, no UI file touched, no knob turned, no data deleted.** Default money
behaviour is unchanged — and that identity is asserted, not claimed (§5.3).

---

## 1. T1 verification

`git log 5af1e9e..HEAD -- api/app/foundation/f03_location/` was **empty**: the two prior
sessions did not touch f03. Verified rather than assumed.

| ID | Verdict | Evidence |
|---|---|---|
| **F3-1** | REPRODUCES, **with one correction** | `arm_geofence` constructed a new row per call, no dedupe, no expiry. **But `disarm_geofence` did NOT have zero production callers** — `f05.disarm_stop` → `depart_stop` → `POST /load/{stop}/end` reaches it, so the happy path always disarmed. Immortality survived on every other path: a stop never departed, a canceled load, an abandoned app, any re-arm |
| **F3-2** | REPRODUCES | ENTER branch is check-then-add; `_active_presence` is a bare `db.scalar` over a set with no uniqueness |
| **F3-3** | REPRODUCES | Each ping applied to current state at its own `occurred_at`, no ordering or future guard |
| **F3-4** | REPRODUCES | `accuracy_m` written by `record_ping`, read nowhere; EXIT fired on a single outside ping |
| **F3-6** | REPRODUCES | `build_trace`'s only callers were its own two tests. The retention comment said so itself |
| minor | REPRODUCES | `_increment_confirmed_arrivals` was read-modify-write; `get_facility` runs per arming inside the ping loop |

### The three pinned facts

**(1) The live-stop predicate.** F5 already stated it, in `complete_load_if_finished`:
`{pending, armed, arrived}` — not `departed`, not `canceled`. Load death is
`LoadStatus.canceled`. **Nothing in the tree writes `LoadStatus.canceled`**, and there is
no stop-cancellation flow either — so D1's "load-cancellation wiring site" **does not
exist**. The predicate reads it anyway, so the reconcile is already correct the day one
appears. The set is now named once (`LIVE_STOP_STATUSES`) and read by both callers, so
they cannot drift about whether `arrived` is live.

**(2) `evaluate_ping` call sites — exactly two.** `api/location.py` (ping ingestion, uses
the return) and `api/load.py` (the manual "I've arrived" synthesis, **discards it**). Both
adapted; the second's indifference is now explained in a comment rather than implied.

**(3) Can the pack's map host a polyline? Yes — and it must not be given this one.**
See §3.1. This selected D5's **delete** branch, against the brief's literal condition.

### Dev data, before any change

| | |
|---|---|
| armings | 69 rows, **22 active**, **0** duplicate-active pairs |
| of those 22 | **1 orphaned** (no live stop at that facility) |
| presence | 58 rows, 11 active, **0** duplicate-active → D2's preflight passed clean |
| pings | 561, of which 400 carry accuracy — **all exactly 150.0** |

D1's premise that production *guarantees* duplicate active armings did **not** reproduce in
dev (0 pairs). Dev is small and mostly departs its stops. The design still holds: 0 today is
not a constraint tomorrow, which is the whole argument for reconcile-not-index.

### Gates

| | Baseline (T1) | Final | |
|---|---|---|---|
| pytest | 1676 | **1714** | +38 |
| vitest | 769 (42 files) | **769 (42)** | unchanged — no UI file touched |
| layout | 289 | **289** | unchanged, run once to prove it |
| ruff + import-linter | clean · 30/30 | **clean · 30/30** | |

---

## 2. Task status

| Task | Status |
|---|---|
| T1 Verify and baseline | CLOSED |
| T2 The migration (0068) | CLOSED |
| T3 Mortal armings (D1) | CLOSED |
| T4 One visit, forward-only time (D2+D3) | CLOSED |
| T5 Inert knobs (D4) | CLOSED |
| T6 The `build_trace` verdict (D5) | CLOSED — **deleted** |
| T7 Finish line | CLOSED |

Nothing BLOCKED.

---

## 3. Two things the design turned on

### 3.1 D5's verdict went against the brief's literal branch condition

The condition was: wire the trace **if** the pack's map can host a polyline without new
rendering machinery. It can — `render.py:_trace` already draws one from `_located_points`,
with `beginPath`/`lineTo`. By the letter, that selects "wire".

It selects "delete" on the evidence, because the obstacle was never rendering. `render.py`'s
governing rule, in its own module docstring:

> The trace is drawn from EVIDENCE, not from raw location pings. Every plotted point is a
> hash-chained record or a geotagged artifact, so the map cannot show a position the
> verification block does not cover.

`build_trace` reads raw `f03.location_ping` — not hash-chained, and **purged on the 365-day
retention declared in the same file**. Wiring it would have (a) plotted positions the
verification block cannot vouch for, in the one artifact whose entire value is that it can,
and (b) made a claim's pack render differently before and after a purge — which is exactly
the property the retention wiring was justified by ("deleting an old ping destroys no
claim's evidence").

Making those points plottable honestly means chaining them as evidence records first. That
is **evidence** machinery, not rendering machinery, and it belongs to the F4 session. So:
deleted, with a tombstone recording what it was, why it went, and what bringing it back
would take. Fifth inert engine closed.

### 3.2 The reconcile's predicate had to be injected, and import-linter said so

The first draft of `reconcile_armings` imported `f05_load.domain.models` from inside f03 to
ask what a live stop was. Import-linter rejected it under *"f05_load internals are private"*
— correctly, and for the deeper reason too: F3 sits below F5, and a location component that
knew what a "stop" was would be F5 leaking downwards.

So F3 owns the mechanism (which armings to disarm, and never to delete them) and the caller
owns the meaning (`f05.has_live_stop_at`). Without a predicate the reconcile collapses
duplicates and orphans nothing, which is the honest behaviour for a caller that cannot say
what "live" means.

---

## 4. Decisions under §3 authority

| Decision | Reasoning |
|---|---|
| **`PingResult` is iterable** (`__iter__`/`__len__`/`__getitem__`) | D3 changes the return type, and T5 requires the pre-existing suite green *unmodified*. Making the result iterable satisfies both: every caller and test that treated it as a list still does, so "unmodified" is a real proof about the state machine rather than a claim about tests edited to agree with it. Exactly **five** assertions changed across the suite — four `== []` → `.events == []` and one list concatenation → `.events + .events`; the same assertions through the new type. Two of the five were found only by the full-suite run, not by grepping the f03 tests |
| **No `__bool__` on `PingResult`** | An earlier draft made truthiness mean `evaluated`, which silently changes `if events:` at every call site. Dropped — a subtle trap for a cosmetic gain |
| **T4 and T5 committed together** | They are one rewrite of `evaluate_ping`; the guards and the knob mechanics live in the same control flow. Splitting them would have been a fake seam in the history |
| **`FUTURE_TOLERANCE` is a constant, not a knob** | It is the width of ordinary handset clock drift, not a policy about money. Five minutes forgives a phone that drifted; it does not forgive one that thinks it is 2031 |
| **`_exit_confirm_pings` floors at 1** | 0 would mean a visit that never ends and a clock that never stops. The retention knob's "0 means off" discipline inverted, because here 0 is the dangerous value — and typing 0 meaning "off" is the plausible operator accident |
| **A skipped ping is still trail-recorded** | Refusing to reason about a ping is not a reason to forget where the driver was. Dropping it would make the map and the retention window lie about the same journey |
| **A future ping does not advance the cursor** | Otherwise one handset with a broken clock sets the mark years ahead and silently refuses every real ping that follows — one bad device ending a driver's tracking |
| **`depart_stop` reconciles the whole account**, not just this facility | Disarming only this dock is what the code already did; the fences it never reached are the ones from stops the driver never departed, which is most of how immortality happened |
| **The reconcile piggybacks on the retention runner** | Same shape of work — a nightly janitor over F3's own tables — and §8 forbids a new job. It is also what makes existing boxes self-heal, since the `depart_stop` wiring only helps accounts that depart a stop from now on |

### Divergences from the prompt

- **F3-1's "`disarm_geofence` has zero production callers" is false** — it has one, via
  `depart_stop`. The finding's *consequence* still reproduces on every other path.
- **D5 took the delete branch** against the literal branch condition (§3.1).
- **D1's load-cancellation wiring site does not exist** — nothing writes
  `LoadStatus.canceled` (§1, fact 1).
- **D1's premise of guaranteed duplicate armings did not reproduce in dev** (0 pairs).
- **The reconcile takes an injected predicate** rather than reading f05 directly (§3.2).
- The facility prefetch inside the ping loop was **skipped** as the brief allowed: with
  armings now collapsed to one per facility the loop is short, and batching it would be a
  second query shape to maintain for no measured gain.

---

## 5. Verification

### 5.1 Migration 0068 — apply, downgrade, refuse, re-apply

```
$ alembic upgrade head        → uq_geofence_presence_active, evaluation_cursor, outside_streak
$ alembic downgrade 0067      → all three gone (index 0, table 0, column 0)
# plant a second ACTIVE presence for one (account, facility)
$ alembic upgrade head
RuntimeError: 0068 cannot apply: 1 (account, facility) pairs with more than one ACTIVE
presence already exist and would violate the new constraint. Reconcile them first — this
migration will not choose which row survives.
Offenders: (UUID('57545429-…'), UUID('2aa5d842-…'), 2)
# reconcile by DEACTIVATING the later one — row count 59 before and after, nothing deleted
$ alembic upgrade head        → clean
$ alembic current             → 0068_f03_location_integrity (head)
```

Production is expected to need no reconciliation here: duplicates are race anomalies, and
dev had zero before the plant.

### 5.2 The dev arming reconcile, run once in-session

```
reconcile: {'scanned': 22, 'orphaned': 1, 'collapsed': 0}
```

| | before | after |
|---|---|---|
| active armings | 22 | **21** |
| total arming rows | 69 | **69** |

One orphan disarmed — exactly what T1's query predicted — and **not one row removed**.

### 5.3 The defaults-identity proof

Three independent legs, because this is the claim the session rests on:

1. `DEFAULT_EXIT_CONFIRM_PINGS == 1` and `DEFAULT_ACCURACY_GATE_M == 0`, asserted directly,
   including through `flags.get_config` on a live database.
2. The **entire pre-existing `evaluate_ping` suite passes** with no behavioural edit.
3. The revert-check that ships `confirm = 2` turns the **pre-existing** tests red
   (`test_exit_emitted_when_leaving`, `test_is_present_tracks_geofence_presence`), so leg 2
   is load-bearing rather than incidental.

---

## 6. Revert-checks

Every guard reverted, the named test confirmed red, restored.
**One stayed green on the first attempt** — the fourth session running in which that has
happened, and again it was the test's fault.

| # | Reverted | Went red |
|---|---|---|
| T3-a | Get-or-create → blind create | `test_arming_twice_yields_one_active_row` + 2 |
| T3-b | The `depart_stop` wiring | `test_departing_one_stop_sweeps_the_fences_of_stops_never_departed` |
| T3-c | The nightly-runner wiring | `test_the_nightly_runner_reports_what_it_reconciled` |
| T3-d | The STATUS half of the live predicate | `test_a_departed_stop_no_longer_earns_its_fence` — **see below** |
| T4-a | The ordering/cursor guard | `test_the_exact_F3_3_sequence_cannot_reopen_a_closed_visit` + 3 |
| T4-b | The future guard | `test_a_ping_from_the_future_…` + `…_does_not_poison_the_pings_after_it` |
| T4-c | The `IntegrityError` recovery | `test_a_second_open_session_is_impossible_…` |
| T5-a | Streak shorted to always-exit | the three knob-on tests |
| T5-b | The accuracy gate | `test_with_the_gate_on_a_vague_ping_is_not_evaluated` |
| T5-c | Defaults drifted (`confirm = 2`) | 3 new + **2 pre-existing** |
| T5-d | The streak reset on an inside ping | `test_a_ping_back_inside_resets_the_streak` |

**T3-d needed a second attempt.** Gutting the status predicate left every test green,
because every departure test routed through `disarm_stop`, which disarms that facility
directly — so the reconcile could stop reading status entirely and nothing noticed. The new
test moves a stop's status underneath the reconcile with nothing else touching the fence, so
only the predicate can produce the result. Same lesson as the previous two sessions: a
revert-check that stays green is an unfinished test, not a pass.

---

## 7. Follow-ups

1. **The F4 session's items, which this one deliberately did not touch:** the device-truth
   basis (mock-location flags, teleport detection), the **"GPS-verified" wording** the
   product uses on claims, and surfacing `gps_time_divergent` — which F3 records on every
   ping and nothing reads. That session also owns the honest way to put a movement trace in
   a pack (§3.1).
2. **`dwell_samples` has no short-session filter**, so a drive-by that produced an
   ENTER/EXIT pair still becomes a dwell sample feeding M2/M8 statistics. F3-1 starves it of
   most inputs — orphaned fences were the main source — but the filter is still absent.
3. **The accepted arm-time race.** Two concurrent `arm_geofence` calls can still both insert;
   there is no unique index and migration 0068 explains why. It is harmless by construction
   rather than by luck: presence is uniquely constrained, so a duplicate arming produces at
   most one visit, and the nightly reconcile collapses the pair.
4. **`LoadStatus.canceled` has no writer.** The reconcile handles it; nothing produces it.
   Either a cancellation flow should exist or the state should go.
5. **The per-arming facility fetch** in the ping loop is now short but still N+1.

### A note to the owner — the two knobs exist, and they are off

`f03.exit_confirm_pings` (**1**) and `f03.accuracy_gate_m` (**0**) are declared, visible in
`/admin/config`, and ship reproducing today's behaviour exactly. Turning either is now a
**config decision, not a code session** — and both move money timing, so both are yours.

- **`exit_confirm_pings`**: at 1, one stray GPS fix outside the fence ends the visit and
  stops the detention clock early. At 2 or 3, a single bad reading costs nothing — and every
  exit is delayed by up to that many pings, which *lengthens* claims.
- **`accuracy_gate_m`**: at 0, every ping is trusted however vague. Above 0, readings the
  phone itself calls unreliable stop deciding presence. Set it too low and a truck in a
  canyon stops being tracked.

**I cannot recommend starting values from this fleet's data, and the reason is the useful
part of this note.** The dev ping table holds 561 rows; 400 carry an accuracy figure and
**every one of them is exactly 150.0** — min, median, p95 and max are the same number. That
is seeded data, not a measurement. Presenting a percentile from it would be inventing a
distribution.

What would produce a real answer: a week of pings from handsets actually in trucks, then
`percentile_cont` over `accuracy_m` grouped by whether the fix fell inside or outside a
fence. The gate belongs somewhere above the p95 of *inside* fixes — high enough that a dock
under a roof is still tracked. Until that data exists, off is the correct value, and the
mechanism being built and tested is what makes the decision cheap when it arrives.
