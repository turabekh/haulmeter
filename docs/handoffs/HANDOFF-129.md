# HANDOFF-129 — live, and measured on the box rather than reported

**Deploy session.** Journey-1 Session A (A1/A2/A3) is on production, both J1 flags are ON,
and the SMTP cutover close-out shipped with it. Everything below was proved by querying
the box or by driving the real site in a browser; nothing here rests on a deploy script's
exit line.

**Two premises in the brief were stale, and measuring them first is what made the session
short.** Session A had already been pushed and deployed earlier — `origin/main` was at
`3212609` and production was already at **0081**, not 0080. So steps 1–3 were mostly
confirmation, and the substance of the session was the verification, the flag flip, and
the SMTP close-out that had not yet been written. HANDOFF-128's shape holds: a brief is a
snapshot, and on this codebase the re-grep is the work rather than a preamble to it.

---

## 1. What is on production now

| | |
|---|---|
| `origin/main` | **`6506eff`** (Session A `224e1d5`/`32a63e4`/`6c3506f` + handoff `3212609` + SMTP close-out `6506eff`) |
| alembic head | **0081_driver_profile_mpg** — queried, not read from migration output |
| `f01.driver_profile.mpg` | `numeric(3,1)`, nullable ✅ |
| `f05.counterparty.contact_email` / `contact_phone` | `character varying`, nullable ✅ |
| `rate_con_parse` prompt | **v2 ACTIVE** (1537 chars, created 2026-08-16 05:09); **v1 still on record** (748 chars, 2026-07-26) |
| `j1_contact_parse` | **enabled=True** |
| `j1_preaccept_intel` | **enabled=True** |
| `m14_overlay` | `enabled=NULL` — untouched, as instructed |
| gates before push | pytest **2076** · vitest **999** · layout **365** · import-linter **31/31** |

Edge, from the public internet: `https://haulmeter.online/` 200 with a valid cert,
`manifest.webmanifest` 200, `sw.js` 200, `/api/auth/me` 401 (alive + auth), the new
`/api/intel/pre-acceptance/{id}` 401 against a control path returning 404 — so the route
exists rather than being swallowed. The served bundle `/assets/index-CkpxafbR.js` contains
`pre-acceptance`, `rc__readabsent`, `load.terms.title` and `equipment.mpg`.

---

## 2. The prompt-registration fix, proved in the wild

This is the one that could only ever be proved on production. `register_rate_con_prompt`
used to read `if get_active_prompt(...) is None`, and `parse_structured` runs the template
stored in the **database** — so on any box that had ever parsed a rate con, editing
`PROMPT_TEMPLATE` shipped green and changed the live parse not at all.

Registration is lazy (first parse, not boot), so immediately after deploy the box still
had **v1 only**. One rate-con parse through `POST /api/load/import` was enough:

```
v1 active=True len=748  created 2026-07-26 11:55
v2 active=True len=1537 created 2026-08-16 05:09   <- ACTIVE
active matches the shipped constant : True
active prompt asks for email/phone  : True / True
```

The earlier wording is preserved on its own row, which is the whole point of versioning a
prompt: an `AiCall` from July is still readable against the text that produced it.

**KNOWN AND INTENDED, not a bug:** because the prompt now advances on deploy, **extraction
of `counterparty_email`/`counterparty_phone` is live for every new parse regardless of the
flag.** `j1_contact_parse` gates only whether the DRAFT carries the contact to the confirm
screen. This is additive — the fields are extracted and then withheld — and it is
deliberate: switching the flag on exercises a path that has already been running, rather
than one nobody has ever executed. Do not "fix" it.

---

## 3. Seen rendering, not inferred

Four checks driven in a real Chromium at **360 × 800** against `https://haulmeter.online`
as the owner account, with a fictional rate con (invented broker, `@example` address; the
docks are real production facilities). All four green:

- **A1** — the confirm screen arrives with `ap@cardinal-freight.example` in Broker email
  and `7045550134` in Broker phone. The parse filled a field the driver used to type.
- **A2 (en)** — the reading block states `This load pays $2,450.00`, `Detention $65.00`,
  `Free time 120`; the contract's own wording sits beside it with the note explaining why
  it is English, and `lang="en"` on the clause text.
- **A2 (uz)** — *Biz o'qigan pul shartlari · Bu yuk to'laydi $2,450.00 · Kutish (detention)
  $65.00 soatiga · Bepul vaqt 120 daqiqa*, with no English leak into the reading, and the
  clauses still verbatim English. `detention` stays English inside the Uzbek label, which
  is §12.3's glossary rule working rather than a missed translation.
- **A3** — nothing renders before a dock is chosen; picking one that clears the floor
  renders **"Ran past 120 free minutes · 0 / 5 · tracked stops"**. A raw pair, no
  percentage, naming the free time it was counted against.

The smoke spec and its fixtures were deleted afterwards — a file with a hardcoded
production URL is a liability sitting in a public repo. The technique (mint a short-lived
F1 session for the owner, inject it into `localStorage` as `longhaul.session`, point
Playwright at the live host) is recorded here so the next session can repeat it in ten
minutes. **Playwright needs `--with-deps`** — I hit `libglib-2.0.so.0` again mid-session
by trimming it off a re-run, which is TRAPS entry 60 for at least the fifth time.

The ops session token was revoked explicitly rather than left to expire.

---

## 4. Both floor directions, on real production data

Asserted through the live HTTPS endpoint, not in CI:

| facility | paired samples | `risk` |
|---|---|---|
| `ebe8cc85…` CLORL - Christie Lites Orlando | **5** | `{"exceeded": 0, "sample_size": 5, "free_time_minutes": 120}` |
| `e0e09bad…` FREIGHT MINDS NJ WAREH | 3 | **`null`** |

`best_hour` is `null` even on the n=5 dock, because no single hour bucket clears the floor
— the two halves are independently absent by design, and this is that design visible.

**I nearly reported the opposite, and the error was mine.** My first sweep used
`select(Facility).limit(4000)` against a table holding **18,333** rows, so it missed the
only qualifying facility and I was about to record "no facility on production meets the
floor". The raw ENTER counts contradicted it, which is what forced the recount. A scan
with a limit is a scan that can be confidently wrong about absence.

---

## 5. Two data-health findings the flip made visible

Neither is a regression from this deploy; both now have a user-visible consequence.

1. **47 unclosed visits — 69 ENTER against 22 EXIT platform-wide.** `dwell_samples` pairs
   ENTER→EXIT and skips an ENTER with no following EXIT, so an unclosed visit contributes
   nothing. `Harvest Foods DC` has 8 ENTERs and **one** usable sample. This is the dominant
   reason the pre-acceptance intel will render for almost nothing today: arrivals are
   detected, departures largely are not. **Worth a session on its own** — it suppresses M2
   dwell stats, M8 risk and the appointment-hour read simultaneously.
2. **Duplicate facility rows split what history there is.** `Metro Market Warehouse` holds
   one sample on each of two rows; the confirm screen offered two `Harvest Foods DC /
   Dallas, TX` candidates rendered identically, which is entry 76's unanswerable question
   back on screen. Modest in volume, but it is the mechanism that keeps samples below a
   floor they would otherwise clear.

Consequence for the pilot: **with both flags on, exactly one facility in production can
render a risk pair today.** The feature is correct and nearly invisible, and that is the
floor doing its job rather than a fault. A driver will see it when the dock has history.

---

## 6. Rollback posture

- **Surfaces** roll back by flipping the two flags OFF — `flags.disable(db, key)` or
  `/admin/flags`. Both are read-only surfaces; nothing is written that a flip cannot hide.
- **0081 is additive** and nullable. No down-migration is planned; `downgrade()` exists and
  drops the column, but nothing needs it — an unread nullable column costs nothing.
- **Prompt v2** rolls back by REGISTERING v1's wording as v3 (`ai.register_prompt(db,
  "rate_con_parse", ai.AiTask.document_parse, <v1 template>, version=3)`), because
  `get_active_prompt` orders by version descending. **Do not delete or deactivate the v2
  row** — the `AiCall` rows made under it must stay readable against the text that made
  them. Documented here; not done.
- **SMTP** rolls back by restoring `/opt/haulmeter/infra/.env.bak.20260816T043040Z` and
  force-recreating `api` and `worker`.

---

## 7. The baseline delta, resolved

HANDOFF-128 quoted a pre-Session-A baseline of vitest 972 / layout 357 without saying
where it came from. Traced:

| commit | vitest | layout | source |
|---|---|---|---|
| `784e2c1` map basemap fallback | 962 → **969** | 353 → **357** | `ui/test/map-no-basemap.test.js` (+7); +29 lines in `layout.spec.js` (+4 checks) |
| `9695a0a` skeleton reserve | 969 → **972** | 357 (unchanged) | `ui/test/loading-state.test.js` (+3) |

Both pre-date Session A. Session A then took vitest 972 → 999 and layout 357 → 365.

---

## 8. SMTP cutover close-out (shipped in `6506eff`)

Sending identity is `claims@haulmeter.online`; transport unchanged (`smtp.gmail.com:587`,
STARTTLS, Gmail in every environment, no Mailpit). Owner confirmed **SPF PASS · DKIM PASS
`d=haulmeter.online` · DMARC PASS**. Placeholders and the settings default now track the
real mailbox; historical handoffs and earlier log entries naming the old address were left
alone, because a handoff is a dated record and the log is append-only. Decision entry 164
carries the reasoning, including the two things worth remembering: **`SMTP_FROM` also sets
the Message-ID domain**, so a cutover that changes only credentials misaligns DMARC; and
**a credential change has no deploy path** — `deploy.sh` excludes `infra/.env` by design,
so it is placed on the box or it has not happened.

---

## 9. Unchanged, and next

- **Session B** is the next build step: B1 (arrival nudge + the on-time consent toggle that
  exists and has no UI caller — `m05_protection.py:1039,1059`) then B2, which is blocked on
  the owner ruling below.
- **J1-D3.1 still needs the owner's ruling** — the fee ledger row contradicts the logged
  rationale at `m09_money/domain/service.py:415-442`. Unchanged from HANDOFF-128 §3.
- **J1-D2** needs restating: day-21 gating is already done; the real gap is that an ungated
  day 21 sends nothing where D2 wants the firm follow-up.
- **The pilot day and D13** are unchanged owner-track items.
- **`make ratecon-eval` still has no corpus.** The runner works; the ≥10 anonymized real
  rate cons remain the one thing that would let anyone say how often the extraction is
  right on real paper. Everything asserted about extraction quality so far — including this
  session's production parse — used documents I wrote.
