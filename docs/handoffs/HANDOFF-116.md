# HANDOFF-116 — the walk works, and nothing this product writes has ever been sent

> **Stack UP · everything from `a4e282c` onward UNPUSHED · nothing deployed.**
>
> **The headline, because it is what the session existed to answer: YES.** A human adds a
> load, arms a stop, photographs a BOL, drives away — and the review card arrives on the
> Load tab about ten seconds later, the sheet opens over it, Send works, and **the
> driver's BOL is in the PDF.** Walked in a real browser against the running stack with
> real geolocation, the real API and the real database. Two sessions of work function.
>
> **The second headline is worse than the first is good. There is no SMTP gateway in this
> codebase.** No email has ever been sent — not a Stop Packet, not a detention notice, not
> an on-time proof, not an invoice. Mailpit has been wired into compose since session 0
> and has received **zero** messages. That is §6, and it is the fourth inert engine.

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, ahead of `origin/main` by everything from `a4e282c` |
| `origin/main` | `f81bdd6` |
| This session | `6019945` + this handoff |
| Gates | **pytest 1383 · vitest 658 · layout 221 checks over 55 states · import-linter 30/30** |
| Migrations | none. dev and production both `0059_f13_config_decl` |
| Local stack | **UP**, seeded at Tampa (27.9506,-82.4572) |
| Deploy | **not run.** The box still serves 112's code |

## 2. THE WALK — what a human actually sees

Driven with Playwright inside the ui container over `http://localhost:9008`, geolocation
set programmatically (identical to DevTools Sensors), the API reached through a hostname
rewrite only. **Nothing was mocked.**

| step | result |
|---|---|
| seed at Tampa, sign in | ✅ |
| add a load, Free time = 2 min, placed by "use my position" | ✅ |
| arrive (geofence ENTER) | ✅ Meter foregrounds, `Free time 0:01:49` counting down |
| capture BOL from the checklist row | ✅ row flips to "BOL captured" |
| move 620 m away | ✅ **card appears ~10 s later** |
| card copy | ✅ *"You left DEV — Test Shipper. Your paperwork is ready."* + **Review & send** |
| legacy "N waiting" link | ✅ **absent** — the v1 defect has not regressed |
| Review & send | ✅ sheet opens **over** `/load` (URL never changes — NAV-3 holds) |
| sheet contents | ✅ Paperwork · DEV — Test Shipper · **BOL captured** |
| Send | ✅ no error; card clears |
| **the PDF** | ✅ **99,747 bytes · `application/pdf` · HTTP 200 from the share link with no session** |

**What is inside the document a recipient opens:**

```
title                     "Stop paperwork packet"     ← not "Stop record"
names the broker          Walk Test Brokerage         ✅
names the dock            DEV — Test Shipper          ✅
embedded image XObjects   2                           ← the driver's BOL photo IS in it
the word "Detention"      ABSENT                      ← A1: "explicitly not a claim"
BOL content hash in pack  True
```

**Phase DoD item 1 is now blocked only on a person, not on the code.** The document a
recipient could use exists and is correct. It cannot yet *reach* them — §6.

## 3. Three fixes the walk forced (all in `6019945`)

**The env did not describe itself.** Nothing said where the DEV facilities had been
seeded, so a browser spoofed to Tampa against pins near Madison shows an empty map with
both halves working exactly as designed. `make seed-where` now prints the ORIGIN to paste
into Sensors, each facility's distance, and the geofence radius. `make seed ORIGIN=..` is
a short alias. Deliberately a CLI target rather than a `/dev` panel: the browser answer
needs an API route that ships in production and is refused only by an environment check —
more surface than the question is worth (owner decision).

**The card showed the OLDEST draft, not the stop just left.** The queue arrives
oldest-first, right for the archive and wrong for a card whose headline is "You left
<facility>". Two drafts at the same dock produced a word-for-word identical headline while
the sheet opened the *older* stop — contents reading "Nothing was captured at this stop"
while the BOL photographed minutes earlier sat in the newer packet. **A driver would have
sent the wrong, empty document with nothing on screen to notice with.** My defect from
115, invisible to every test because every test had exactly one packet. One regression
test, proved red.

**`PUBLIC_BASE_URL` was empty in dev**, so Send was refused with a plain "Not sent" —
correct behaviour, and it stops J7-AP one step short of the only question it exists to
answer. Now set in `.env.example` with the reasoning.

## 4. Two things DRIVE.md asserted that are not true

**The three DEV pins never render together.** They are three facility *types*, so each
belongs to a different preset — measured:

| preset | DEV pins |
|---|---|
| **Drive** (default) | Test Truck Stop only |
| Tonight | Truck Stop + Yard |
| **Work** | **Test Shipper** — the one J7-AP arms |
| Fuel / Service | none |

J0 and J2 both claimed all three render. **Seeing one pin on Drive is correct**, and the
shipper is invisible until you switch to Work — which no journey said. This is a second,
independent reason the flow felt broken.

**The Meter dev-tooling gap does not exist.** J4 step 4 guessed there might be no way to
compress free time. The load form has a **Free time (min)** field beside Rate $/hr; set it
to 2 and the whole free-time → amber → accruing chain is watchable in two minutes. No
tooling was built, which is the best outcome available for a gap that was hypothesised
rather than measured.

## 5. A note for whoever next drives a browser in this repo

`http://ui:9008` is **not a secure origin**, so Chrome refuses geolocation there outright
("Only secure origins are allowed") no matter what permissions are granted. Run the
browser **inside** the ui container against `http://localhost:9008` instead — localhost is
a secure context. The layout harness's own AI-CONTEXT explains its denied geolocation as
"Playwright denies geolocation unless a context grants it"; that is wrong on the
mechanism. Its coverage of §15.5's degraded card is real but survives for a different
reason than recorded, and granting permissions would not have broken it.

## 6. OPEN, AND IT IS THE BIGGEST ONE YET — nothing is ever emailed

```
gateways that exist:  RecordingNotificationGateway   (an in-memory list)
                      StubNotificationGateway
                      WebPushNotificationGateway     (browser push)
SMTP gateway:         NONE — no smtplib, no EmailMessage, nothing
config:               smtp_host = "mailpit", smtp_port = 1038   ← read by NOTHING
Mailpit total:        0 messages, ever
```

`send_counterparty_message` calls `gateway.send_email(...)`, and every caller in the
product passes `RecordingNotificationGateway()`, whose `send_email` appends to a list.
The F8 thread and message rows are written faithfully, so the database says the message
was sent. **Nothing leaves the box.**

What this costs, in order of severity:

1. **v2.0 Phase DoD item 1** — "a driver who is not the owner has sent a Stop Packet that
   a real recipient could use" — is **unreachable**. The document is right; it cannot
   arrive.
2. **The detention wedge (DoD item 3, actual payment)** rides on M3's notice reaching a
   broker. It never has.
3. **Every "check Mailpit" step in DRIVE.md** — J0.7, J5.2, J7-AP, J12 — has always been
   unpassable. Marked blocked, not failing.
4. `smtp_port` defaults to **1038**, the *host-published* port; Mailpit inside the network
   listens on `MAILPIT_SMTP_PORT`. So even the unused setting is probably wrong, which is
   itself evidence nothing ever connected.

**Not built here, deliberately.** It is a new provider seam plus a production decision
(which real email provider, what deliverability story, what happens to the queue when it
is down) and this was a verification session. It is the next task.

## 7. Exact next task

1. **Build the SMTP gateway** (§6). The dev end is Mailpit and already in compose; the
   production end is an owner decision. Until this exists, no amount of correct document
   generation reaches anybody.
2. **Then the handset background-sensor test** (v2.0 DoD #8). Unchanged in importance —
   this session proved the chain works *given positions*; whether positions arrive
   unprompted on a real phone is still unanswered and untested, nine sessions old.
3. **Push**, then decide on deploying.
4. Still awaiting an owner decision, untouched by design: **claim-on-EXIT** (§12.2 money
   act) and **`register_flag`'s gate bypass** (fixing it switches the Service chip off in
   production; raising takes the registry down at boot).

## 8. What I did NOT do

- **No SMTP gateway** (§6) — the finding, not the fix.
- **Nothing pushed or deployed.**
- **No `/dev` seed-origin panel** — owner chose the CLI target.
- **The idempotency step was not walked to completion.** The card clears on the first
  Send, so there is nothing to double-tap there; the archive route is where a second tap
  is possible and the send path is idempotent by state (asserted in pytest). Worth a
  human's five minutes rather than another scripted walk.
- **The offline and DRIVING variants were not walked** — both are asserted in vitest;
  neither is a substitute for a handset.
- **Exploratory drafts were deleted from the dev DB** so the measured walk was clean. If
  a stop looks half-fixed, arm a fresh one (DRIVE.md now says so).

## 9. Restarting

```
make up
make seed ORIGIN=27.9506,-82.4572   # or wherever your browser is spoofed
make seed-where                     # ...and this tells you where that was
make test        # 1383 pytest + 658 vitest — do NOT pipe it
make lint        # 30 contracts
make ui-layout   # 221 checks over 55 states
```

To see the card without a phone: create a load at the DEV shipper with Free time 2, tap
**I've arrived**, capture a BOL from the checklist, then More → **Leave this stop**.
Nothing is waiting on a background job, an ingest, or a queue.
