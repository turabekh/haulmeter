# HANDOFF-135 — the pilot day, checked before the pilot day

A short session and not a build one. The stack came back up after HANDOFF-134's break, and
the time went to the top item on 134 §8 — **the pilot day** — in the only way a session can
touch it: by removing the reasons the afternoon would fail for something other than the
driver.

**No product code changed.** Three documents, two TRAPS entries, one dev-database flag
alignment, and a verification that was owed.

---

## 1. The stack is up

`make up` from cold. Verified on the box rather than reported:

| check | result |
|---|---|
| containers | api · worker · ui · postgres · redis · minio · mailpit, all running |
| `migrate` | exit **0** |
| alembic head (dev) | **0087_m15_hidden** |
| `/health` | 200 · `{"status":"ok","environment":"dev"}` |
| UI | 200 on :9008, and it **renders** — see below |
| worker | started, 13 jobs, first sweep clean |
| outbound queue | **0 unsent of 80**, unchanged across the recreate |

A 200 from vite is not a rendered app, so the login surface was booted in a real browser at
**360 × 800**: it renders, no horizontal overflow, no page errors. The one console line is
the dev server returning `sw.js` as `text/html` — the service worker is exercised by
`make ui-pwa` against a real build, not by the dev server, so it is noise here.

---

## 2. Production, read read-only

Nothing was mutated. Every row below came from a `select` on `haulmeter-test`
(`uzimiz-prod` / `us-central1-a`) on 2026-08-17.

| what | measured |
|---|---|
| `j1_contact_parse` · `j1_fee_disclosure` | **ON** — the validation doc's claim is true |
| `j1_arrival_nudge` | NULL → `default_on` false = **OFF** |
| `f09.ai_call` `f05.document_parse` | **57 calls, last 2026-08-16** |
| `f08.outbound_message` | **0 unsent** of 62 |
| `f05.stop` | 27 armed · 18 with an appointment · **0 in the future** |
| `f08.push_subscription` | **0 rows** |
| `f13.validation_gate` | no gate on any `j1_*` flag |
| alembic head (prod) | **0083_receivable_kind_fee** |
| accounts | 181 |
| services | all Up; **mailpit still among them** (134 §9 q8, unchanged) |

**Production is four migrations behind local and that is correct** — 0084–0087 are M15,
which is deliberately unshipped. Nothing in Journey 1 needs them.

**The rate-con parse works on production with a real key.** 57 `document_parse` calls, the
most recent the day before this session. Line 1's machine half is not a hope.

---

## 3. Two findings that would have cost the pilot day

**Line 5 is self-blocking as written.** `dispatch_arrival_reminders` returns `[]` while
`j1_arrival_nudge` is off, and the line's clearing condition in `j1-journey.md` is that the
observation *gates the flag ON*. Nothing can be observed. The flag is **global**, so the
real question is blast radius — and it is measurable: **0 armed stops have an appointment
in the future**, against a `[now, now + 15 min]` reminder window. Turning it on today sends
to nobody but the pilot driver, and the flag carries **no validation gates**, so
`/admin/flags` will not refuse. Afterwards `clear_decision` hands it back to the code
default; `disable()` would write False and the declared default could never apply again.

**`f08.push_subscription` is empty on production.** No handset has ever registered. The
flag alone would still deliver nothing — the pilot phone granting notification permission
is a *separate* precondition, and it will be the first row in that table.

Neither is a session's call. Both are in the runbook as owner decisions.

---

## 4. What changed

**`docs/validation/j1-pilot-runbook.md`** (new) — the operator's half of the pilot day:
the preflight above with its verbatim query, the two decisions owed before the day, the
five lines in the order that leaves each one's state for the next, what evidence to capture
per line and what disqualifies it, and the two lines that *cannot* close that day (3 needs
n≥5 dock data; 7 is a broker's calendar, and its observable is the Money row showing
gross · fee · net, not a notification). `j1-journey.md` gained a pointer to it.

**It does not duplicate `WATCH.md`.** WATCH.md owns *how to watch* — its ONE RULE governs
the day. This is the technical half: flags, keys, subscriptions, queue state.

**TRAPS 69a** — `exec` into the long-lived `ui` container is not exempt from trap 69, and
fails in a shape that argues against it: the browser binary survives in the `playwright`
named volume while the apt libraries die with the rebuilt container, so the cache looks
warm and Chromium still cannot find `libglib-2.0.so.0`.

**TRAPS 77** — `make ci` cannot be run twice in a row; it ends by leaving `ui` (and
`test-api`'s postgres/redis) up, and it begins with a preflight that demands those ports
free. `make down` between runs is part of the harness. This is recorded because the thing
most likely to be run repeatedly is a repeatability check, and four identical port failures
in runs 2–5 look exactly like a finding.

**Dev database only:** `j1_contact_parse` and `j1_fee_disclosure` set to `true` locally to
match production. Both are gate-less, so this is what `enable()` writes. Before this, all
four `j1_*` flags resolved OFF locally and **a local rehearsal would have shown a product
without the contact prefill or the fee disclosure** — the wrong thing to practise on.
`j1_arrival_nudge` left NULL, as on prod.

---

## 5. The five-run `make ci` verification

134 §2 recorded this as owed: one clean run at `0d11a8c`, and three attempts at the
five-run confirmation that never completed — twice invalidated because the tree moved while
they ran.

Run from a clean tree at **`c2cb6aa`**, committed first, with `make down` before each run
(§4, TRAPS 77) and the stack restored by `make up` at the end.

> **RESULT: see the table appended at the close of this session.** It is written from the
> raw per-run logs in the session scratchpad (`ci-run-1.log` … `ci-run-5.log`), never from
> memory, and a single red run in five is the answer to the question — not a reason to
> re-run.

---

## 6. What did NOT happen

- **No line in `j1-journey.md` moved.** A runbook is not an observation. All seven are open.
- **No M15 work.** No UI, no locale strings, nothing deployed; `m15_roadside` still absent
  from production entirely.
- **Nothing was pushed or deployed.** Production was read and never written.
- The Uzbek clips (134 §8 item 2) still need a native speaker, and the Tajik draft still
  needs a paid reviewer.

---

## 7. Next

1. **The pilot day.** It now has a runbook and a measured preflight. It still needs one
   driver, one broker, one afternoon — and the two decisions in the runbook §2.
2. **Play the three Uzbek clips** — `docs/voice-samples/`. A person, not a key.
3. If M15 continues, **Session C needs its own kickoff against D14**, and the honest first
   item is still the UI.

---

## 8. Owner questions

All nine in **134 §9** stand unchanged. This session adds two, both scoped to the pilot day
and both in `j1-pilot-runbook.md` §2:

| # | question | blocks |
|---|---|---|
| 10 | **Flip `j1_arrival_nudge` ON for the pilot window?** Blast radius measured at nil; no gates; reversible with `clear_decision` | line 5, and it is the only line that gates a flag |
| 11 | **Which broker inbox receives the first real claim?** LIVE-FIRE — a real agreed recipient, named before the day | line 6 |
