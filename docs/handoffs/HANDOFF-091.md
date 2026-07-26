# HANDOFF-091 — the session where running it beat testing it

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** brought DOWN at end of session (`make up` to restore).

**State in one line:** the **Docs tab and the Load tab are both complete to their §10 specs**, and
**eight defects were found by running the product or looking at it — none by the test suite**, which
was green before and after every one of them.

> This supersedes HANDOFF-090, which was written mid-session and then had §12–§14 appended as the
> session kept going. Read this one; 090 is kept as the record of that intermediate state.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0050_f06_document_archive_reason** |
| Tests | **pytest 999 · vitest 365 · layout 136/136 · ruff clean · import-linter 30/30** |
| §23 decision log | **48 entries** |
| Handoffs | 000 → 091 |
| Git | **57 commits, `main` pushed to `origin/main`** — the remote blocker is closed |
| Services | **stopped** (`make down` run at end of session) |

## 2. What shipped

**Docs tab (M5-FR3) — removal and the archive.** "Delete" is **remove**, and remove is reversible:
§17 Q16 forbids hard delete, so a removed document leaves the wallet, leaves inspection mode and
stops the expiry ladder while the row and bytes stay put. The archive shows **why** each row is there
("replaced by a newer one" / "you removed this") and whether Restore will work — a blocked restore
names the document in the way. Migration 0050 added `archive_reason`. §23 entry 46.

**Load tab (§10.2) — all four missing anatomy items.**

| §10.2 | Was | Now |
|---|---|---|
| next-stop preview | absent | ✅ |
| single state-dependent CTA | six stacked buttons | ✅ ladder + "More for this stop" sheet |
| **Snap BOL rung** | **never existed** | ✅ |
| empty state: rate-con photo import | four-field manual form | ✅ |
| DRIVING voice hint | absent | ✅ (points at the Map tab, which has voice) |

**Rate-con import (PRD §108's *primary* way to create a load).** Photo → F6 → F9 structured parse →
driver-confirm → load + stop. It **stops at a draft** (M4-FR4), every parsed value is editable, and a
term the contract is **silent on is said as silence, never as a zero**. §23 entry 47.

**Load history.** A finished load is reachable again, with its evidence, paperwork and money. §23
entry 48 — the owner chose the placement, because design-prd is silent and navigation is a
never-improvise category.

**F9 structured outputs + model id.** `output_config.format` with a JSON schema on all three parse
callers (F5 rate con, M4 lumper, M9 settlement). Model `claude-haiku-4-5-20251001` →
**`claude-opus-5`** (no date suffix — the dated form silently 404s when a snapshot retires), with
cost tuned by **effort** (`low` for extraction) rather than model tier, and `max_tokens` raised to
8192 because thinking is on by default and shares that budget.

## 3. The eight defects, and the pattern

**Every one was green in CI when it was found.** Five came from the owner looking at a screen, three
from running the product. That is the most important line in this document.

| # | Found by | Defect |
|---|---|---|
| 1 | opening the Docs tab | The wallet had **no writer** — every driver-facing document endpoint was a GET |
| 2 | `make ui-layout` | The layout harness was measuring **Vite's error page**; 135 mobile-first checks passed against a screen that was not ours |
| 3 | running the import | The model was handed a **SHA-256 hash** where a contract should be — copied from the e2e, where a fake provider made it irrelevant |
| 4 | running the import | An **all-null parse counted as a read** — F9's required-keys check tests that the key is *present*, not that it has a value |
| 5 | measuring | The facility match **cannot be pre-ticked**: pg_trgm scores a wrong dock 0.645 and the right one 0.679 |
| 6 | a live parse | A rate con stating TONU was reported **silent on TONU** — case mismatch on the term key |
| 7 | live history | Every load reported "evidence pack" — the flag asked whether a log **exists**, and `arm_stop` opens one for every stop |
| 8 | four screenshots | The evidence record listed the driver's **whole wallet** under "Share with broker" |

Plus one the suite found on itself: `tests/m13` went red **between two runs with no code change** —
`enqueue_moderation` took the database clock while its caller passed an injected `now`, so a 72h SLA
was measured across two clocks. **An injected clock that does not reach the record it dates is not an
injected clock.**

**The recurring shape** — six times now — is *a capability that exists in the foundation with nothing
reaching it*: the wallet's writer, the document viewer, the archive, `get_document_bytes`,
`include_archived`, the rate-con chain assembled only inside a test. When picking up work here,
**check what already exists before building it.**

**The second recurring shape** is an *indicator that can only answer one way*: the BOL row that could
never say yes, the evidence flag that could never say no, the harness that could not fail. These read
as working software and are decoration.

## 4. Verified live (not asserted)

```
rate con (real PDF, real model) -> $2,500 linehaul · $75/h after 120min · ref L-9001
                                   receiver + appointment · TONU stated -> silent_on []
                                   a rate con stating neither -> silent_on [detention, free_time, tonu]
nothing created until confirmed  -> /load/active null
load created                     -> source rate_con_parse · contract in the wallet
two loads ended                  -> both `completed`, history lists them newest-first
evidence indicator               -> quiet load 0 · load with an arrival 1
shareable record                 -> wallet holds [bol, permit, insurance, med_card, cdl]
                                    the record shows [bol]
```

## 5. Exact next task — Session 11

1. **FR5's EXIT carve-out** — still not started across three sessions. Verify M2-FR4's micro-review
   prompt really fires on geofence EXIT **before** relying on it as precedent.
2. **The M5 DoD close-out** — the §22.3 sweep. Carries HANDOFF-089 §4's caveat: the harness's
   pre-fix evidence has to be **re-earned**, not cited.
3. **Then M6**, chosen for a finish line inside our control rather than by numeric order.

## 6. Debt — logged, not worked around

**New this session**

- **M4 and M9 still send the model a `content_hash`, not the document** — the same defect fixed for
  the rate con. The attachment mechanism exists (`document_b64` in the parse context) and both
  callers hold the F6 document, so this is small; it changes their runtime cost, which is why it was
  flagged rather than taken.
- **F9's required-keys check tests presence, not value.** A schema guarantees the *shape*, so an
  all-null answer still passes. F5 works around it with `has_terms`; M4 and M9 have the same exposure.
- **F9 talks to the API over raw httpx, not the Anthropic SDK.** Deliberate when written (the
  transport is a module function so tests monkeypatch it without a network) and internally
  consistent — but new API surface has to be hand-rolled, as `output_config` just was.
- **No ICU plurals.** `t()` has no plural support and the six locales do not share one rule (ru needs
  three forms), so counts use labelled figures. PRD §171 puts ICU in F15's translation pipeline.
- **The rate-con import is not offline-capable** — every other capture queues through F12; this one
  needs the model. A dead zone gets the manual form.
- **No geocoder**, which is why facility matching is name-only and a newly created facility takes the
  confirm screen's coordinates.
- **The layout harness never opens sheets.** It measures nine base surfaces; the archive sheet, the
  confirm sheet, the viewer, the capture sheet, the More sheet, the history sheet and inspection mode
  are all **unmeasured at 360 dp**.

**Carried**

- **Hard delete for a mis-capture** — the §17 Q16 carve-out the owner deferred.
- F5 has no path to correct a parsed appointment window.
- No global voice affordance (M11); the status-strip mic stays disabled and labelled.
- F2 geohash-boundary duplicate miss; `merge_facilities` staleness.
- `collect_files.py` sits untracked at the repo root and is not ours to commit or delete.

## 7. Blockers

**None.** The remote was added and everything is pushed.

## 8. Commits this session (newest first)

```
098994d docs: HANDOFF-090 §14 — what four screenshots caught
dfae285 An invoice whose own figures do not reproduce
c638e3f A record offered to a broker listed the driver's CDL
c41baf2 §23 + HANDOFF-090 §13: load history, and where it was allowed to live
57e1bff A finished load left no way back to itself
712d5cd docs: HANDOFF-090 §12 — structured outputs, the model id, and the TONU bug
7b8709c F9 asked for JSON and went hunting for braces; now the format guarantees it
a5a1c1c §23 + HANDOFF-090: the Load tab, and what running it caught
088ab3d The Load tab had six buttons where §10.2 specifies one, and no next stop
f137dc5 The primary way to create a load existed only inside a test
bf99886 The BOL row asked a question nothing could answer yes to
6737d7c docs: HANDOFF-089
a6ad714 §23: delete is remove, and remove is reversible
b1e0cab The layout harness was measuring Vite's error page
7a78b10 A wallet you cannot take anything out of is a drawer that only opens one way
```

## 9. Decisions logged (§23 entries 46–48)

- **46 · Documents** — "delete" is remove, and remove is reversible; the reason is load-bearing.
- **47 · Load tab** — the four specified-but-absent items; the ladder guides rather than gates; the
  three rate-con defects found by running it.
- **48 · Load history** — where it lives was the owner's call (design-prd silent, navigation
  never-improvise); loads never left `draft`; an indicator that can never say no.

## 10. Key files touched

```
MIGRATION  0050_f06_document_archive_reason
F2   domain/service.py (search_by_name) · public.py
F5   domain/ratecon.py (NEW) · domain/service.py (list_loads,
     complete_load_if_finished) · public.py
F6   domain/models.py (archive_reason) · domain/service.py (archive_document,
     restore_document, set_document_subject) · public.py
F9   domain/provider.py (document blocks, output_config schema + effort,
     _parse_json strict) · domain/service.py (parse_structured schema)
F14  domain/service.py (enqueue_moderation now)
M3   domain/service.py (amount derives from reported seconds)
M4   LUMPER_SCHEMA · M9 SETTLEMENT_SCHEMA · M5 archive/restore + wallet count
API  load.py (import, history, facility reuse, next_stop, stop-scoped record)
     m05_protection.py (archive, restore, GET /documents/archive)
CORE config.py (f9_model -> claude-opus-5)
UI   LoadSurface · DocsSurface · EvidenceSurface · ClaimSurface
     RateConImportSheet.vue (NEW) · DocumentCaptureSheet (stopId, fixedType)
     DocumentViewer (remove) · api.js · fixtures.js · i18n/*.json (43 keys ×6)
     vite.config.js (allowedHosts — the harness fix)
```

## 11. Ports / env / flags

**No port or flag changes.** One migration (0050). Two env notes:

- **`ANTHROPIC_API_KEY` is set in `infra/.env`**, so `/load/import` makes **real model calls** and
  draws on F9's per-module budget under module key `f05`. This is how defect #3 was caught.
- `f9_model` is now `claude-opus-5`; structured parses run at `effort: low`.

## 12. Restarting

```
make up          # preflight, then the full stack
make test        # 999 pytest + 365 vitest
make ui-layout   # 136 mobile-first checks at 360 dp
```
