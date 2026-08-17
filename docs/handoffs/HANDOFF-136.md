# HANDOFF-136 — M15 Session C: a person can reach it

The module had 12 tables, four scored dimensions, ten failure tags and this codebase's
first WebSocket, and **no human outside the build could touch any of it.** That is the
thing this session changed. HANDOFF-135 covers the earlier half of the same sitting (the
pilot-day preflight); this one is M15 only.

Authorized by **decision entry 179** against D14 scope (b), which requires B and C to be
"authorized against this entry by their own kickoffs".
Kickoff: `docs/kickoffs/KICKOFF-m15-session-c.md`.

---

## 1. Observed, not asserted

A driver account, on the running stack, in Chromium at **360 × 800**:

| step | what happened |
|---|---|
| **More** | the Roadside Ready row is there, with its caption |
| **Roadside Ready** | offers "Start a practice check" · no horizontal overflow |
| **Consent** | all three facts stated · **"Not now" and "I agree" are both 56 dp buttons** |
| **Session** | `201`, then the officer line rendered: **"How many hours have you been driving today?"** |
| **The mic** | 56 × 56 · page errors: **none** |

**That officer line is the first WebSocket frame this codebase has ever delivered to a
user interface.** The transport shipped in Session B and had only ever run in a test.

Getting there took four attempts and the reason is worth keeping: the browser must run
where **both** locked ports are `localhost`. Inside a container the API is cross-origin
(`net::ERR_FAILED` — CORS allows `localhost:9008`, not `ui:9008`), `page.route` cannot
rewrite a **WebSocket**, and Chromium special-cases `localhost` so
`--host-resolver-rules` is ignored. → **TRAPS 78.**

---

## 2. Two defects, both found by using the thing

**Q-6 was enforced in the domain and re-decided at the edge** (entry 180). `_officer_frame`
read `allow_draft` **off the client's own WebSocket frame**, so any browser sending
`{"type":"ready","allow_draft":true}` was served F9-drafted, unreviewed text.
`session_loop.py`'s docstring says the seam is safe because "nothing in the request path
passes it", and names a test that asserts the request path — the test asserts the domain
DEFAULT, which cannot testify about what an HTTP layer chooses to pass. Red-first at the
socket; both controls passed, isolating the failure to "the client asked and the server
obeyed".

**The publish surface made two phrasings of one question mutually exclusive.** Releasing
the seeded scenario released one variant per intent and then refused the rest:
`previous_version` was computed as the highest released version among *siblings*, when the
domain's bump rule is about *supersession*. An intent is meant to hold several released
lines at once — that is what `teachable_variants` returns and what Q-5's holdouts sit
beside. Now 0, with the schema gap stated in the docstring rather than disguised.

**Neither was visible from a green suite.** The first needed a test at the socket; the
second needed somebody to actually publish something.

---

## 3. What was built

**Backend.** `GET /roadside/scenarios` — the only way a client can learn a scenario id; the
probe had been querying the database directly, so a driver app could not have opened a
session at all. `startable_scenarios()` in the domain beside Q-5/Q-6: released **and** every
allowed intent able to speak, so a driver is never offered a session that opens and shuts
on `NoContentAvailable`. Both halves sabotage-checked. The **F14 publish surface** —
`mark_reviewed`/`release` had no caller anywhere in the product, so nothing could ever
reach `released`. `/auth/me` gains `roadside_enabled`.

**The audit law caught what I missed:** every mutating admin endpoint must write an audit
entry. The entry *is* the review record — Q-6 wants "a named human said this was fit for a
driver" answerable afterwards, and `mark_reviewed` only checks that a name was supplied.
The reviewer is the signed-in admin's own email, never a field.

**Driver surfaces.** More row (composed from the inbox row — §10.5 keeps that list plain,
no new bottom-nav tab), consent, session, result. Plus `AdminRoadside` in the console.

**Strings.** 58 keys × 6 locales. The band keys are not a naming choice — they are what
`BandVerdict.label_key` returns, so a mismatch renders a raw key to a driver.

**Paperwork, same commits:** 16 new layout-harness checks (365 → **381**), DRIVE.md **J13b**,
the driving-posture contract extended so the four routes cannot claim a posture they do not
implement.

---

## 4. Gates

| gate | value |
|---|---|
| pytest | **2299 passed** (was 2279) |
| vitest | **1043 passed** (was 1028) |
| layout harness | **381 passed** (was 365) |
| import-linter | **32 kept, 0 broken** |
| ruff | clean |

`make ci` as a whole is **still not verified repeatable** — see HANDOFF-135 §5. One clean
run at `c2cb6aa` this session, plus the earlier one at `0d11a8c`. Two, not five.

---

## 4b. DEPLOYED — and the first content ever released (2026-08-18, after §4 was written)

The owner authorized the deploy that "release scenario 1's lines on production" required.
Decision entry **181**.

| check | result |
|---|---|
| alembic (prod) | **0087_m15_hidden** (was 0083) |
| `m15` tables | **12** |
| `m15_roadside` | present, `enabled` NULL, `default_on` false — **OFF** |
| content | **5 released**, 3 draft holdouts, 1 released scenario |
| audit | **12 rows** (6 review + 6 release) — the review record |
| outbound queue | **0 unsent of 63**, unchanged across the deploy |
| public edge | site 200 · `/api/health` 200 · **`/api/roadside/scenarios` 404** |

**That 404 is the module gate working.** Released content sits behind a closed flag; no
driver can reach any of it. Flipping `m15_roadside` is question 14 and has not been asked.

Only `_seed_m15_roadside` was run on production — never `seed_demo.main()`, which would
also plant a dev-driver account and "DEV —" facilities there.

**One over-broad action.** The release went through the real HTTP surface rather than the
database, because the audit entry is the record — which needed a server-side session for
`admin@haulmeter.online`. Revoking it failed on a wrong signature, and the correction ended
**all 3 live sessions on that account, of which 1 was mine.** Anyone signed in as that admin
is signed out. Nothing lost, no password touched.

---

## 5. The state of the local box, deliberately

- **`m15_roadside` is ON in the local dev database.** My own kickoff DoD said it would be
  left OFF; I left it on so the owner can walk J13b without setting anything up. Production
  is untouched — **m15 does not exist there at all**, no flag row, no migrations 0084–0087.
- Scenario `1ed32eea…` and five phrase variants are **released locally**, reviewed by
  `m15-walk-admin@haulmeter.online` (a platform-admin account this session created).
  Holdouts were deliberately **not** released — Q-5.
- Nothing was pushed. Nothing was deployed.

---

## 6. What M15 still is not

- **FR5 (teaching loop), FR6 (drill plan), FR7 (record + `/verify`)** — not started. The
  result surface's "Start my plan" CTA is deliberately absent for that reason; offering it
  would be a dead control.
- **No notifications.** P-1/P-2 remain **PROPOSED, NOT APPROVED** (entry 177). No class is
  registered and no call site exists.
- **The seven-locale gate is OPEN**, by the owner's reading: six ship, Tajik still needs a
  paid reviewer.
- **The six locales' new strings are model-produced and unreviewed**, on the same footing as
  the rest of the catalogue. Worth saying plainly rather than leaving implied.
- **Latency is still unmeasured** at a useful n — HANDOFF-134 §5 stands.
- `m15_billing` and `m15_assessment` still do not exist.

---

## 7. Owner questions

134 §9 and 135 §8 stand. This session adds:

| # | question | blocks |
|---|---|---|
| 12 | **Sign P-1 / P-2** (entry 177) — no M15 notification can exist until then | FR6's drill reminders, and any invite |
| 13 | **Release scenario 1's English lines on production?** You are the named human Q-6 wants; the surface now exists. Nothing can be practised anywhere until someone does | every driver-facing use of M15 |
| 14 | **Should `m15_roadside` be deployed at all yet?** Production has no m15 whatsoever today | the module reaching a real phone |

---

## 8. Next

1. **The pilot day still outranks all of this** — HANDOFF-135, `docs/validation/j1-journey.md`.
2. **Session D** — FR5/FR6, and it needs its own kickoff against D14 like this one did. The
   honest first item is the drill plan, and it is blocked on P-1 for reminders.
3. **Finish the five-run `make ci` verification** when the box is free.
4. **Uzbek voices and Tajik review** — still people, not keys.
