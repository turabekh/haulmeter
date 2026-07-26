# HANDOFF-090 — the Load tab, and the primary path that lived only in a test

> **SUPERSEDED by [HANDOFF-091.md](HANDOFF-091.md).** This was written mid-session and then had
> §12–§14 appended as the session continued. 091 consolidates it; this is kept as the record of the
> intermediate state.

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** the Load tab now matches **all four** things §10.2 specifies and never had —
the next-stop preview, the single CTA, the DRIVING voice hint, and "Add a load" by rate-con photo.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0050_f06_document_archive_reason** (none added) |
| Tests | **pytest 999 · vitest 365 · layout 136/136 · ruff clean · import-linter 30/30** |
| §23 decision log | 48 entries |
| Handoffs | 000 → 090 |
| Git | **57 commits, pushed to `origin/main`** (remote added by the owner this session) |

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

- ~~F9 coerces JSON by prompt~~ · ~~`f9_model` is date-suffixed~~ — **both closed** in `7b8709c`
  (see §12). All three parse callers now pass a JSON schema; the model is `claude-opus-5` at `low`
  effort for extraction.
- **F9's required-keys check tests presence, not value** — F5 works around it with `has_terms`, and
  the gate is now documented in `parse_structured`'s docstring. M4 and M9 have the same exposure:
  a schema guarantees the *shape*, so an all-null answer still passes.
- **M4 and M9 still send the model a `content_hash`**, not the document — the same defect fixed for
  the rate con in `f137dc5`. The attachment mechanism now exists (`document_b64` in the parse
  context) and both callers hold the F6 document, so this is small; it changes their runtime cost,
  which is why it was flagged rather than taken.
- **F9 talks to the API over raw httpx, not the Anthropic SDK.** Deliberate when written (the
  transport is a module function so tests monkeypatch it without a network), and internally
  consistent — but it means new API surface has to be hand-rolled, as `output_config` just was.
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

## 12. F9 structured outputs + model id (added after §9's commits)

`parse_structured` asked the model for JSON and then scavenged the reply for the first `{` and the
last `}`. It now sends **`output_config.format` with a JSON schema**, so malformed output is not
something to recover from. All three callers bring a schema — F5's rate con, M4's lumper receipt,
M9's settlement lines.

Two consequences worth keeping: the "return ONLY JSON" plea is **dropped** when a schema is present
(asking for what the format guarantees just adds a second, weaker instruction), and the strict path
**does not fall back to scavenging** — brace-hunting can succeed on the wrong thing, returning a
fragment as though it were the whole.

`accessorial_terms` had to become a list of `{term, wording}`: structured outputs require
`additionalProperties: false` on every object, which is exactly what an open map is not. It is
normalised back to a map on the way out.

**Model:** `claude-haiku-4-5-20251001` → **`claude-opus-5`**. The old id carried a date suffix — the
shape that silently 404s when a snapshot retires. Cost is tuned by **effort** rather than model tier:
structured parses run at `low`. `max_tokens` raised to 8192, because thinking is on by default on
Opus 5 and shares that budget with the response.

**One bug the live run caught.** The model names terms the way the contract does — a real parse
returned `{"TONU": "50% of linehaul if cancelled after arrival"}` — and the exact-key lookup for
`"tonu"` missed it, so the screen said the rate con was **silent on TONU while quoting the clause
that grants it**. A driver who believes there is no TONU clause does not claim TONU. Matched
case-insensitively now, and verified both ways live.

## 13. Load history (added after §12)

Asked where past loads are seen. **Nowhere** — `/load` had eleven routes and not one
listed loads. The only "which load" read was `/load/active`, the single armed stop, so ending a load
orphaned its evidence log, condition captures, stop-scoped BOL and rate con: all still stored, none
reachable. An evidence pack is worth having precisely because it can be produced weeks later.

**Two defects underneath.** `LoadStatus` has carried draft/active/completed/canceled since F5 was
written and `set_load_status` was **never called from anywhere** — every load ever created sat in
`draft`, so "completed" could not be listed even by something that wanted to. A load now completes
when its **last** stop departs. And the rate con had no link to the load it built: photographed
*before* the load exists, filed against the account, stop unknown until the driver confirms — F6 can
now attach it without changing whose wallet it is in.

**design-prd was silent and navigation is never-improvise (§22)**, so the shape was the owner's
call, logged as §23 entry 48: the Load tab, tertiary, opening a sheet (NAV-3). Rows carry only what
the load produced.

**One more found by running it.** Every load reported "evidence pack", because `arm_stop` opens a log
for every stop and the flag asked whether one EXISTS. An indicator that can never say no is
decoration — the same shape as the BOL row that could never say yes. It counts contents now: a quiet
load reports 0, one with an arrival reports 1.

## 14. What four screenshots caught (added after §13)

The owner sent four screens. **Five defects, none of which any test noticed.**

**The evidence record listed the driver's whole WALLET** — CDL, medical card, insurance, every rate
con — under a heading sitting directly above *"Share with broker · They get one link to this
record."* The shared artifact never carried them (`compose_pack` builds from the log's records and
artifacts alone), so nothing leaked; what leaked was the **impression**, and the harm runs backwards:
a driver withholds a legitimate claim to protect documents that were never going anywhere. The record
now lists the paperwork attached to **that stop**. Verified live — a wallet of four credentials
renders one BOL.

**`RATE_CON` / `MED_CARD`** — the raw enum, upper-cased: ALL-CAPS (Forbidden #5), untranslated in six
locales, beside a `docs.type.*` catalogue that has had labels since the capture sheet was built. The
same drift the Docs grid was caught by, in a second place. The status column went with the wallet — a
BOL does not expire, so flagging paperwork "expiring" in flare answered a question the list no longer
asks.

**"1 records"** — `t()` has no plural support and the six locales do not share one plural rule (ru
needs three forms), so a figure-first noun cannot be correct here without ICU, which PRD §171 puts in
F15's pipeline. Labelled figures are plural-free everywhere. **ICU plurals logged as F15 debt.**

**"The shareable claim PDF generates at activation"** was false — the pack renderer shipped in
session 6 and the same screen carries a working Export PDF two cards down.

**An invoice whose own figures did not reproduce.** "0:00:38 · $120/h" over **$1.29**; 38s at $120/h
is $1.27. The amount was rounded off the float behind the clock (38.7s) while the time was truncated
to the second. The amount now derives from the seconds we report — a clerk verifying a claim does the
only arithmetic available to them, the figures on its face.

**And one the suite found on itself:** `tests/m13` went red between two runs with no code change.
`enqueue_moderation` took the **database** clock while its caller passed an injected `now`, so the
72h SLA was measured across two clocks and passed only while real time sat on the right side of the
boundary. An injected clock that does not reach the record it dates is not an injected clock.

**Checked and left alone:** the Money tab's `$0.00 delivered to you` above `$1.29 invoiced` is the
North Star figure (recovered + fuel saved + audit-flagged), which is what §10.3 specifies as the
month summary. An invoice is not money delivered.

## 11. Ports / env / flags

**No port, migration or flag changes.** One env note: `ANTHROPIC_API_KEY` is set in `infra/.env`, so
`/load/import` makes real model calls and draws on F9's per-module budget under module key `f05`.
