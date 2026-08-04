# HANDOFF-117 — the product got an email provider, and the dock got a job on it

> **Stack DOWN · four commits UNPUSHED · nothing deployed.** haulmeter.online still
> serves 112's code.
>
> Two pieces of work, both starting from the owner rather than from the board.
>
> **Email has a real provider.** 116 sent the product's first email ever, to Mailpit,
> inside the box. This session it reaches a human inbox: Gmail SMTP, dev and production
> on one account, **verified by a real send the owner confirmed receiving**. No code
> changed — the gateway 116 built already did STARTTLS and `login()`. §23 entry 126.
>
> **The Load tab, from a screenshot of a real stop.** The owner reported "tapping on
> photos not working" and asked for the screen to be easier for drivers who are not
> tech-savvy. The bug was real and one line explains it. Underneath it were two larger
> things, one of which is **the fifth built-and-inert engine**: design-prd §5's
> **ON_SITE has been unreachable in a truck since the deriver was written.**

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, four commits ahead of `origin/main` |
| `origin/main` | `113327e` (verified by fetch) |
| This session | `c0b2346` · `51f88e7` · `aa5971c` · `84b4330` |
| Gates | **pytest 1391 · vitest 689 · layout 225 checks · import-linter 30/30** |
| Migrations | none this session. dev and production both `0059_f13_config_decl` |
| Working tree | clean apart from untracked `collect_files.py` (pre-existing, not mine) |
| Local stack | **DOWN** — brought down at the owner's request at the end of the session |
| Dev data | Tampa `27.9506,-82.4572`, intact from 116. `make seed-where` still prints it |
| Email | **Gmail, live in dev.** Mailpit is up in compose and no longer addressed |
| Deploy | **not run.** A6, 114's preset fix, 115, 116 and 117 are all absent from the box |

**A gap in the record, noted rather than papered over:** commits `bc8fb9b`, `d50529a`,
`34d2a42`, `113327e` (2026-08-03 — vendor-portal vitest gate, the lot-status card, the
scorecard eye, the login-screen language chooser) are **pushed and carry no handoff**.
Their decisions were logged as §23 entries 123–125, so the reasoning survives; the
session narrative does not. This file does not reconstruct it.

## 2. Email: the provider question is closed (`c0b2346`, `51f88e7`)

116 left "no production email provider chosen" open. It is **Gmail**, owner's decision,
**dev and production on one account** with the consequences accepted explicitly.

**No code changed.** The gateway from §23 entry 122 already did STARTTLS and
`smtp.login()`, and `test_smtp_gateway.py:90` already asserted the
`starttls → login → message` order. This was a `.env` shape and nothing more.

What the owner had saved was `GMAIL` and `GMAIL_APP_PASSWORD`, **read by nothing** —
settings bind `SMTP_*` (`core/config.py:50-60`), so those keys would have sat in `.env`
looking correct while `configured` stayed false and every send fell back to the
recording gateway. Converted in place; the App Password had its display spaces stripped
(Google shows `xxxx xxxx xxxx xxxx`, `smtplib` sends the literal string).

**Measured, not reviewed:** `counterparty_gateway()` picked `SmtpNotificationGateway`,
provider ref `smtp-1`, and **the owner confirmed the message arrived.** That is the
first time this product has reached a person outside the box.

Two failure modes are recorded in `.env.example` because both are silent:

- **Port 465 cannot work.** The gateway opens `smtplib.SMTP` then calls `starttls()`;
  implicit SSL hangs to the 10 s timeout and returns `smtp-failed-SMTPServerDisconnected`.
- **An unverified `SMTP_FROM` is rewritten, not refused.** Gmail replaces it with the
  authenticated account, so a mismatch ships a From line nobody chose while the F8 row
  records success. `SMTP_FROM` therefore equals `SMTP_USERNAME`.

**A send from dev is now a real send.** Recipients are pre-filled and editable, so a
live broker address typed into a test load emails an actual broker. Seeded
`@bolt.example` counterparties are safe — the TLD does not resolve. DRIVE.md J0.7
carries this warning, and its "check Mailpit" steps now point at the Gmail inbox.

## 3. The fifth inert engine — ON_SITE (`aa5971c`)

Chasing why the owner's screen had so few controls found this. §5's ON_SITE was
**reachable in tests and unreachable in a truck**, and had been since the deriver was
built. Three legs, all verified in code before anything was changed:

1. `/location/ping` returned **only edge events** — no steady-state presence field.
2. `location.js` was the only writer of `present: true`, on an ENTER edge, so presence
   existed only in the instant the crossing arrived.
3. `onSite` is a module-level `let`. **A reload set it back to false** with no edge left
   to restore it, and **`onArrive` never touched it** — so the "I've arrived" fallback,
   the path a driver takes *precisely when the background sensor did not fire*, produced
   ON_SITE never.

So every ON_SITE behaviour in the product was correct, tested, and dark — including the
one-tap cargo shortcut §23 entry 64 exists to provide, which is invisible in exactly the
moment it was designed for.

**The fact was already in the database.** F3 has written `GeofencePresence` rows with
`active` since the Foundation and nothing ever asked. `is_present_anywhere` asks;
`/location/ping` returns `present` on every ping; the client sets state from it and
`onArrive` sets it immediately, because the server writes a real ENTER for that tap
(`api/load.py:492`) and the fallback should not have to wait a minute for a sensor.

**An edge is a fact about a moment. A state has to be askable at any moment** —
including the first render after a cold start. That sentence is the whole bug.

## 4. The Load tab at the dock (`84b4330`)

**The reported bug.** `Photos 0/4` was a plain `<li>` with no handler while every
capturable row above it was a `.checklist__snap` button. Nothing failed when the owner
tapped it; there was no handler to fail. Now the same 48 dp glove target as its
neighbours, to the destination the More sheet already used.

**§10.2's missing rung (§23 entry 127).** The ladder ran Arm → Snap BOL → Send notice →
Generate claim, and *arrived · BOL filed · free time still running* — **most of a stop** —
fell off the end and rendered **no primary action at all**, on a tab whose anatomy
promises a state-dependent single CTA. It reads **"Take cargo photos 0/4"** now.

> **A defect the existing suite caught, worth keeping in view:** the first version gated
> on `!photosDone`, and `photosDone` is false when **nothing is required**. That
> promoted a photo task for stops whose checklist never asked for one — inventing a job
> and then grading the driver against it. Gated on `photosRequired > 0`. The old
> `ui-components` test failed and was right to.

**Facts and actions looked identical (§23 entry 128).** "Late 15:40" is a status;
"Photos 0/4" is a control; same size, colour and alignment. The only way to learn which
lines did something was to tap them — which is exactly how this arrived as a bug report.
Rows that act end in a `--text-3` chevron; rows that state a fact do not. **"Notice not
sent" stays deliberately inert:** a §12.2 money act belongs behind the CTA, never behind
a row a thumb brushes past.

**Three accent controls competed (§23 entry 129).** "Correct the appointment", "View all
evidence" and "More for this stop" were all `--shield-500` at label weight. Accent is now
the forward path; the rare repair steps to `--text-2` with an underline, keeping its
48 dp target and its shape as a control.

**Ordering that is load-bearing:** the money rung still outranks the photo rung once
detention accrues, and **DRIVING outranks both** — the app never asks a moving truck to
photograph anything. That last one is asserted at the surface, not only in `state.js`.

## 5. How this was tested

12 new UI tests, **proved red first**: 7 of 11 failed against the pre-change screen when
`LoadSurface.vue` was stashed. The other 4 pass vacuously against old code (there were no
buttons to over-reach) and were kept as guards. Plus 5 state tests, 1 sensor test and 2
API tests for presence-as-state.

**One coverage gap, stated rather than glossed.** The new CTA state has **no
layout-harness coverage**. The harness cannot reach ON_SITE — it gets no geolocation on
its origin (116 §6) and driver state is not in localStorage — and every route in would
add app surface for a test, which this project has refused before (116 §3, the seed
panel). The risk was measured instead: the longest render is **27 characters** (es, with
the count), **identical to `cond.start` in ru**, which the harness already measures in
the *narrower* rungs row. Bounded by proven shapes, not unmeasured. **If someone gives
the harness a driver-state hook, this state is the first thing to point it at.**

## 6. Exact next task

1. **The handset background-sensor test** (v2.0 DoD #8) — unchanged from 116, and now
   nine-plus sessions old. Whether `/location/ping` fires unprompted while the app is
   backgrounded, screen off, over hours, **has still never been observed by anyone**. A
   desktop tab cannot answer it. Note that §3 makes the fallback path work properly for
   the first time, which lowers the cost of that sensor failing — it does not answer it.
2. **Push, then decide on deploying.** A deploy needs **production `SMTP_*` added to
   `infra/.env` on the VM** — `deploy.sh:46` deliberately never ships it. Without it the
   box runs `SMTP_HOST` unset, falls back to recording, and is where 116 started. Note
   the box has none of 113–117, so production email needs the deploy before it needs the
   credentials.
3. **Two owner decisions still open, untouched:** claim-on-EXIT one-tap, and
   `register_flag`'s gate bypass (114 §7 — F13's central promise going unenforced).
4. Then the v2.0 board, which has not moved: **A2←D5 · A4←D3 · A7←D1 · A8←D7 · A10←D4**,
   A11 gated on A2, all seven decisions D1–D7 open.

**Phase DoD: 2 of 8.** Item 1 is unchanged in status — the document is correct, arrives,
and is now blocked only on a driver who is not the owner.

## 7. What I did NOT do

- **Nothing pushed, nothing deployed.**
- **Nothing decides what happens when Gmail is down or the quota is hit.** The gateway
  swallows the failure by design and records `smtp-failed-*`; nothing retries, nothing
  tells anyone, and free Gmail caps near 500 recipients/day — a ceiling this platform
  meets long before it meets its driver count.
- **No layout-harness state for the new CTA** (§5 above).
- **`StubNotificationGateway` (SMS) and `StubPaymentGateway` (F7) are untouched** and
  should still be assumed inert until someone watches one work. After five, the prior
  should be inert-until-observed, not correct-until-doubted.
- **The plain-language copy pass was not done.** The owner asked for a screen that is
  easier for drivers who are not tech-savvy; this session fixed structure (what is
  tappable, what the primary action is) and left vocabulary alone. "Capture cargo
  condition", "Generate claim", "Snap BOL" are still the app's words for things. That is
  a six-locale copy change and its own decision.
- **The harness's wrong geolocation comment is still in place** (116 §6).
- **ON_SITE was not walked in a browser.** It is proved by unit and API tests; nobody has
  watched the CTA appear at a real dock. Given what this session found, that distinction
  should be treated as load-bearing.

## 8. Restarting

```
make up                              # preflight, then the full stack
make seed-where                      # the Tampa origin is still seeded — paste into Sensors
make test                            # 1391 pytest + 689 vitest — do NOT pipe it
make lint                            # ruff + import-linter (30 contracts)
make ui-layout                        # 225 checks, ~3 min
```

`infra/.env` carries the live Gmail block; it is gitignored and was never committed. To
put dev back on Mailpit for a session where you want to read message bodies quickly:
`SMTP_HOST=mailpit`, `SMTP_PORT=1038`, `SMTP_STARTTLS=false`, then recreate the api
container.

To see the dock behaviour without a phone: create a load at the DEV shipper with Free
time 2, tap **I've arrived** — which now sets ON_SITE immediately — and the Primary
should read "Take cargo photos 0/4". Reload the tab; it must come back within one ping.

Nothing is waiting on a background job, an ingest, or a queue.
