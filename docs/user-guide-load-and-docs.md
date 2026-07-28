# User guide — the Load tab and the Docs tab

**Audience:** drivers using the app, and anyone doing QA on it.
**Scope:** the two tabs where a load is run and where paperwork lives — `/load` and
`/docs` — plus every screen they open (evidence record, claim detail, cargo-condition
capture, incident, document viewer, archive).

This guide describes **what the app does today**, not what is planned. Where a control
exists but the capability behind it is incomplete, that is stated in §9 rather than
glossed over. Governing documents: `trucker-platform-prd.md` (build law) and
`design-prd.md` §10.2 (Load), §10.4 (Docs).

---

## 1. The two tabs in one paragraph each

**Load** is the current stop and what it is worth. Its centre is **The Meter** — one
figure that always answers "is my time being measured, and what is it earning?" Around
it sit the stop you are at, a four-item evidence checklist, one primary action chosen by
what you have not yet done, and a preview of where you go next. When a load ends, the
tab empties back to two controls: add a load, or look at past ones.

**Docs** is your wallet and your capture inbox. Its one primary action is **Inspection
mode** — producing a credential to an officer in two taps, with no signal. Below it: what
is expiring, your own documents, the paperwork attached to your loads, and anything you
photographed that never became a load. Nothing here is ever deleted; removal is
reversible.

---

## 2. The Meter — read this first

The Meter is the same component in the same place in every state. What changes is the
label, the figure and the colour.

| State | Label | Figure | Status line | Variant |
|---|---|---|---|---|
| No load | `No load` | `—` | *(none)* | `countdown` |
| Load added, not yet arrived, appointment ahead | `Until appointment` | `H:MM:SS` counting **down** | *(none)* | `countdown` |
| Not yet arrived, appointment passed | `Appointment passed` | `H:MM:SS` counting **up** | *(none)* | `warning` (amber) |
| Not yet arrived, no appointment on file | `Waiting to arrive` | `—` | *(none)* | `countdown` |
| Arrived, inside free time, **over** 30 min left | `Free time` | `H:MM:SS` counting **down** | *(none)* | `countdown` |
| Arrived, inside free time, **under** 30 min left | `Free time` | `H:MM:SS` counting **down** | *(none)* | `warning` (amber) |
| Free time exhausted, detention accruing | `Detention` | `$0.00` counting **up** | `H:MM:SS · $75/h` | `accruing` |
| Claim filed | `Detention` | frozen `$` amount | `Claim filed — clock stopped` | `accruing` |

The amber at 30 minutes of free time remaining is the one warning the Meter gives on its
own: it is the last moment at which leaving is still a decision rather than a
consequence.

Three expectations that surprise people:

- **The figure ticks in the browser, not on the server.** The app reads the clock once
  from the API and counts locally each second. Switching tabs and coming back re-reads it.
- **Filing a claim freezes the Meter deliberately.** What you see must match the claim you
  filed. Detention may keep accruing in the real world; the frozen figure is the claim.
- **The Meter never invents money.** With no load it rests at `—`. There is no sample
  load, no demo figure, nothing on this screen that is not yours.

---

## 3. Load tab — full journeys

### 3.1 Journey: add a load from a rate confirmation

This is the primary way a load is created (PRD §108).

**Empty state** shows: the resting Meter, one sentence — *"The Meter runs when you have a
load. Add one and it starts."* — a filled **Add a load** button, and a quiet **Past
loads** link.

1. **Tap "Add a load".** A sheet opens: *"Photograph the rate confirmation and we read
   the terms off it. Nothing is created until you confirm what we read."*
2. **Choose a photo or file.** Images and PDFs are both accepted. An image previews; a
   PDF shows its filename (a PDF cannot render as a preview image, so it names it rather
   than showing a broken frame).
3. **Tap "Read the rate con".** The document is filed to your wallet **immediately and
   unconditionally** — before any parsing is attempted. Losing the contract is never a
   possible outcome of a failed read.
4. **The confirm screen.** Everything parsed lands in an **editable field**. Nothing is
   created yet.

   - Success banner: *"Read from your rate con. Check it against the paper."*
   - Failure banner: *"We could not read this one. It is saved to your wallet — enter the
     terms below."* — you type the load instead. This is also what you see when no AI
     model key is configured.
   - Silence banner: *"This rate con does not state: detention · free time · TONU"* — a
     term the contract omits is reported as **silence, never as `$0`**. A rate con that
     is silent on detention is a fact worth knowing before you accept the load.

5. **Confirm each stop.** One block per stop, labelled `Pickup` / `Delivery` and `1 / 2`:

   | Field | What it does |
   |---|---|
   | Facility | The dock's name, editable. |
   | *Is this the same place?* | Existing facilities that may be this dock, each with its locality so two same-named docks can be told apart. Plus **"None of these"**. |
   | Receiver address | Typing it and leaving the field runs the geocoder. |
   | Placed at … | The geocoder's own wording for what it matched — shown, not assumed. |
   | **Find this place** / **Use where I am now** | Retry the geocode, or use your current GPS fix. |
   | Appointment / Window ends | Start and end of the window, as `datetime-local`. |

6. **Confirm the load-level terms:** Broker, free minutes, detention rate per hour.
7. **Tap "Start".**

**Expectations:**

- **Nothing is pre-selected in the facility match list.** Not caution — measurement:
  fuzzy matching scores an unrelated dock at 0.645 and the correct one at 0.679, so no
  threshold separates them. A wrong match costs one tap to notice; a wrong default costs
  a load attached to a dock you never visited.
- **"Start" stays disabled until every stop has coordinates.** The geofence is armed on
  them. A stop that cannot be placed is a stop whose arrival can never be detected, so the
  sheet refuses to file it rather than inventing a location.
- **Only the first stop is armed.** Arming opens an evidence log and a live geofence, and
  you are at one dock at a time. Stop 2 arms when you leave stop 1.
- **A failed "Start" leaves your form exactly as typed.** You never re-photograph a rate
  con because a request failed.
- **The rate con is attached to the first stop** once the load exists, so the load's
  history shows the paper it came from.

### 3.2 Journey: approaching the dock

Before you arrive, the tab shows:

- **The Meter** counting down to (or up from) the appointment.
- **Stop context:** facility name, then the broker/counterparty on its own line.
- **Appointment** with the window in monospace, e.g. `08:00–10:00`.
- **Where that time came from** — one of *"Read from your rate con"*, *"You entered
  this"*, *"From your fleet system"*.
- **"Correct the appointment"** (or *"Add the appointment"* if there is none).
- **The evidence checklist**, with the arrival row reading *"Arrival not recorded yet"*.
- **Next** — the following stop's facility and appointment time, if the load has one.
- **Primary CTA: "I've arrived"**.

**Correcting the appointment** opens a sheet: *"Use the time on the rate con. This is
what your detention clock is measured against."* Saving re-marks the window's source as
**"You entered this"** — the parse no longer gets credit for a value it did not supply.

**Why the provenance line matters:** a mis-read appointment silently costs you a
protection you believe you have, and it is only correctable **while you are still
approaching** and can still ring the broker. That is the entire reason the window is
shown before arrival rather than judged after it.

### 3.3 Journey: arriving and the clock

**Tap "I've arrived".** In one action the app:

1. Records a geofence ENTER at the stop's coordinates.
2. Writes an `Arrived` event into the stop's tamper-evident evidence chain.
3. Starts (or resumes) the detention claim and its clock.
4. Files an **on-time proof artifact** — computed and stored on *every* arrival, in the
   window or out of it, whether or not you opted into notifying the broker. The artifact
   is your protection; the notice is a separate choice.

**What you see immediately:** the Meter switches to `Free time` and starts counting down.
The first checklist row resolves:

| Row state | Meaning |
|---|---|
| ✓ **On time** `08:14` | You arrived inside the appointment window. |
| ⚠ **Late** `10:31` | You arrived outside it. Amber, not red — an unblaming statement of fact. |
| 🕐 **Arrival not recorded yet** | Not arrived. |

**The evidence checklist**, four rows, each carrying colour **and** icon **and** label:

1. On-time verdict + arrival time.
2. `BOL captured` / `BOL not captured`.
3. `Photos 0/4` — the denominator is the point; a bare count cannot tell you whether you
   are finished.
4. `Notice sent` / `Notice not sent`.

**"View all evidence →"** opens this stop's full record (§3.8).

### 3.4 Journey: the CTA ladder

The tab shows **one** primary button at a time, chosen by what is not yet done, in this
order:

```
I've arrived  →  Snap BOL  →  Send notice  →  Generate claim
```

The rungs the ladder passes over do not disappear — they stay reachable as small text
controls in a wrapping row beneath the primary button, in that same order. The ladder
decides what is **loudest**, not what is **permitted**: a driver at a receiver that has
not produced paperwork yet must still be able to file a claim.

Also in that row:

- **Capture cargo condition** appears there directly while the truck is parked at the
  dock (ON_SITE), because that is the only place those photographs can be taken. It stays
  in the More sheet as well — this is a shortcut, not a move.
- **More for this stop** opens everything else.

**The More sheet** contains:

| Item | What it does |
|---|---|
| Capture cargo condition | The guided four-photo sequence (§3.5). |
| Report an incident | Damage / refusal / unsafe site / theft / other (§3.6). |
| View what you filed | Appears only after you file an incident **in this session**. |
| Check load profit | Cross-link to the profit calculator. |
| **Leave this stop** / **End load** | The label says which — see §3.9. |

### 3.5 Journey: cargo-condition photos

**More → Capture cargo condition** (or the on-site shortcut). A guided sequence, one
decision per screen, four steps in order:

```
Trailer exterior  →  Seals  →  Load blocking  →  Reefer setpoint
```

Each tap opens the rear camera directly. Each photo is hashed and appended to the stop's
evidence chain. The counter reads `Step 2 of 4`. At the end: *"Condition documented"*.

**Expectations:**

- Photos count toward the `Photos n/4` checklist row on the Load tab.
- **Offline photos are queued and replayed exactly once.** Photographing cargo in a dead
  zone is safe — an idempotency key prevents a duplicate appearing in the chain.
- **While driving**, the step and the progress stay readable but the camera does not
  open: *"Pull over to photograph the load. Your progress is saved."* The progress is
  already durable server-side, so that is a fact, not a reassurance.

### 3.6 Journey: report an incident

**More → Report an incident.** Pick one kind chip — Damage, Load refused, Unsafe site,
Theft, Other — add an optional note, file it. Filing opens its own protected evidence
record.

Confirmation is a toast: *"Incident logged — added to your evidence"*, or offline,
*"Saved — it'll sync when you're back online."*

**Expectation to know about:** after filing, **"View what you filed"** appears in the
More sheet and takes you to that incident's record, where it can be exported or shared.
That link lives **only for the current app session** — reopening the app loses it. The
incident itself is permanent; the shortcut to it is not.

### 3.7 Journey: notice and claim

**Send notice** tells the broker that detention is now running, citing the rate
confirmation.

- Before free time is exhausted, nothing is sent: *"Detention hasn't started yet —
  nothing to notify."*
- When it goes out: *"Broker notified — detention on record."* The `Notice sent` row
  ticks, and a `Broker notified` event enters the chain **only if a message actually
  went out** — logging an attempt that no-oped would assert a fact a dispute turns on.

**Generate claim** closes the loop into a GPS-backed, filed detention claim.

- **The control only appears once the amount is above zero.** Free time running out and
  money being owed are not the same instant. Filing at `$0.00` would freeze the Meter at
  nothing and hide every claim control behind it.
- Filing anchors the evidence chain, composes the claim pack, and — for drivers on their
  own authority — opens a receivable against the broker.
- The Meter freezes. A **"View claim"** row appears.

**The claim detail screen** (`/claim/:stopId`) shows:

| Section | Contents |
|---|---|
| Header | Facility · broker |
| The money | The amount, and how it settles — **"Money owed to you"** (own authority: the broker is invoiced in your name, with your verified MC#) or **"Handed to your carrier"** (company driver: the pack goes to your carrier to collect). |
| How it's calculated | Detention time · rate per hour · free time in minutes. |
| GPS-verified evidence | The timeline, plus a **Chain verified** badge. |

The arithmetic on the face of the claim reproduces exactly: the amount is derived from
the seconds printed on it, not from the float behind them. An invoice whose own figures
do not reproduce invites the one question a detention claim cannot afford.

### 3.8 Journey: the evidence record and sending it

Reached from **"View all evidence →"**, from a past-load row, or from "View what you
filed". Route: `/load/:stopId/evidence`.

| Section | Contents |
|---|---|
| Header | Facility name, and **Chain verified** when the hash chain is intact. |
| Cargo condition photos · *n* | Each photo with its real thumbnail, its guided prompt name, its capture time and its verified hash. |
| Timeline | `Arrived`, `Broker notified`, `Departed`, `On-time check` — each named by **what happened**, with its time. |
| Documents on file | Paperwork attached to this stop, properly labelled (`BOL`, `Rate con`) with its date. |
| Send this record | **Export PDF** and **Share with broker**. |

**Export PDF** is your own copy. It regenerates from the chain every time, so it is
always current. It downloads directly. If it fails: *"Couldn't build the PDF just now.
Check your signal and try again."* — nothing is queued, because your own copy is not a
promise to anyone.

**Share with broker** is a different act and the copy says so. It **pins** what is being
sent: from that moment the bytes are frozen, so the chain may grow and the link keeps
serving exactly the document the counterparty was given. You may add an email address.
*"They get one link to this record. No sign-in needed."* One link, never an attachment.
The link can be extended or closed later.

Offline, a share is queued: *"No signal — the link goes out when you have one."*

**While driving**, everything on this screen stays **readable** and nothing **acts** —
the Export and Share card does not render.

### 3.9 Journey: leaving a stop, and ending a load

**More → the last item**, whose label tells you which will happen:

- **"Leave this stop"** — the load has further stops. The stop is marked departed, the
  **next stop is armed**, and the Load tab switches to that dock. The Meter re-arms for
  the new stop.
- **"End load"** — this was the last stop. The stop departs, the load reaches
  `completed`, and the tab returns to its empty state.

### 3.10 Journey: past loads

**Past loads** is a quiet link on the empty state. It opens a sheet listing every load you
have run. Each row carries **only what that load actually produced** — a load that
captured nothing says so.

```
Harvest Foods DC → Metro Market                    ⌄
TQL-88214 · 2026-07-28 · 2 stops
$271.43 · Invoiced
evidence pack · BOL · Rate con
```

| Line | Meaning |
|---|---|
| Route | `Origin → Destination`. A single-stop load shows one name. |
| Meta | Load reference number · date · stop count. |
| Money | Summed across every stop, with one claim state. Or *"no detention"*. |
| Produced | *"evidence pack"* plus each document type. Or *"nothing was captured"*. |

- **A multi-stop row expands** (chevron) into one row per stop — `1 · Pickup · Harvest
  Foods DC`, its money and its photo count — each opening that stop's evidence, plus
  **"Export whole load"**, which produces a single PDF covering the entire route with
  labelled per-stop sections.
- **A single-stop row** has nothing to expand and goes straight to its evidence.

**Two expectations worth stating plainly:**

- **Past loads is only reachable when no load is active.** The control renders on the
  empty state. While you are running a load, history is not reachable from this tab.
- **Offline, the sheet shows the last-known list** rather than an error screen.

### 3.11 Special states

**While driving** the Load tab collapses to the Meter alone plus one line pointing at
voice, which lives on the Map tab. No stop context, no checklist, no buttons, no sheets.
It is a glance, and glances are all a moving truck gets.

**Location off** shows one persistent card on this tab and nowhere else:

> Location is off, so arrivals aren't detected. Start the meter yourself when you reach a
> dock. — **Turn location back on**

It states the **consequence**, not the permission, and it never nags beyond that card.
It does not appear when location is simply *unavailable* (a desktop browser, hardware
off) — there is no one-tap fix for that, and offering one would be a dead control.

---

## 4. Docs tab — anatomy

Top to bottom at 360 dp:

```
┌──────────────────────────────────┐
│  🛡  Inspection mode             │  ← the one primary action, 56 dp
├──────────────────────────────────┤
│  Medical card · expiring   ⚠     │  ← expiring strip, only when non-empty
│  Insurance · expired       ⛔    │
├──────────────────────────────────┤
│  ›  Your documents            4  │  ← collapsed by default
│  ›  Load paperwork            3  │
│  ›  Not attached to a load    2  │
├──────────────────────────────────┤
│  +  Add document                 │  ← hidden while driving
│  🗄  Archived                 2  │  ← only when something is archived
└──────────────────────────────────┘
```

**The three sections are collapsed by default and the count is on the heading**, so
nothing has to be opened to learn whether it is worth opening. The expiring strip sits
above them and surfaces what needs action with no tap at all.

An empty wallet shows one sentence: *"Your CDL, medical card, insurance and permits live
here, ready for a roadside inspection even with no signal. They appear as they are added
to your account."*

---

## 5. Docs tab — full journeys

### 5.1 Journey: a roadside inspection

The design target is **two taps from a cold start, with no signal**.

1. **Tap "Inspection mode".** A sheet lists only the four credential types an officer
   asks for: **CDL, Medical card, Insurance, Permit** — each with its expiry date.
2. **Tap any document.** The actual document opens full-screen — the image, or the PDF in
   a viewer with an "Open document" fallback link.

Hint on the sheet: *"Tap any document to show it."*

**Expectations:**

- **A row is not a credential.** A list reading `CDL · 2028-01-17` is our *claim* that you
  hold one. Inspection mode exists to produce the document itself.
- **It works with no signal.** Document bytes are cached immutably for a year, so a
  document opened at home opens again at the scale house. If it genuinely cannot be
  fetched: *"Could not open this one. It is still saved."* — a plain statement, never an
  empty frame.
- **Driving does not block viewing.** You hand the phone to an officer, and by then the
  truck is stopped. The driving guard is on capture and on destructive actions, which is
  where it belongs.
- Load paperwork (BOL, POD, rate cons) is **not** in inspection mode. An officer is not
  asking for your rate con.

### 5.2 Journey: add a document

**Tap "Add document".**

1. **"What is it?"** — chips for CDL, Medical card, Insurance, Permit, Rate con, BOL,
   POD, Other. (Reached from the Load tab's **Snap BOL**, this step is skipped: you have
   already answered.)
2. **A replacement warning, if one applies.** For CDL, Medical card and Insurance — the
   types you hold exactly one of: *"You already have one of these. Saving replaces it —
   the old one stays in your records."* Stated **before** you save, while you can still
   stop. Permits deliberately never warn: you legitimately carry several at once, and
   nothing distinguishes them, so superseding on type alone would archive the wrong one.
3. **Photo or file.** Images preview; PDFs are named.
4. **"Expires on"**, shown **only** for CDL, Medical card, Insurance and Permit. Hint:
   *"We warn you 30, 14 and 3 days before."* A BOL does not expire, and asking for a date
   that will never matter teaches you the form is not paying attention.
5. **"Save to wallet".**

**Expectations:**

- Online, the sheet closes and the wallet simply has the document. Completion is
  deliberately silent — you watched it arrive, so announcing it again is noise.
- Offline it is **queued and replayed exactly once**; a credential photographed in a dead
  zone never lands twice.
- The sheet itself carries confirmation copy — *"Saved to your wallet."*, *"Saved on your
  phone. Syncs when you have signal."*, *"The previous one was archived, not deleted."* —
  but both hosts (Docs and Snap BOL) close the sheet on the same event that sets it. Treat
  those three strings as unverified in the running app until someone has watched for them;
  see §9.
- **While driving the capture chip does not render** — and if you opened the sheet while
  stopped and then pulled away, **the sheet closes**. A live camera UI at 65 mph is a
  hazard, and hiding the button that opens a flow is not the same as closing the flow.

### 5.3 Journey: the three sections

**Your documents** — your own credentials, grouped by type, each showing its expiry (or
`—`). Tapping one opens it.

**Load paperwork** — grouped by **load**, not by type, because a BOL matters for the load
it belongs to, not for being a BOL. Each row: the route, the reference number and date,
and which document types are on it. Tapping a row opens **that load's evidence record**.

**Not attached to a load** — rate cons, BOLs and PODs photographed that never became a
load. Said plainly rather than left looking like filed paperwork, with a **Remove**
control on each. Hint: *"Photographed, no load made."*

**Why this split exists:** the wallet used to return everything on the account grouped by
type, so a CDL sat between rate cons. Measured on a real account: 40 documents, 5 of them
the driver's own.

### 5.4 Journey: something is expiring

The strip near the top shows a pill per affected document: **amber** for `expiring`, **red**
for `expired`, e.g. `Medical card · expiring`.

`expiring` means a reminder is currently due — the 30, 14 and 3-day ladder. `expired`
means the date has passed. Documents with no expiry date never appear here.

### 5.5 Journey: correct a mistake

Open any document → **Edit** (beside the expiry) → correct the date → save.

*"Corrects the date only. To replace the document itself, add a new one."*

**The bytes are never editable.** Replacing an image is a new capture, which supersedes
and archives, so what you file and what an inspector sees cannot quietly diverge. Editing
is offered only on live documents — an archived one records what *was* true, and editing
it would rewrite history rather than correct the present.

### 5.6 Journey: remove a document, and get it back

1. Open the document → **"Remove from wallet"** (outlined red).
2. A confirm sheet: **"Remove from wallet?"** — *"It leaves your wallet and stops expiry
   reminders. Nothing is deleted — you can restore it any time from Archived."* Then
   **Remove** (filled red) or **Keep it**.

**What removal actually does:** it takes the document out of circulation, not out of
existence. It leaves the grid, leaves inspection mode and stops the expiry ladder, while
the row and the bytes stay exactly where they were.

**The archive** — the `Archived · n` control, which only renders when there is something
in it. Every row says **why** it is there, because these are different facts leading to
different outcomes:

| Reason | Restorable? |
|---|---|
| *"You removed this"* | Always. |
| *"Replaced by a newer one"* | Only if no current one of that type is in the wallet. |

A blocked row says so instead of offering a control that exists only to fail: *"A current
one is already in your wallet. Remove that one first to bring this back."* The block is
the supersession rule from the other side — two live CDLs is a question about which is
current, asked at a roadside inspection, which is the worst possible moment for it.

Archived documents can still be **opened and read**. Footer: *"Nothing here is deleted.
Tap any document to open it."*

**While driving**, Restore and Remove do not render. Viewing does.

---

## 6. How the two tabs connect

| You do this on Load… | …and it appears in Docs as |
|---|---|
| Photograph a rate con in the import sheet | `Rate con` under **Load paperwork**, attached to the load's first stop |
| Photograph a rate con, then abandon the import | `Rate con` under **Not attached to a load** |
| Tap **Snap BOL** at a stop | `BOL` under **Load paperwork** for that load |
| Capture cargo-condition photos | *Not* in Docs — evidence photos live in the stop's evidence record, not the wallet |

| You do this in Docs… | …and it appears on Load as |
|---|---|
| Add a document with a `stop` attached | The `BOL captured` checklist row ticks |
| Tap a **Load paperwork** row | That load's evidence record opens |

---

## 7. Offline behaviour — what queues and what does not

| Action | Offline behaviour |
|---|---|
| Cargo-condition photo | **Queued**, replayed exactly once |
| File an incident | **Queued**, replayed exactly once |
| Add / remove / restore a document | **Queued**, replayed exactly once |
| Share a pack with a broker | **Queued** — *"the link goes out when you have one"* |
| View a document | **Works** — cached immutably for a year |
| Read the wallet / past loads | **Shows the last-known list**, never blanks |
| **"I've arrived"** | **Not queued.** Fails silently — see §9 |
| **Send notice** | **Not queued.** Fails silently |
| **Generate claim** | **Not queued.** Fails silently |
| Correct an appointment | **Not queued** — the sheet stays open with what you typed |
| Export a PDF | **Not queued** — states the failure |
| Location ping | **Deliberately dropped.** A replayed position would be judged against server time and could fabricate an arrival at a dock you left this morning. A lost transition is a gap; a fabricated one is a lie in an evidence chain. |

---

## 8. Every screen these two tabs can reach

| Route | Screen | Reached from |
|---|---|---|
| `/load` | Load tab | Tab bar |
| `/load/:stopId/evidence` | Evidence record | "View all evidence", past-load rows, Docs paperwork rows, "View what you filed" |
| `/claim/:stopId` | Claim detail | The "View claim" row after filing |
| `/protection/condition` | Cargo-condition capture | More sheet, or the on-site shortcut |
| `/load/calc` | Profit calculator | More sheet |
| `/docs` | Docs tab | Tab bar |

---

## 9. Known gaps — what this guide is not promising

Carried from `docs/handoffs/HANDOFF-097.md` §7. These are real and open, not
speculation:

- **`rate_cents` and `accessorial_terms` are parsed from a rate con and stored on no load
  field.** The import screen reads them; nothing keeps them.
- **Per-stop detention terms exist in the schema and cannot be expressed in the UI.** Every
  stop on a load carries the load's terms.
- **Arrive, Send notice and Generate claim are not queued offline.** In a dead zone the
  button does nothing visible and nothing is retried. Arrival is the one that matters
  most: with no signal at a dock, the clock does not start.
- **"View what you filed" for an incident survives only the current session.**
- **Past loads is unreachable while a load is active.**
- **Evidence logs recorded before commit `f3e6a86` are polluted** — a scoping defect let
  other stops' arrivals into a pack. The chain is append-only, so those records cannot be
  removed without breaking the hashes that make a pack worth anything. **Only stops
  recorded after `f3e6a86` are clean.**
- **The free-time caption was reported as missing in one screenshot right after arrival
  and has never been reproduced.** Do not "fix" it without seeing it.
- **The document-capture sheet's three confirmation strings may be unreachable.**
  `DocumentCaptureSheet` sets its `done` state and emits `captured` in the same call;
  both hosts — the Docs tab and Snap BOL — close the sheet on that event. Read from the
  code, not observed in the app. Worth one minute of QA before either fixing it or
  deleting the strings; if the sheet really does close over them, that is the
  "capability with nothing reaching it" shape this project keeps finding.

---

## 10. QA checklist — the shortest path through both tabs

Run this against a real stack (`make up`), on a 360 × 800 viewport, signed in.

**Load**

1. Empty state: Meter reads `No load` / `—`. No money anywhere on screen.
2. Add a load from a rate con photo. Confirm the parse banner matches reality (readable
   vs unreadable). Confirm **Start is disabled** until every stop is placed.
3. Confirm the facility match list has **nothing pre-selected**.
4. Pre-arrival: window and its provenance line both render. Meter **ticks**.
5. Correct the appointment → provenance flips to *"You entered this"*.
6. Arrive → on-time verdict resolves with a time; Meter switches to `Free time`.
7. Snap BOL → the `BOL not captured` row flips to `BOL captured`.
8. Capture 4 condition photos → `Photos 4/4`.
9. Send notice before free time expires → *"nothing to notify"*. After → *"Broker
   notified"*.
10. Confirm **Generate claim is not offered at `$0.00`**.
11. File the claim → Meter freezes at the filed amount; "View claim" appears.
12. Open the evidence record. **Export the PDF and open it.** Confirm the timeline names
    events (`Arrived`, not "Event recorded"), that the stop is identified by leg and
    role, and that the header does **not** say the chain is broken.
13. Leave the stop → the tab switches to stop 2, not to empty.
14. End the load → Past loads shows the **route**, the **summed** money, and expands to
    both stops. Export whole load.

**Docs**

15. Inspection mode → four credential types → tap one → **the document itself renders**,
    image and PDF both.
16. Add a CDL when one exists → the replace warning appears **before** saving.
17. Confirm the expiry field appears for CDL and **not** for BOL.
18. Confirm the three sections are collapsed with counts on the headings.
19. Confirm the BOL from step 7 is under **Load paperwork**, filed against its load.
20. Remove a document → confirm sheet states the consequence and its limit → Archived
    count increments → the row states **why** → Restore returns it.
21. Try to restore a superseded credential whose replacement is live → the row says it is
    blocked and names what is in the way.
22. Set DRIVING → capture chip gone, Add-document sheet closes, Inspection mode still
    reachable.

**The standing warning.** Every claim in this guide was read out of the code, and code is
not the running app. Ten defects in one session were found by an owner *using* the app
that 1,048 tests and 545 layout checks could not see. Run it.
