# HANDOFF-096 — three defects in one control, found by a screenshot

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 28 July 2026 · **Stack:** UP (`make down` to stop).

**State in one line:** the owner ran a **real rate con** through the import sheet, and the three
radio buttons under *"Is this the same place?"* turned out to hold **three separate defects** —
none of which a 1,023-test suite or a 545-check layout harness could see.

> A short increment on HANDOFF-095. Read 095 for the Load tab's close-out and T-5.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0051_f05_stop_appointment_source** |
| Tests | **pytest 1023 · vitest 402 · layout 545 · ruff clean · import-linter 30/30** |
| §23 decision log | **66 entries** |
| Handoffs | 000 → 096 |
| Git | 268 commits · `main` is **19 ahead of `origin/main`** (local only, HANDOFF §4.3) |
| Services | **running** |

## 2. The one control (§23 entries 65, 66)

*"Is this the same place?"* offers the facility candidates a parsed receiver name matched, and asks
the driver to confirm or reject. It had three faults at once:

1. **"None of these" arrived pre-ticked.** `chosenFacility` starts at `null` to mean *not
   answered*, and that radio carried `:value="null"` — so `v-model` matched it and Vue rendered it
   checked. §23 entry 47 says the match must **never** be pre-ticked: pg_trgm scores a wrong dock
   0.645 and the right one 0.679, four hundredths apart, so no threshold separates them.
2. **The pre-ticked one was the harmful answer.** "None of these" is what tells the API not to
   reuse a dock, and a duplicated dock **splits that facility's dwell history in two** — the exact
   defect entry 47 was written to fix.
3. **The answer was then discarded server-side.** A driver who rejected every candidate sent
   exactly what a driver who never answered sent — no `facility_id` — so `_resolve_facility` ran
   its name+geohash fallback anyway and could attach the load to the dock they had just refused.
   Every load created in the sheet shares **one pair of coordinates**, so the geohash half of that
   rule matches everything the sheet has ever produced.

> **A screen that asks a question and then overrides the answer is worse than one that never
> asked.**

**Three cases are now distinct:** a chosen `facility_id` wins; `create_new_facility` creates;
silence still falls back to matching, which stays right when nothing was ever asked — an
unreadable rate con offers no candidates at all.

**And a fourth defect in the same sheet:** the **broker name was parsed and discarded**.
`broker_name` is in the schema the model fills; the read handler assigned facility, reference,
appointment, free time and rate — and not that one. Same shape as the appointment defect fixed in
entry 62, in the adjacent field. **Fixing one dropped parse field did not prompt anyone to check
the others.**

## 3. A test was holding a bug in place

The existing suite asserted `radios[last].checked === true` and called "None of these" *"the
default, which is the honest one"* — contradicting entry 47 **and** the component's own comment two
lines above the code. So the decision log, the source comment and the test each said something
different about the same three radio buttons, and the screen did a fourth thing.

**A comment is not a test.** There is now an assertion that no facility answer is pre-selected at
all, one for the broker round-trip, and one for each side of the rejection.

## 4. The QA checklist

A tickable manual pass for the Load tab, ordered by the lifecycle of a real load — 79 checks
across 12 stages plus offline, large text, six locales and light theme:

**https://claude.ai/code/artifact/0330a177-344d-48e2-8951-e5da91fbe022**

Two facts it encodes that cost time to rediscover:

- **A load cannot be created without uploading a file** — the manual form only appears *after* a
  read attempt, by design (§10.2 makes the rate-con photo the one action).
- **Every load created in the sheet lands at `32.7767, −96.797`** — that is the coordinate to feed
  DevTools Sensors for anything geofence-related, and it is also why the dedup rule over-matches.

It also states what a browser cannot test: Android back and §20's budgets need a device.

## 5. Exact next task — Session 16

1. **Decide M2-FR4** — the micro-review prompt **six handoffs** have cited as precedent and which
   does not exist. It now has a working EXIT hook available to it; what it lacks is a decision:
   build it, or strike it from the PRD.
2. **Choose the next module deliberately**, the way M5 was chosen — by whether its finish line is
   inside our control. M6 depends on booking, payment and refund posture (F13-gated, PRD §295), so
   numeric order may be the wrong answer.
3. **Finish the manual QA pass** above before starting a module. Four defects in one sheet, all
   green in CI, is the argument for it.

## 6. Debt

**New**

- **The typed facility name is discarded when a candidate is picked** — correct (one dock, one
  name, one history) but it looks like data loss on screen. Noted in the checklist rather than
  changed.

**Carried (unchanged from 095)** — DRIVING thresholds reasoned not calibrated; §5's app-wide
capture chip and "auto-foregrounds the Meter" not taken; RESTING not derived; `make ci` needs a
stopped stack; dead-zone pings dropped not queued; `POST /load/{stop}/end` emits no EXIT; no
in-app notification centre; map facility card + fuel-price sheet unmeasured; `make ui-layout`
~10 min; `API_BASE` hardcoded; **M2-FR4 does not exist**; M4/M9 send a `content_hash` not the
document; F9 required-keys tests presence not value; F9 on raw httpx; no ICU plurals; rate-con
import not offline-capable; no geocoder; hard delete deferred (§17 Q16); no global voice
affordance; F2 geohash-boundary duplicate miss; `collect_files.py` untracked and not ours.

## 7. Commits since HANDOFF-095 (newest first)

```
168bdb7 The screen asked "is this the same place?" and overrode the answer
90d710e The screen pre-ticked the answer that duplicates a dock
```

## 8. Key files touched

```
API  load.py (CreateLoadIn.create_new_facility; _resolve_facility honours a rejection)
UI   core/components/RateConImportSheet.vue (NO_MATCH sentinel, broker assignment,
     create_new_facility on confirm)
TEST test_load_import.py (rejection creates; a chosen id still wins — both proven to bite)
     ui-components.test.js (nothing pre-selected; broker round-trip; both rejection sides)
DOCS design-prd.md §23 entries 65, 66
```

## 9. Restarting

```
make up          # preflight, then the full stack
make test        # 1023 pytest + 402 vitest
make ui-layout   # 545 mobile-first checks at 360 dp, incl. 200% (~10 min)
```

**The standing warning, now with one more entry behind it:** every completion claim in these
handoffs is unverified until you run it — including this one. Six documents in this repo have
asserted something the code did not do, and this session added a *test* to that list. §23 entry 42
named it: *"the original sentence recorded an intention as an accomplishment."*
