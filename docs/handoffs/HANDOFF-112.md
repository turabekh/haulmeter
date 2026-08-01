# HANDOFF-112 — A1 requirement 1, and the first config key anyone could actually find

> One session, continuing 110/111 under **PRD v2.0**. It builds the last buildable piece
> of **A1 — requirement 1, the capture checklist** — and the finding underneath it is
> that the requirement's own last clause was the hard part.
>
> **Stack UP · everything pushed and deployed · haulmeter.online CURRENT.**
> Verified against the artifact, not the deploy script's output: production head is
> `0059_f13_config_decl`, `f06.doc_type` carries `seal` and `damage`, the declaration row
> exists and is UNSET, both checklists resolve with a real capture path for every item,
> and the served bundle carries `checklist__snap`, `load.doc.*` and `admin.cfg.bad_json`.
> A fresh backup was taken at the new schema and the **restore performed and verified**
> from the bucket (A12 §7 item 7): head matches, 18,322 facilities / 174 accounts / 60
> beliefs / 196 events all match, PostGIS geometry intact.

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, pushed to `origin/main` at `f1ed43d` |
| Gates | **pytest 1345 · vitest 632 · layout 209 · import-linter 30/30** |
| Migrations | dev **and production** head `0059_f13_config_decl` |
| Working tree | clean apart from untracked `collect_files.py` (pre-existing, not mine) |
| Deploy | run at the owner's word, then verified against the box (see the banner) |

## 2. A1 requirement 1 — what it actually asked for

> "A capture checklist per stop type — BOL, seal, cargo condition, lumper receipt,
> damage. **The checklist is configuration (F13), not code.**"

The last sentence is the requirement, not a note on it. Measured before building:

- `CONDITION_SEQUENCE` in `m05_protection/domain/enums.py` is a hardcoded Python list of
  four items, and it serves **M5-FR2's cargo photos**, not A1's per-stop-type paperwork.
  Changing it means a deploy.
- `grep 'flags.get_config|set_config|CONFIG_'` across M5 returned **nothing**. M5 read no
  F13 config at all.
- §10.2's evidence card carried exactly **one** paperwork row, hardcoded to the BOL.

So a driver dropping a load was **never asked for the POD**, and a driver collecting one
was **never asked for the seal**. A pickup and a delivery got the same single question.

## 3. Three things had to be true before the list was worth rendering

**It had to be ANSWERABLE.** `seal` and `damage` were not F6 `DocType` values, and
`capture_document` — the only writer of a stop's paperwork — rejects anything outside
`DRIVER_DOC_TYPES`. A checklist row with nowhere to capture it is a tick that can never
turn green. That is `has_bol`'s own lesson facing the other way:

> "the row rendered an unconditional tick. **A checklist that always says yes is
> decoration**" — and one that can only ever say no is the same decoration, learned
> faster.

`checklist_capture_path()` returns `None` for an item nothing can satisfy, and a test
refuses to let a **default** checklist name one. Migration `0058` adds the two enum
values; both were added to `DRIVER_DOC_TYPES` so the real writer accepts them.

**It had to be ACTIONABLE.** The capture sheet was `fixed-type="bol"`. Five rows would
have asked for five artifacts and filed five BOLs. Each uncaptured row is now a 48 dp
target (§6.5) that opens the sheet for **its own** type.

**It must not DUPLICATE.** `cargo_condition` is on the configured checklist *and* is
already the photos row carrying §10.2's `2/4` denominator. Only `kind: "document"` rows
render; the domain layer keeps the full list.

**`damage` is IF-APPLICABLE.** A clean stop has no damage to photograph. Reporting a
clean stop as incomplete is how a checklist becomes noise — and a dismissed checklist is
exactly the rubber stamp `draft_stop_packet_on_exit` was built to prevent. Its label
reads "No damage recorded", and `checklist_outstanding` excludes it.

## 4. The requirement was true in the code and FALSE in practice

`capture_checklist` reads `a01.capture_checklist` and an operator could POST it. Then
three separate things meant nobody could:

1. **`/admin/config` listed rows that EXIST.** `get_scope` returns `ConfigEntry` rows,
   so an unset key appeared nowhere. `a01.capture_checklist` is the **first config key
   any component in this product reads** — nothing anywhere calls `set_config` outside
   the admin endpoint and tests, so there was no seeding pattern to follow and no
   declaration mechanism to extend.
2. **`/config/scopes` returned scopes that have entries.** On a box where nothing has
   been configured — every box, on first boot — that is an empty list, so the console's
   scope dropdown was empty and everything behind it unreachable. The endpoint's own
   comment promised an operator "never has to guess a scope name to discover what is
   configurable."
3. **The console editor is one text input.** The checklist value is an object:
   `v-model` renders `[object Object]` and saving writes that string back. An operator
   opening the page to adjust the checklist would have **destroyed** it, and
   `capture_checklist` would then read a quoted blob as a list of characters.

So F13 gained `ConfigDeclaration` (migration `0059`) — *what is tunable*, as opposed to
*what is tuned*.

**Declaring is deliberately NOT setting.** Seeding the default into a `ConfigEntry`
would pin it at the moment the box first booted, and every later change to the code
default would silently fail to apply anywhere that had ever run. A declaration carries
the default without materialising it, is idempotent (`register_module` runs every boot),
and shows the shipped default **beside** the set value — an operator comparing what they
changed against what shipped needs both.

The console editor now round-trips JSON and **refuses** a malformed edit rather than
storing the broken text. Scalars stay scalar; §23's "28" lesson is not undone.

## 5. Proven on the real box, not in a fixture

Against the running dev stack, through the real writer, the real enum, the real DB:

```
pickup   -> bol, seal, cargo_condition, damage
delivery -> bol, pod, cargo_condition, lumper_receipt, damage
  after capturing a seal:  seal ticked, nothing else moved
  outstanding: ['bol', 'cargo_condition']        # damage excluded, correctly

before:              ['bol','pod','cargo_condition','lumper_receipt','damage']
after operator edit: ['bol','pod','lumper_receipt','damage','seal']
pickup untouched:    ['bol','seal','cargo_condition','damage']
restored to default: ['bol','pod','cargo_condition','lumper_receipt','damage']
```

No deploy involved in that change. That is the requirement demonstrated rather than
asserted. Both probes rolled back / cleaned up; **dev carries no leftover state.**

## 6. Two tests were VACUOUS and the contrast check caught them, not review

- `does not render cargo condition twice` counted rows containing `"0/4"`. A stray
  `cargo_condition` row renders `load.doc.cargo_condition` — a missing i18n key, which
  never contains `"0/4"` — so the test **stayed green with the filter deleted**. It
  counts rows now: four document rows plus three fixed rows is seven, and the fifth
  configured item appearing makes eight.
- The first-pass answerability test would have passed on enum membership alone. It
  checks `DRIVER_DOC_TYPES` now, because `capture_document` is what actually refuses.

Every new UI assertion was run against reverted code before being trusted. 4 of 6 in the
checklist file bite; the per-item-sheet test bites; the two that do not are the
offline-fallback case and the one above, which is why the one above was rewritten.

## 7. The mechanism was in one more place than I first looked

Adding `seal`, `damage` and `lumper_receipt` to `DRIVER_DOC_TYPES` also puts them in the
**Docs tab's type chooser**, which renders `docs.type.<type>`. Three missing keys would
have shipped as three chips reading their own key names beside "BOL". Added in all six
locales, with a test.

Layout: the `LIVE_MOCKS` meter fixture was shape-matched to the endpoint (the §23 84/85
lesson) so every existing load state now sweeps the real five-row checklist rather than
the single-row fallback, and `load-checklist-capture` opens the sheet from a row. 205 →
209 states.

## 8. Exact next task

**A1 is complete except F12 queueing, which remains deliberately unbuilt** (recorded in
111). The next Group 1 item is the owner's call:

- **A2 is blocked on D5**, **A4 is blocked on D3** — owner-only decisions. The
  design-prd rule 6 delegation (§23 entry 118) does **not** cover them: v2.0 §6 is a
  different document.
- A3 and A12 are done. A5 and A9 are done but **A5 is still unvalidated by any driver
  who is not the owner**.

## 9. What I did NOT verify

- **Deployed, but no traffic has exercised it.** Both migrations ran clean on production
  and the restore was re-verified at the new head, so the SCHEMA is proven. What is not
  proven is the path: no request has hit `/load/{stop}/meter` on production since, and
  the checklist rows have never been rendered by a browser pointed at haulmeter.online.
- **No human has used the checklist.** No driver, and not the owner, has walked a real
  stop from capture to tick on a handset. A push on a real handset is now **seven**
  sessions old.
- **No human has driven the admin console panel.** It is a §18 portal, so it is outside
  the mobile-first layout sweep by design — five vitest cases are all that stands behind
  it. The JSON editor has never been typed into by a person.
- **The API/UI doc-type contract has no shared test.** The chooser's list arrives from
  the server and the vitest test supplies it; the api container cannot read `ui/`, so a
  type added server-side without a label here is still caught by nothing. Stated in the
  test itself rather than left implicit.
- `checklist_outstanding` is implemented and tested but **reaches no screen yet** — the
  same shape as M5-FR1's on-time verdict, which was computed for months and rendered
  nowhere. It is one function call from the Load tab if a future session wants the
  "what is still missing" sentence.

## 10. Restarting

```
make up          # preflight, then the full stack
make test        # 1345 pytest + 632 vitest — do NOT pipe it
make lint        # ruff + import-linter (30 contracts)
make ui-layout   # 209 states, ~4 min
```
