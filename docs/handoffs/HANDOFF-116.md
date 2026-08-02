# HANDOFF-116 — the walk works, and the product sent its first email

> **Stack DOWN · everything from `a4e282c` onward UNPUSHED · nothing deployed.**
> haulmeter.online still serves 112's code.
>
> **The question this session existed to answer: does a human adding a load, arming a
> stop and leaving actually get the finished paperwork, with the BOL in it? YES.** Walked
> end to end in a real browser against the running stack — real geolocation, real API,
> real database, nothing mocked. The card arrives ~10 s after the EXIT, the sheet opens
> over the Load tab, Send works, and the PDF a recipient opens contains the driver's BOL.
>
> **Walking it also found that this product had never sent an email.** Not one, ever.
> There was no SMTP gateway in the codebase; every counterparty send site passed a
> recording gateway, so the database said a notice was sent and nothing left the box.
> Mailpit had been wired into compose since session 0 holding **zero** messages. **Fixed
> in the same session** — Mailpit 0 → 1, and the link in that email returns the paperwork.
>
> That was the **fourth** built-and-inert engine. All four share one shape, now named in
> §23 entry 122: *a deferral that cannot fail is indistinguishable from a finished
> feature.*

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, ahead of `origin/main` by everything from `a4e282c` |
| `origin/main` | `f81bdd6` (verified by fetch, not inherited) |
| This session | `6019945` (the walk + its three fixes) · `9c96896` (the SMTP gateway) · doc commits |
| Gates | **pytest 1389 · vitest 658 · layout 221 checks over 55 states · import-linter 30/30** |
| Migrations | none this session. dev and production both `0059_f13_config_decl` |
| Working tree | clean apart from untracked `collect_files.py` (pre-existing, not mine) |
| Local stack | **DOWN** — brought down deliberately at the end of the session |
| Dev data | seeded at **Tampa 27.9506,-82.4572**; `infra/.env` now carries `PUBLIC_BASE_URL` and `SMTP_*` |
| Deploy | **not run.** A6, 114's preset fix, 115 and 116 are all absent from the box |

## 2. THE WALK — what a human actually sees

Driven with Playwright **inside** the ui container over `http://localhost:9008`, with
geolocation set programmatically (identical to DevTools Sensors) and the API reached by a
hostname rewrite only. Nothing was mocked; every endpoint, row and rendered byte is real.

| step | result |
|---|---|
| seed at Tampa, sign in via `/dev` | ✅ |
| add a load (Free time = 2 min, placed by "use my position") | ✅ |
| arrive — geofence ENTER | ✅ Meter foregrounds, `Free time 0:01:49` counting down |
| capture BOL from the checklist row | ✅ row flips to "BOL captured" |
| move 620 m away | ✅ **card appears ~10 s later** |
| card copy | ✅ *"You left DEV — Test Shipper. Your paperwork is ready."* + **Review & send** |
| legacy "N waiting" link | ✅ **absent** — the v1 defect has not regressed |
| Review & send | ✅ sheet opens **over** `/load`; the URL never changes (NAV-3 holds) |
| sheet contents | ✅ Paperwork · DEV — Test Shipper · **BOL captured** |
| Send | ✅ no error; the card clears |
| the email | ✅ **Mailpit 0 → 1** |
| the PDF behind its link | ✅ **HTTP 200 · `application/pdf` · 100,042 bytes**, no session needed |

**What is inside the document a recipient opens:**

```
title                     "Stop paperwork packet"     ← not "Stop record"
names the broker          Walk Test Brokerage         ✅
names the dock            DEV — Test Shipper          ✅
embedded image XObjects   2                           ← the driver's BOL photo IS in it
the word "Detention"      ABSENT                      ← A1: "explicitly not a claim"
BOL content hash in pack  True
```

**Phase DoD item 1 is now blocked only on a person.** The document exists, is correct, and
reaches a recipient. What remains is a driver who is not the owner doing it for real.

## 3. Three fixes the walk forced (`6019945`)

**The env did not describe itself.** Nothing anywhere said where the DEV facilities had
been seeded, so a browser spoofed to Tampa against pins seeded near Madison shows an empty
map — with both halves working exactly as built. That is the friction that started this
session. `make seed-where` now prints the ORIGIN to paste into Sensors, each facility's
distance from it, and the geofence radius an EXIT must clear. `make seed ORIGIN=..` is a
short alias for the long variable. Deliberately a CLI target and not a `/dev` panel: the
browser answer needs an API route that ships in the production image and is refused only
by an environment check — more surface than the question is worth (owner decision).

**The card showed the OLDEST draft, not the stop just left.** The queue arrives
oldest-first, which is right for the archive and wrong for a card whose headline is "You
left \<facility\>". With two drafts at the same dock the headline was word-for-word
identical while the sheet opened the *older* stop — its contents line reading "Nothing was
captured at this stop" while the BOL photographed minutes earlier sat in the newer packet.
**A driver would have sent the wrong, empty document with nothing on screen to notice
with.** My defect from 115, invisible to every test because every test had exactly one
packet. Fixed; one regression test, proved red.

**`PUBLIC_BASE_URL` was empty in dev**, so Send was refused with a plain "Not sent" —
correct behaviour (for a handoff the link IS the document), and it stopped J7-AP one step
short of the only question it exists to answer. Now set in `.env.example` with the
reasoning, so a fresh clone can complete the journey.

## 4. The fourth inert engine — no email had ever been sent (`9c96896`)

```
gateways that existed:  RecordingNotificationGateway   (an in-memory list)
                        StubNotificationGateway
                        WebPushNotificationGateway     (browser push)
SMTP gateway:           NONE — no smtplib, no EmailMessage, nothing
config:                 smtp_host = "mailpit", smtp_port = 1038   ← read by NOTHING
Mailpit total:          0 messages, ever
```

`send_counterparty_message` calls `gateway.send_email(...)`, and all seven send sites
passed `RecordingNotificationGateway()`, whose `send_email` appends to a list. The F8
thread and message rows were written faithfully, so **the database said the message was
sent.** Nothing left the box — not a Stop Packet, not a detention notice, not an on-time
proof, not an invoice.

What that cost, all past tense as of `9c96896`:

1. **Phase DoD item 1** was **unreachable** — the document was right and could not arrive.
2. **The detention wedge** (DoD item 3, actual payment) rides on M3's notice reaching a
   broker. It never had.
3. **Every "check Mailpit" step in DRIVE.md** — J0.7, J5.2, J7-AP 7–8, J12 — had always
   been unpassable. All unblocked now with what the walk measured.

### What was built

`SmtpNotificationGateway` + `counterparty_gateway()`, wired into all seven sites. Three
shape decisions, recorded as **§23 entry 122** so the next adapter matches:

- **The switch is the HOST, not a key.** Mailpit needs no credentials, and a dev box that
  silently stopped sending would put us straight back here. Blank `SMTP_HOST` to turn
  email off — which is exactly what `conftest` does, so the suite neither fills Mailpit
  nor lies about what was sent.
- **The choice is made at SEND time, not at import.** The API modules hold one gateway at
  module scope; deciding at construction bakes in whatever configuration the process
  started with, and the suite runs with email off while the app runs with it on. One
  frozen choice cannot serve both, and freezing the wrong one is silent.
- **A gateway may never fail its caller** (inherited from WebPush). An unreachable server
  is a transport fact, not a reason to lose the F8 row or 500 a driver who just tapped
  Send. The ref records `smtp-failed-<type>`, because a row claiming delivery it did not
  get is the lie the class exists to end.

**Measured:**

```
From          paperwork@haulmeter.online
To            ap@bolt.example
Subject       Stop paperwork
body          one plain line, one link
following it  HTTP 200 · application/pdf · 100,042 bytes
              2 embedded images (the BOL) · "Stop paperwork packet" · no "Detention"
```

**One correction to what this handoff first claimed:** `smtp_port=1038` is **right**, not
"probably wrong". Mailpit binds `MAILPIT_SMTP_PORT` inside the compose network as well as
on the host — verified with `netstat` in the container. The setting was correct all along
and simply had no reader.

## 5. Two things DRIVE.md asserted that were not true

**The three DEV pins never render together.** They are three facility *types*, so each
belongs to a different preset — measured against the real overlay endpoint:

| preset | DEV pins visible |
|---|---|
| **Drive** (the default) | Test Truck Stop only |
| Tonight | Truck Stop + Yard |
| **Work** | **Test Shipper** — the one J7-AP arms |
| Fuel / Service | none |

J0 and J2 both claimed all three render. **Seeing one pin on Drive is correct**, and the
shipper is invisible until you switch to **Work** — which no journey said. A second,
independent reason the flow felt broken.

**The Meter dev-tooling gap does not exist.** J4 step 4 guessed there might be no way to
compress free time so the colour boundaries could be watched. The load form has a **Free
time (min)** field beside Rate $/hr; set it to 2 and the whole free-time → amber →
accruing chain is watchable in about two minutes. No tooling was built, which is the best
available outcome for a gap that was hypothesised rather than measured.

DRIVE.md now carries all of this, plus the exact EXIT geometry (>150 m from the shipper,
≈0.0022 lat, then up to 60 s for a ping) and the instruction to arm a **fresh** stop.

## 6. A note for whoever next drives a browser here

`http://ui:9008` is **not a secure origin**, so Chrome refuses geolocation there outright
("Only secure origins are allowed") no matter what permissions are granted. Run the
browser **inside** the ui container against `http://localhost:9008` — localhost is a
secure context, and it is what the owner's browser uses anyway.

The layout harness's own AI-CONTEXT explains its denied geolocation as "Playwright denies
geolocation unless a context grants it". **That is wrong on the mechanism** — it is the
insecure origin, and granting permissions would not have changed it. The harness's
coverage of §15.5's degraded-location card is real but survives for a different reason
than recorded. Not corrected in code; noted here because the comment sends the next
person after the wrong thing.

## 7. The pattern, because this is the fourth one

Four built-and-inert engines have now been found in three sessions: the Stop Packet that
contained nothing, the doc-expiry reminder that reached no phone, the same reminder
landing on a tab root, and the email transport that did not exist. **They share a shape.**
The seam was modelled honestly. The adapter was deferred with a comment saying so.
Nothing ever failed to remind anyone.

`gateway.py`'s own docstring said *"the concrete FCM/Twilio/email adapters plug in at
activation"* — accurate, dated, and read by nobody for months. A deferral that cannot fail
is indistinguishable from a finished feature, and a green suite cannot tell them apart
either: it asserts the seam, and the seam is fine.

**`StubNotificationGateway` (SMS/Twilio) is the same pattern, still sitting there.** So is
`StubPaymentGateway` in F7. Neither is urgent; both should be assumed inert until someone
watches one work.

## 8. Exact next task

1. **The handset background-sensor test** (v2.0 DoD #8). Everything else in the A1 chain
   has now been walked and works; whether `/location/ping` fires unprompted while the app
   is backgrounded, screen off, over hours, **has never been observed by anyone**. It is
   nine sessions old and it is the last unproven link. A desktop tab cannot answer it.
2. **Push**, then decide on deploying. A deploy now also needs the **production SMTP
   settings** decided — otherwise the box runs with `SMTP_HOST` unset, falls back to
   recording, and is exactly where this session started.
3. **Two owner decisions still open, untouched by design:**
   - **claim-on-EXIT one-tap** — a §12.2 money act behind a Send.
   - **`register_flag`'s gate bypass** — fixing it at `add_gate` switches
     `a05_service_preset` OFF in production (the Service chip disappears from drivers'
     maps); raising instead takes the registry down at boot. A real fork, not a refactor.
4. Then the v2.0 board, which has not moved: **A2←D5 · A4←D3 · A7←D1 · A8←D7 · A10←D4**,
   A11 gated on A2, all seven decisions D1–D7 open.

**Phase DoD: 2 of 8.** Item 1's status changed twice in three sessions — unreachable by
construction → merely unmet → **blocked only on finding a driver.**

## 9. What I did NOT do

- **Nothing pushed, nothing deployed.**
- **No production email provider chosen** — dev is Mailpit; production is an owner
  decision and a `.env` change, not code. Nothing decides what happens to the queue when
  the provider is down.
- **No `/dev` seed-origin panel** — owner chose the CLI target.
- **Idempotency was not walked to completion.** The card clears on the first Send so there
  is nothing to double-tap there; the archive route is where a second tap is possible and
  the send path is idempotent by state (asserted in pytest). Worth five human minutes.
- **The offline and DRIVING variants were not walked** — both are asserted in vitest, and
  neither is a substitute for a handset.
- **The harness's wrong geolocation comment was left in place** (§6).
- **Exploratory draft packets were deleted from the dev DB** so the measured walk was
  clean. If a stop looks half-fixed, arm a fresh one.
- **The manual load form collects no load reference**, so the packet subject reads "Stop
  paperwork" rather than "Stop paperwork · \<ref\>". A1 req 4 is satisfied when a
  reference exists (the rate-con parse supplies one); the fallback form simply has no
  field. Noticed on the walk, not fixed — it is a form change and nobody asked.

## 10. Restarting

The stack is **down**. To come back:

```
make up                              # preflight, then the full stack
make seed ORIGIN=<lat>,<lon>         # wherever your browser is spoofed
make seed-where                      # ...and this tells you where that was
make test        # 1389 pytest + 658 vitest — do NOT pipe it
make lint        # ruff + import-linter (30 contracts)
make ui-layout   # 221 checks over 55 states, ~3–4 min
```

`infra/.env` now carries `PUBLIC_BASE_URL=http://localhost:8008` and the `SMTP_*` block.
Both are needed for J7-AP to complete: without the first, Send is refused; without the
second, no email is transmitted.

To see the whole chain without a phone: create a load at the DEV shipper with Free time 2,
tap **I've arrived**, capture a BOL from the checklist, then either move the spoofed GPS
>150 m away or use More → **Leave this stop**. Both draft the packet.

Nothing is waiting on a background job, an ingest, or a queue.
