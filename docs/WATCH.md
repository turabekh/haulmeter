# WATCH.md — driver comprehension protocol

**What this is.** The observation half of DRIVE.md. DRIVE.md asks *does it work?* and you answer it
in a browser. WATCH.md asks *can a driver follow it?* and only a driver can answer it.

**Why it exists.** PRD v2.0 A10 requirement 2: *"Walk the detention flow with a driver end to end.
**Record where they stop, not what they say.**"* Three drivers independently said "easy to follow"
about three different features. That is a symptom report, not a specification — it could mean labels,
ordering, decision count, vocabulary, or not knowing the feature was there. Those have four different
fixes and three of them make the others worse. This document turns the symptom into a defect list.

**What it produces.** A stop-point log. Not opinions, not ratings, not a survey — a list of the exact
moments a driver hesitated, tapped the wrong thing, went back, or asked you something. That list is
the input to A10 and the evidence behind owner decision **D4**.

**What it unblocks.** Phase DoD items 1 and 2 (A1 packet sent by a non-owner driver; ≥20 lot-status
reports from non-owner drivers) both require a driver using the app anyway. This is not extra work —
it is work already owed, done in a way that also produces a design spec.

---

## THE ONE RULE

**Give the instruction. Then say nothing.**

Every other rule in this document is a consequence of that one. The moment you explain, hint, point,
or "just quickly show" — the session is over as evidence. You can restart it as a demo if you like,
but stop logging.

Silence is uncomfortable for about eight seconds and then it becomes the most valuable data you will
get all month.

---

## Rules of use

1. **Three drivers minimum, five is better.** One driver stopping somewhere is a note. **Two drivers
   stopping at the same place is a defect row.** That threshold is the whole method — it is what
   separates a preference from a problem.
2. **Their phone, not yours.** §20 specifies a ≤$180 Android as the baseline device. A driver's own
   handset carries their font scale, their screen brightness, their cracked glass, and their network.
   Yours does not.
3. **Never demo first.** Not a walkthrough, not an orientation, not "so this is the Load tab." A
   driver who has been shown the app cannot tell you whether the app explains itself.
4. **Record where they stop, not what they say.** Drivers are polite and they rationalise. *"Oh I
   see, that makes sense"* three seconds after a four-second hesitation means the hesitation was
   real and the sentence is noise. Log the hesitation.
5. **Do not fix anything during the session.** Note it, help them past it, keep going. A session that
   turns into a support call produces one anecdote instead of five stop-points.
6. **Do not defend the design.** If they say it's confusing, the answer is *"tell me more"* — never
   *"well, the reason it works that way is…"* The second answer teaches them to stop reporting.
7. **Twenty minutes, hard stop.** Fatigue produces compliance, and compliance looks like success.
8. **Log during, not after.** Memory smooths. Use the table at the bottom of this doc, on paper or a
   second device, while it is happening.

---

## Running it remotely (Perth ↔ US)

The whole platform is US drivers and the owner is in Perth. This is solvable and should not become
the reason it never happens.

**Best: a video call with the phone propped up so you can see the screen AND the thumb.** Hesitation
is a thumb hovering, and a screen recording alone loses it. WhatsApp or Messenger video, phone leaned
against something on the dash or the bunk. Ask them to keep the phone still and talk out loud about
nothing in particular — you are not asking them to narrate, you are keeping the line from going
quiet enough to feel awkward.

**Acceptable: phone screen recording, sent afterwards, then a five-minute call.** You lose the thumb
and you lose the live hesitation, but you keep the taps and the back-outs. Ask them to record their
own voice too. Then watch it before the call, and only ask about the moments you already saw.

**Do not use: a survey, a questionnaire, or a call with no screen.** Those measure what a driver
remembers and how much they like you.

**Time zone:** Perth is 13–15 hours ahead of the US mainland. Your evening is their early morning;
their evening is your morning. A driver at a truck stop after their ten-hour break is a driver with
twenty free minutes and a phone in their hand. That is the window.

**Pay them.** Twenty minutes of an owner-operator's time is worth something and offering it changes
the relationship from favour to work — which makes them more honest, not less.

---

## Before you start (once)

1. A **fresh account** on their phone. Not yours, not a demo login. If they already have an account,
   that's better — but note it, because a returning driver cannot give you a first-run reading.
2. Confirm the app is the **deployed build**, not a local one. As of HANDOFF-118 the box was serving
   112's code with five sessions unpushed; if that is still true, you are testing something nobody
   is running.
3. Ask permission to record, in one sentence, and mean it: *"Can I record the screen? I'm trying to
   find where the app is confusing, not testing you."*
4. Say that sentence anyway even if you are not recording. Drivers assume they are being graded.
   They are not, and it changes what they do.

---

# THE TASKS

Five tasks. Run **T1 and T2 always** — they are Phase DoD items 1 and 3. The rest as time allows,
in order.

Each task gives you the **exact words to say** and then nothing else. Read the instruction verbatim.
Improvised phrasing leaks hints.

---

## T1 — Detention `[M3]` `[DoD#3]`

> **Say:** *"You just got held up at a receiver for three hours. Get paid for it."*

**Done means:** a detention claim exists in the database with a counterparty, and the driver has
attempted to send it.

**Do not say:** "load", "stop", "meter", "claim", "detention tab", or the name of any tab.

**Watch for, in order:**
- Do they open the app to the Map and stay there? (The Map is the default and the money is on Load.)
- Do they find "add a load" without being told a rate con photo is the primary path?
- Do they understand the Meter is counting *their* money and not a timer?
- At free-time expiry, does anything tell them something changed?
- Do they know who the claim goes to, and do they believe it went?

**The moment that matters most:** whether they ever arrive at the Load tab unprompted. If they don't,
nothing downstream of it has been tested.

---

## T2 — Stop packet `[A1]` `[DoD#1]`

> **Say:** *"You've just finished loading. Send your paperwork to your dispatcher."*

**Done means:** a stop packet is composed, reviewed by them, and sent.

**Do not say:** "packet", "capture", "checklist", "review card".

**Watch for:**
- Do they go looking for a camera, or wait for the app to ask them?
- A1 requirement 5 says the driver reviews before it sends. Do they *understand* that the review card
  is a review — or do they tap it expecting it to have already gone?
- Do they know what's in the packet without opening it?
- After sending: do they believe it arrived? Ask *"did that go?"* and log the answer, because F-01
  and F-06 in the backend audit both mean it may not have.

---

## T3 — Roadside `[M5]` `[F6]`

> **Say:** *"An officer is at your window and wants to see your medical card."*

**Done means:** the document is on screen, readable, in under fifteen seconds.

**This is the task with a clock on it.** Everything else can be slow. This one cannot — a driver
fumbling in front of an officer will never use the feature again.

**Watch for:** taps to reach it; whether they find inspection mode at all; whether the document
renders large enough to hand over; whether they try to zoom.

---

## T4 — Parking `[M1]` `[M6]` `[A7]`

> **Say:** *"It's 4pm. You need somewhere to park tonight."*

**Done means:** they identify a specific place they would drive to.

**Watch for:**
- Do they trust the availability badge? Ask *"how do you know that's right?"* — this is the §11.7
  honesty discipline meeting a real person, and it is the only way to find out whether "7m · 3
  drivers" reads as trustworthy or as noise.
- Do they look for tonight, or for now? A7 exists because drivers plan ahead; watch whether the
  current UI lets them.
- **If the map is empty where they are, stop and log it as coverage, not comprehension.** Nine states
  are live (A9). A driver in Georgia seeing nothing is F-A9, not a design defect.

---

## T5 — Shortpay `[M9]`

> **Say:** *"Your settlement came in light. Work out what they didn't pay you."*

**Done means:** they find the audit and can say what's missing.

**Watch for:** whether "Money" reads as *money owed to me* or *money I have*. Note also that F-23 in
the backend audit means the figures here may be wrong — if a driver says the number looks too high,
that is a backend defect confirmation, not a comprehension one. Log it in DRIVE.md instead.

---

## The five-second probe (run once, at the start)

Before T1, open the app on each tab root, one at a time, three seconds each, and ask:

> *"What do you reckon this screen is for?"*

Write down their exact words. Not whether they were right — **their words**. If four drivers describe
the Money tab in four different ways, the tab label is the defect and no amount of reorganising the
contents will fix it.

This takes ninety seconds and is consistently the highest-yield ninety seconds in the session.

---

# STOP-POINT LOG

One row per stop. Fill it in **during** the session.

**Types:** `HOVER` (thumb over a control ≥3s without tapping) · `WRONG` (tapped something that
doesn't lead there) · `BACK` (went back or closed) · `ASK` (asked you a question) · `QUIT` (gave up)
· `WORD` (said something out loud that shows a wrong model)

| # | Driver | Task | Screen | Type | What happened — their words where possible | Severity |
|---|---|---|---|---|---|---|
| 1 | | | | | | |
| 2 | | | | | | |
| 3 | | | | | | |
| 4 | | | | | | |
| 5 | | | | | | |

**Severity:** `BLOCK` (could not complete without help) · `SLOW` (completed, visibly hard) ·
`DOUBT` (completed but didn't trust the result).

`DOUBT` is the one people forget to log and it is the most expensive kind. A driver who files a claim
and doesn't believe it sent will not file a second one, and DoD #3 needs a second one.

---

# AFTER: turning the log into work

1. **Group by screen, then by type.** Not by driver.
2. **Two or more drivers on the same screen with the same type = a defect row.** Move it into
   DRIVE.md's defect table with a `[WATCH-n]` tag so it is traceable back to the observation.
3. **One driver = a note.** Keep it. Three notes on the same screen from three different angles is
   also a defect, and you will only see that after the third session.
4. **Do not design from a single stop-point.** The fix for a `HOVER` on the Load tab could be a label
   change or a reordering; the log tells you *where*, and only the second driver tells you *what*.
5. **Anything tagged coverage or backend goes to DRIVE.md, not here.** This document is only about
   whether a driver can follow the app.

## What this makes decidable

- **D4** — whether to add the comprehension criterion to design-prd §22.3 — becomes a decision with
  evidence rather than a judgement call. If drivers complete T1 and T2 unaided, the criterion is
  documentation. If two drivers `BLOCK` on the same screen, it is a law.
- **A10 requirement 3** — *"Do not specify the document-portal work yet… one more conversation is
  required"* — the conversation is T3 plus the five-second probe.
- **A8 / D7** — whether Parking earns a sixth tab. T4 answers it directly: watch whether a driver
  goes looking for parking somewhere that isn't the Map. Guessing at this from a design argument is
  how a tab bar gets rearranged twice.

---

## The failure mode of this document

Running it once, finding three things, fixing them, and never running it again.

The value is in the **repeat**: the same five tasks, same words, after each change, with new drivers.
A stop-point that disappears is a fix that worked. A stop-point that moves somewhere else is a fix
that relocated the problem — which is the normal result of a redesign, and the only way to catch it
is to have measured the same thing twice.
