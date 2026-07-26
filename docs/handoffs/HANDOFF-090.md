# HANDOFF-090 — the Load tab, and the primary path that lived only in a test

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** the Load tab now matches **all four** things §10.2 specifies and never had —
the next-stop preview, the single CTA, the DRIVING voice hint, and "Add a load" by rate-con photo.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0050_f06_document_archive_reason** (none added) |
| Tests | **pytest 985 · vitest 363 · layout 136/136 · ruff clean · import-linter 30/30** |
| §23 decision log | 47 entries |
| Handoffs | 000 → 090 |
| Git | **51 commits, `main` in sync with `origin`** (remote added by the owner this session) |

## 2. What §10.2 asked for, and what was there

| §10.2 | Before |
|---|---|
| Meter card · stop context · evidence checklist | ✅ |
| **next-stop preview** | ❌ absent |
| **state-dependent single CTA** (Arm → Snap BOL → Send notice → Generate claim) | ❌ six stacked buttons, **no Snap BOL rung at all** |
| **Empty state: "Add a load" by rate-con photo as the ONE action** | ❌ a four-field manual form |
| DRIVING: Meter-only glance **+ voice hint** | ⚠️ collapsed correctly, no hint |

## 3. The BOL row could never say yes

The checklist reads `has_bol(stop)` — a document scoped to **this stop** — and the only capture sheet
in the app filed everything against the **account**. So the row was **permanently false in
production**: not wrong about its data, asking a question the app had made unanswerable.
`POST /protection/documents` has accepted `stop_id` since the writer shipped and nothing passed it —
the fourth capability found sitting in the foundation with nothing reaching it.

The ladder is now implemented as one. It **guides rather than gates**: Snap BOL outranks Generate
claim because a claim without the BOL is weaker, but a driver whose receiver has not produced
paperwork must still be able to file, so passed-over rungs stay reachable as secondary text controls.

## 4. The primary way to create a load existed only inside a test

PRD §108 calls rate-con parse **primary**; PRD §7.16(b) puts "a test driver with a parsed rate con"
in the Foundation DoD. F6 stored `rate_con`, F9 parsed documents, `create_load_from_parsed_terms`
took the result — and **the only place the three were ever joined was
`tests/e2e/test_common_ground_e2e.py`.** The Foundation DoD was satisfied by an assembly that
existed nowhere a driver could reach.

It now runs in production and **stops at a draft** (M4-FR4's driver-confirm step). A term the
contract is **silent on is said as silence, never as a zero** — a driver shown "$0/h" would believe
the contract said so.

**Three defects found by running it, not by testing it.** Green tests covered all three.

1. **The model was handed a SHA-256 hash.** `parse_rate_con` passed `document.content_hash`, copied
   from the e2e where a fake provider made it irrelevant. F9's transport now carries the document
   itself as an image or PDF block. *Naming a document is not reading it.*
2. **A form of nulls counted as a read.** F9's required-keys check tests that the **key** is present,
   not that it has a value — so an all-null parse passed and the screen printed "Read from your rate
   con" over an empty form.
3. **The facility match must never be pre-ticked**, and that is measured. Against "ACME Distribution
   Center", pg_trgm scores an unrelated **"Dallas Distribution Center" at 0.645** and the correct
   **"ACME Distribution Ctr" at 0.679** — four hundredths apart, because the score is dominated by
   shared words. No threshold separates them, so matches are offered and the driver picks.

Matching at all fixed a defect the import surfaced: `POST /load` called `create_facility`
unconditionally, so a driver running the same lane twice put two rows in the registry for one dock —
and those duplicates are what M2's dwell history aggregates over.

## 5. Verified live, against the real model

```
1. photographed rate con -> READ
   $ 2,500.00 linehaul · $75/h after 120min · ref L-9001
   silent on: ['tonu']   (stated as silence, never as $0)
   facility candidates offered: 3 · none pre-selected
2. nothing created yet -> None
3. driver confirmed -> load created
   ACME Distribution Center · Acme Brokerage Inc · $75/h after 120min · source rate_con_parse
4. the contract is in the wallet: ['rate_con']
```

An `ANTHROPIC_API_KEY` **is** configured in `infra/.env`, so this is a real parse of a real PDF —
which is how defect (1) was caught at all.

## 6. Exact next task — Session 10

1. **FR5's EXIT carve-out** — still not started; verify M2-FR4's micro-review prompt really fires on
   geofence EXIT before relying on it as precedent.
2. **The M5 DoD close-out** — the §22.3 sweep, still owed, and still carrying HANDOFF-089 §4's
   caveat that the harness's earlier evidence has to be re-earned.
3. **Then M6**, chosen for a finish line inside our control rather than by numeric order.

## 7. Debt logged, not worked around

- **F9 coerces JSON by prompt, not by schema.** `parse_structured` asks the model to "return ONLY a
  single valid JSON object" and then regex-extracts it. The Messages API has **structured outputs**
  (`output_config.format` with a JSON schema) which would make malformed output impossible. This is
  a foundation-wide change touching M4 and M9 as well, so it was flagged rather than taken here.
- **F9's required-keys check tests presence, not value** — F5 works around it with `has_terms`.
  M4 and M9 use the same gate and have the same exposure.
- **`f9_model` is `claude-haiku-4-5-20251001`** — a date-suffixed ID where `claude-haiku-4-5` is the
  current form, and a model choice worth an owner decision now that a real key is wired.
- **The rate-con import is not offline-capable.** Every other capture queues through F12; this one
  needs the model. A driver photographing a rate con in a dead zone gets the manual form.
- **The confirm screen sends fixed coordinates** for a newly-created facility — there is no geocoder
  in this stack, which is also why facility matching is name-only.
- Carried: F5 has no path to correct a parsed appointment window; no global voice affordance (M11);
  the layout harness never opens sheets; F2 geohash-boundary duplicate miss; `merge_facilities`
  staleness; hard delete for a mis-capture (§17 Q16 carve-out).
- `collect_files.py` sits untracked at the repo root and is not ours to commit or delete.

## 8. Blockers

**None.** The remote was added and pushed this session — the seventeen-session single-disk blocker
is closed.

## 9. Commits this session

```
(this commit) §23 + HANDOFF-090
088ab3d The Load tab had six buttons where §10.2 specifies one, and no next stop
f137dc5 The primary way to create a load existed only inside a test
bf99886 The BOL row asked a question nothing could answer yes to
```

## 10. Key files touched

```
F2     domain/service.py (search_by_name + SEARCH_NAME_SIMILARITY) · public.py
F5     domain/ratecon.py (NEW — prompt registry, parse, silent_terms, facility
       candidates, has_terms, draft_from_rate_con) · public.py
F9     domain/provider.py (_anthropic_messages carries a document block;
       AnthropicModelProvider attaches it from context)
API    api/load.py (POST /load/import; _resolve_facility reuse-before-create;
       facility_id / rate_con_document_id / reference_number on POST /load;
       next_stop on the meter payload)
UI     surfaces/LoadSurface.vue (CTA ladder, More sheet, next-stop preview,
       DRIVING voice hint, empty state -> rate-con import)
       core/components/RateConImportSheet.vue (NEW — photo -> draft -> confirm)
       core/components/DocumentCaptureSheet.vue (stopId + fixedType)
       core/api.js (importRateCon) · i18n/*.json (16 keys ×6)
TESTS  api/test_load_import.py (NEW, 14) · f05_load/test_load.py (+7)
       f09_ai_gateway/test_ai_gateway.py (+document assertions)
       ui-components.test.js (+7 rate-con, ladder, anatomy, DRIVING)
```

## 11. Ports / env / flags

**No port, migration or flag changes.** One env note: `ANTHROPIC_API_KEY` is set in `infra/.env`, so
`/load/import` makes real model calls and draws on F9's per-module budget under module key `f05`.
