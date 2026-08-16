# DRIVE.md — Haulmeter browser test journeys (v2)

**What this is.** The owner's manual test suite. Every journey is a numbered sequence you run in a
browser against the local stack, with an expected result at each step. A journey passes only if every
step matches. Anything else goes in the defect log at the bottom — that log is the input to the next
session's plan. This inverts the loop: sessions now exist to turn ❌ rows green.

**v2 change:** adds **J7-AP — the stop auto-pilot** (the automation-surfacing rework: EXIT drafts →
a review CARD arrives on the Load tab → one Send). Everything else is unchanged from v1.

**Rules of use**
1. Run at **360 × 800** (Chrome DevTools device mode) — LAW 0. Widen only after it passes narrow.
2. Where a step names exact UI copy, it was verified against the code. Where it says *(label may
   differ)*, a wording mismatch is a **doc fix, not a defect** — but a missing control is a defect.
3. This doc is updated **in the same commit** as any feature that changes it (v2.0 acceptance #3).
4. Tags like `[M3-FR2]` `[A1]` `[DoD#3]` trace each journey to the requirement it tests.
5. Snapshot caveat: written against the HANDOFF-114 tree. If a step fails, first ask "did a later
   session change this?" — then log it.

---

## J0 — One-time setup (do once, ~15 min)

1. `make env` (first run only) → `infra/.env` from example. Ports LOCKED: API **8008** ·
   frontend **9008** (fallback 3008) · Postgres 5438 · Mailpit UI **8038** · MinIO console 9019.
2. `make up` → preflight passes (or names the conflicting PID), stack starts.
3. Seed demo data **at the coordinates your browser is spoofed to** — this is the step that made
   the auto-pilot unwalkable when it was skipped. You cannot arm a stop against a facility that is
   not near you.
   `make seed ORIGIN=27.9506,-82.4572`
   (`ORIGIN` is an alias for `DEV_SEED_ORIGIN`; both work. `make seed` does pass the env through —
   verified 2026-08-02.) → Plants the Dallas demo set **plus** three **"DEV —"** facilities
   (shipper, truck stop, bookable yard) within ~125 m of that point.
   **Forgotten where you seeded?** `make seed-where` prints the ORIGIN to paste into DevTools
   Sensors, each DEV facility's distance from it, and the geofence radius. Run it whenever the map
   looks empty — an empty map is almost always this, not a broken feature.
4. Admin sign-in needed later and `/admin` refuses? Run `scripts/seed_admin.py` the same compose-run
   way (the /dev button can only *register* a plain account, not mint an admin).
5. Browser: `http://localhost:9008/dev` — the dev directory. Two sign-in buttons (driver / admin),
   link cards for `/map /load /money /docs /more /load/calc /money/audit /protection/condition
   /fleet /owner /admin /scorecard /login`.
6. DevTools: device mode 360×800 · **Sensors → Location → Other** · grant location permission.
7. **Outbound email goes to real Gmail, not Mailpit** — owner decision 2026-08-04, dev *and*
   production on one account. **As of 2026-08-16 that account is the Google Workspace mailbox
   `claims@haulmeter.online`** (owner cutover; transport unchanged — still `smtp.gmail.com:587`
   with STARTTLS). So the inbox to watch is the account in `SMTP_USERNAME` (`infra/.env`), and
   `http://localhost:8038` stays empty by design; Mailpit is still in compose and still bound,
   simply not addressed. To put dev back on it, set `SMTP_HOST=mailpit` / `SMTP_PORT=1038` /
   `SMTP_STARTTLS=false` in `infra/.env` and recreate the api container.
   ⚠️ **A send from dev is a real send.** Recipients are editable and pre-filled from the load, so
   typing a live broker address into a test load emails an actual broker an actual detention
   notice. The seeded `@bolt.example` counterparties are safe — the TLD does not resolve, and
   Gmail bounces them back to the same inbox a minute later.
   ✅ **Email works at all as of 2026-08-02 and did not before.** There had been no SMTP gateway in
   the codebase for the life of the project: every send site passed a recording gateway, so the F8
   rows said a notice was sent and Mailpit had received **zero** messages. Fixed (§23 entry 122).
   If nothing arrives, check `SMTP_HOST` in `infra/.env` — blank switches email off by design, and
   a wrong App Password fails as `smtp-failed-SMTPAuthenticationError` in the F8 provider ref while
   the driver still sees "Sent".
8. Convention: **always enter surfaces from `/dev`** — you never guess a URL.

---

# TIER P0 — the money path (Phase DoD #3) + the automation rework

## J1 — First run, auth, empty product `[F1]`
1. Incognito → `localhost:9008` → login/register (no activation step).
2. Register fresh → signed in in well under 60s, no verification email.
3. Walk all five tabs. Each empty state = one sentence of purpose + one action (§15.3). No fixture
   money, no fake meter (the Load meter **rests** — em dash, no status).
4. Tab bar: 5 tabs, icons **with labels**, on every root. No hamburger anywhere.
5. **Language, before signing in** (§23 entry 125): the login screen carries a chooser above the
   wordmark naming the CURRENT language in its own words ("English", "ਪੰਜਾਬੀ"). Tap → sheet with
   all six in their own names → pick one and the whole screen, including the CTA, re-renders in it
   and the choice persists to the next cold start. It is the same `LocalePicker` More opens, so a
   driver never meets two controls for one setting.

## J2 — Map read: presets, pins, honesty `[M1-FR1..5, §11]`
1. `/dev` → driver → **Map**. GPS at your seed ORIGIN.
   ⚠️ **The three DEV pins never render together, and this doc used to claim they did.** They are
   three different facility types, so each belongs to a different preset (measured 2026-08-02):
   | preset | DEV pins visible |
   |---|---|
   | **Drive** (the default) | Test Truck Stop only |
   | **Tonight** | Test Truck Stop + Test Yard |
   | **Work** | **Test Shipper** — the one J7-AP arms |
   | Fuel / Service | none |
   So opening the map on Drive and seeing one pin is CORRECT. **To find the shipper, switch to
   Work.** One pin on Drive is not a defect; zero pins on every preset means you seeded elsewhere —
   run `make seed-where`.
2. Chip row: **five icon chips** — Drive, Tonight, Work, Fuel, Service. **No Food chip**
   (`m13_vendor` OFF — this absence is the test).
3. Long-press a chip → translated name (aria/title). Selected chip changes **fill/weight**, not
   just colour (C-1).
4. Switch Sensors to Dallas, pan/zoom → dense viewport: clusters show count; labels only past a
   zoom threshold; no overlapping labels.
5. Tap a pin → **facility card as a bottom sheet** (grab handle, ~40%/90% snaps), one contextual CTA.
6. A crowd status shows age quietly (`40m · 3 drivers`); a stale (>4 h) status renders **hollow**;
   a TPIMS/authoritative reading is attributed to the **feed**, never "1 driver" `[A3]`.
7. "Navigate" → deep-links to an external nav chooser. **No in-app routing anywhere** `[M1-FR8]`.
8. Reload → last preset remembered; a remembered-but-dark preset falls back to Drive.

## J3 — Add a load (rate-con import) `[F5, M4-FR4, §10.2]`
1. **Load** empty state → exactly **one** action: add a load via rate-con photo *(label may differ)*.
2. Import a rate-con photo/PDF → parsed values land in **editable draft fields**; a silent term
   shows as **silence, never $0**; facility match list **never pre-ticked**.
3. Confirm → load exists; Load tab shows counterparty row, appointment row, evidence checklist
   (BOL / photos / notice — honestly unticked).
4. Unreadable branch: import a photo of your desk → manual form carries the load; no fake "read"
   claim.
4a. **What we read, in your language `[J1-A2]`** — the money terms appear as a stated
   reading above the editable fields, so the confirm step is a comparison a non-English
   reader can actually make. Full walk-through in **J17 step 3a**.
4b. **On-time check-in `[J1-B1, M5-FR1]`** — on the confirm sheet, under the broker phone,
   a single unticked line: **"Tell {broker} when I arrive"**. It appears **only** when a
   broker address is present (no recipient, no offer) and is **off by default** — it sends
   a counterparty a message on the driver's behalf, so it is theirs to ask for. Tick it,
   file the load, and the consent is recorded against that load. ⚠️ live-fire: use a
   fixture address. The proof artifact is filed on arrival **either way**; consent gates
   only the notice to the broker.
5. **Broker contact, prefilled from the paper `[J1-A1]`** — flag `j1_contact_parse`, ships **OFF**;
   switch it on in `/admin/flags` first or the fields arrive blank and the step proves nothing.
   With it on, a rate con that prints an AP address lands it in **Broker email** and the number in
   **Broker phone**, both still editable — a parse is a proposal. Three things to watch, in
   descending order of how much they matter:
   - a rate con that prints **no** email leaves the field **empty**, never a placeholder;
   - a **photographed** rate con whose footer runs off the edge also leaves it empty — the server
     holds the parse to the driver's own address rule, so `dispatch@` never reaches the field;
   - what you **type over** it is what gets filed. ⚠️ J0.7 applies with full force here: prefilled
     means one tap from a real send, so a test rate con carries a **fixture** address
     (`@example`, `@bolt.example`) and never a live broker's.
   How often the parse is right on real paper is a **measurement, not a test** — `make ratecon-eval
   DIR=…` against a corpus held outside this (public) repo. Below 10 documents across 3 broker
   formats it reports itself as a sample.
6. **What this dock has done to other drivers `[J1-A3]`** — flag `j1_preaccept_intel`, ships
   **OFF**. With it on, **picking a matched facility** in the candidate list adds up to two
   lines under it: the detention **raw pair** ("Ran past 120 free minutes · 9 / 21 tracked
   stops") and the quickest appointment hour with its own sample. Three things to check:
   - it appears **on the choice**, not on the read — before a driver picks, there is no dock
     to ask about, and three candidates' histories at once is three answers to a question
     nobody asked;
   - it is a **pair, never a percentage** (§23 entry 153), and it names the free time it was
     counted against — the risk is measured against *this contract's* free minutes, so
     editing **Free minutes** and re-picking the dock changes the count;
   - below **5 tracked stops nothing renders at all** — not a greyed figure, not a hedged one.
     Seed a thin dock and confirm the lines are simply absent.
   Switching to **"None of these"** clears both lines: a stale figure attached to the wrong
   dock is worse than no figure.

## J4 — Arm, arrive, The Meter `[M3-FR1..2, F3, §9]`
0. **The arrival nudge `[J1-B1]`** — flag `j1_arrival_nudge`, ships **OFF**; switch it on in
   `/admin/flags` first. With an armed stop whose appointment is ~15 min out (the lead is
   `m05.arrival_lead_minutes`, tunable in `/admin/config`), the worker sends one P1 push
   that deep-links to `/load` with the arrival CTA in view. Three things to watch:
   - it needs **no background location** — the trigger is the clock and the armed stop, so
     it works on a handset that never granted the permission (that permission is DoD #8's
     open question, which is exactly why this path must not depend on it);
   - **already at the dock → silence.** Arrive first, then wait for the lead window: no
     push. The geofence answered the question the nudge would have asked;
   - **the in-app half needs no push at all.** Open `/load` with the appointment passed and
     the Meter already says so, in the warning colour, with **I've arrived** primary. That
     is what catches a 04:00 appointment quiet hours filed.

1. On the load: **Arm stop** for the **DEV — shipper**. Sensors = your seed ORIGIN (`make
   seed-where`). Creating the load at that facility arms its first stop for you.
2. Pre-arrival shows **"I've arrived"** CTA (§15.5). Preferred: nudge Sensors onto the shipper pin
   and wait ≤ ~1 min for geofence ENTER. Fallback: tap **I've arrived**.
3. → **The Meter** foregrounds: mono, fixed-width, counting **free time down**. No layout shift.
4. Boundary colours: free-time turns **amber** in the last 30 min; detention counts **money up** in
   green. **There is no dev-tooling gap here** — this doc used to guess there was. The load form has
   a **Free time (min)** field beside Rate $/hr; set it to **2** when you create the load and the
   whole free-time → amber → accruing chain is watchable in about two minutes.
5. `docker compose stop api` → Meter **keeps ticking** from local state; calm offline strip.
   Restart → silent recovery.
6. **At the dock, the screen has a job on it** (§23 entry 127, 2026-08-05). Arrived with the BOL
   filed and free time still running used to render **no primary button at all** — the state that
   covers most of a stop. It now reads **"Take cargo photos 0/4"**, and once detention accrues the
   money rung (**Send notice**) takes the Primary back. A stop whose checklist asks for no photos
   keeps no primary here, which is correct rather than missing.
7. **Every checklist row that does something ends in a chevron** (§23 entry 128); rows that only
   state a fact ("Late 15:40", "Notice not sent") do not. **Tap "Photos 0/4" → condition capture.**
   That row was an inert `<li>` until 2026-08-05 — the one line on the card that looked most like a
   job and did nothing.
8. **ON_SITE now survives a reload** (§5). Presence used to reach the client only as an ENTER edge,
   so refreshing the tab — or arriving via the **I've arrived** fallback, which trips no edge — left
   the app believing the truck was nowhere, and every ON_SITE behaviour went dark. `/location/ping`
   answers `present` on every ping. To check it: at the dock, reload the tab; the cargo-photo
   Primary must come back within one ping (≤60 s while armed).

## J5 — Notice → exit → claim pack → invoice `[M3-FR3..6, F4, §17]`
1. Detention accruing → **Send notice**. Confirmation reuses the verb ("Notice sent"); checklist
   flips that row.
2. **The Gmail inbox**: notice email — plain, professional English, one link, no images, load ref in
   subject. (Unblocked 2026-08-02; before that nothing was ever transmitted.)
3. Move Sensors away (or **End load**) → EXIT closes the stop.
4. Generate claim → **PDF**: header Meter figures, parties & refs, mono timeline w/ hairlines, map
   trace, artifact thumbnails, hash block. AP-clerk-readable in 30s.
5. Invoice **in the driver's name** (billing-agent), conventional layout.
6. Money tab: receivable, `invoiced`, aging in mono.

## ⭐ J7-AP — The stop auto-pilot (THE REWORK) `[A1, M3-FR5, M5-FR5, F8, §10.2]`
> This is the new-work journey. It proves the automation's *result arrives on the Load tab as a
> card*, not as a link to a separate screen. Run it after J4 (you need an armed, arrived stop with
> at least one captured document).

**Setup:** driver signed in, load active, armed at the **DEV — shipper**, Sensors on it so you're
ENTERed, at least one BOL captured via the checklist.

> **WALKED END TO END on 2026-08-02 (HANDOFF-116) and it works** — the card fires ~10 s after the
> EXIT and the driver's BOL is in the sent PDF. Three things had to be fixed first and are baked
> into the steps below: seed at your own coordinates, set `PUBLIC_BASE_URL`, and arm a **fresh**
> stop.
>
> **Arm a FRESH stop.** Documents captured before commit `a4e282c` are not in any stop's hash
> chain, so a stop armed in an earlier session renders half-fixed and makes this journey lie. Old
> stops predate the fix; start a new load.
>
> **`PUBLIC_BASE_URL` must be set** (`infra/.env` — now set in `.env.example`). Without it Send is
> refused with a plain "Not sent", correctly: for a handoff the link IS the document. If you copied
> `.env` before 2026-08-02, add `PUBLIC_BASE_URL=http://localhost:8008` and restart the api.

1. **Leave the dock.** Move Sensors **more than 150 m from the shipper** — the geofence radius. From
   the seed ORIGIN that means about **0.0022 of latitude (~240 m)**; a smaller nudge keeps you
   inside and nothing happens. Then **wait up to 60 s**: while a stop is armed the client pings on
   movement ≥50 m or once a minute, so the EXIT is not instant. The measured walk saw the card ~10 s
   after moving. Within a moment the EXIT fires and
   the packet drafts server-side. **Or leave by hand** — More → **Leave this stop** / **End load** —
   which now drafts the packet too (§15.5: build for auto, degrade to one-tap, never to nothing).
   Both paths are worth running: the hand path is the one that works when the background sensor
   does not, and until HANDOFF-115 it produced no paperwork at all.
2. **The review card arrives at the top of the Load tab**, without you leaving the tab or
   re-entering it. *(the rework)* — NOT a "N waiting" text link. Plain language: *"You left
   [facility]. Your paperwork is ready."* with the load reference beneath, and **one** action,
   **Review & send**.
   - ❌ **If instead you see only a small "N waiting" link that routes you to `/protection/packets`,
     the rework has not landed** — that is the exact v1 defect this journey exists to close.
   - ❌ **If the card only appears after you switch tabs and come back**, the EXIT watcher is not
     firing — log it. The card is supposed to arrive while you are looking at the Meter.
   - ⚠️ **With more than one packet waiting, the card names the stop you JUST LEFT** — the newest,
     not the oldest in the queue. Walking it on 2026-08-02 found the opposite: two drafts at the
     same facility produced a word-for-word identical headline while the sheet opened the OLDER,
     empty stop, so a driver would have sent the wrong document with nothing in it and no way to
     notice. Fixed; if the sheet ever says "Nothing was captured at this stop" right after you
     photographed a BOL, it has regressed.
   - *(Changed from the plan: the card has ONE action, not a Primary plus a preview expander. §8
     gives a card one action max, and the preview lives in the sheet, which is where you are
     reviewing anyway — design-prd §23 entry 120.)*
3. **Tap Review & send.** A **bottom sheet opens over the Load tab** (does NOT navigate you to
   another page — NAV-3). Two labelled sections when a claim rides along: **Paperwork** and
   **Detention claim**, with one Send.
   - **The claim section shows a claim you ALREADY FILED** (from the CTA ladder's *Generate claim*).
     Detention accruing but nothing filed → **packet only**, and that is correct: filing opens a
     receivable, increments the broker's claim history and freezes the Meter, and §12.2 forbids a
     button labelled about paperwork doing that on your behalf. Claim-on-EXIT one-tap is next
     session's decision, not this one's.
4. **The Paperwork section lists what is actually in the packet** — BOL captured, Cargo
   photographed, and so on. Nothing captured → it says so rather than showing an empty list.
5. **Recipients are pre-filled** from the load's counterparty and are **editable** — change the
   address and it goes where you typed (A1 req 6).
6. **Nothing sent silently before this** — you are seeing the packet *before* it goes (A1 req 5).
7. **Send.** The **Gmail inbox** now receives it: `From:` the account in `SMTP_FROM` — since the
   2026-08-16 cutover that is `claims@haulmeter.online`, and **Show original** should read
   `SPF: PASS`, `DKIM: PASS` with `d=haulmeter.online`, `DMARC: PASS`. (Gmail rewrites
   any From it has not verified, so `SMTP_FROM` matches the account.) The counterparty on
   `To:`, subject **"Stop paperwork · <load ref>"** (just "Stop paperwork" when the load has no
   reference — the manual fallback form does not collect one), body one plain line with one link.
   Neutral tone: a handoff, not a claim.
8. **Open the actual PDF — click the link in the emailed message**, which is exactly what a broker
   does. It renders from pinned bytes with no session. Measured on the walk of 2026-08-02:
   **HTTP 200, `application/pdf`, 100,042 bytes**, containing:

   - titled **"Stop paperwork packet"** (not "Stop record") ✅
   - **naming the broker and the dock** ✅
   - **2 embedded image XObjects — the driver's BOL photo is IN it** ✅ (until HANDOFF-115 the
     document held zero artifacts and one row: a blank page with a hash block)
   - **no "Detention" anywhere** ✅ — the packet is explicitly not a claim
   If any of those flips, it is a blocks-money defect, not cosmetic.
9. **Idempotency:** tap Send again (or double-tap) → the packet leaves the queue on the first Send,
   so there is nothing to double-send from the card. (The archive at `/protection/packets` is where
   a second tap would be possible; the send route is idempotent by state.)
10. **Notification: N/A this pass.** The EXIT push needs a new `f08` notification class and the
   owner chose **Option A — no new class this session** (design-prd §23 entry 121). There is
   deliberately no push; the card is the surfacing. Do not log its absence as a defect.
11. **Offline variant:** with the card showing, go **Network → Offline** and reload. The card
    **still renders from cache** (§15.1). **Send does NOT queue** — by design: a queued send would
    report success from a dead dock and leave you believing your paperwork went out (§12.4). You
    should see a plain *"No signal. Send this when you're back online."* and the packet still
    waiting. A silent success here is the defect.
12. **DRIVING variant:** with the app in a DRIVING state, the card must **not** offer Send — it
    shows *"Paperwork ready — review it when you stop."* and no button (Forbidden #11). (Hard to
    trigger on desktop — approximate or defer to handset; don't log as a defect.)
13. **The archive still works:** `/protection/packets` still lists drafted packets as history.
    The rework *added* the inline card; it did not remove the archive door.

## J6 — Money lifecycle `[M4-FR5, M9-FR4]`
1. **Money**: month summary (Meter treatment), receivables list with status pills + aging.
2. Each receivable: one **Next action** (nudge / escalate / mark paid).
3. **Mark paid** → state flips, month total moves, paid event lands in earnings (the DDD counter).

---

# TIER P1 — the daily surface

## J8 — Report a lot status, with proof `[M1-FR7, F10, F7]`
1. Map "at" the DEV truck stop → **tap the pin** → the card asks "How's parking here right now?"
   with Empty/Some/Full **on the card itself** (§23 entry 123). Two taps from the map, no second
   sheet, and the card is not swapped out from under you mid-answer.
2. Submit **Full** → the sheet closes, pin badge updates within a minute; `now · 1 driver`-shape
   freshness. Measured 2026-08-03: the whole card fits at 360×800 with nothing scrolled.
3. The floating **report** chip is still the from-anywhere path — it reports the NEAREST pin, and
   its sheet header now **names that facility**. Check the name before you tap; that is what it is
   there for.
4. Move 50 km away, retry → accepted but recorded `presence_proven=false` — F10 weights it down and
   pays no points. (It is not refused; verify in `f10.submission`, not by expecting an error.)
5. **More** → points moved for the accepted report; re-spamming hits the cooldown.

## J9 — Service & repair `[A5, DoD#6]`
1. Map → **Service** chip → repair/tire/wash/parts pins (Dallas is richer).
2. Card: **tap-to-call** where a phone exists, hours **verbatim** (never "open now"), service list,
   directions.
3. A facility with **no phone** → call row **absent, not empty**.
4. Admin → Flags → toggle `a05_service_preset` **off** → reload Map → **Service chip gone**
   (server-driven row). Back **on** → returns. If the toggle refuses on its gate: that's the
   `register_flag` bypass twin — **log exactly what happened**.

## J10 — Weigh stations `[E3.1]`
Map (Drive) around Dallas → weigh-station pins (small square) → the card asks **"Is this scale open
right now?"** with **open/closed** inline (never Empty/Some/Full — a scale's answer must not be filed
as a parking reading) → status + freshness update; armed load → corridor surfaces **scales ahead**.

## J11 — Fuel `[M1-FR5, M7-FR5]`
1. Map → **Fuel** → prices; EIA baseline where no crowd price, crowd confirms where present, each
   labelled (§11.7).
2. Station card: **confirm price** → your confirmation with distinct-driver count.
3. Negative: **no** "your net price"/program filter yet — `[A4]` unbuilt pending D3. If you see one,
   something is inventing UI.

## J12 — Parking booking + Owner portal `[M6]`
1. Map at Madison → **DEV — bookable yard** (square) → card with price + **Book**.
2. Book a night → one transparent price, confirmation; ledger records it (test-mode).
3. `/owner` (desktop fine — §18): the yard's calendar shows the booking; payout reflects the split.
4. Cancel per policy → both sides update; cancellation email in the Gmail inbox.

## J13 — Docs wallet `[M5-FR3, §17 Q16]`
1. **Docs** → capture a "CDL" → typed, gridded **by type**, localized label.
2. Second CDL → **pre-emptive** replace warning (amber, not red) → old one archived, pointed at
   replacement; expiry ladder follows the live one only.
3. **Remove** → confirm sheet states consequence + limit (reminders stop, nothing deleted). Archive
   shows *why* each row is there; **Restore** works — except a superseded CDL while its replacement
   is live, and the block **names** the obstacle.
4. **Inspection mode**: from cold start, ≤2 taps, **works with the API stopped**.

## J14 — Evidence share links `[F4 sharing]`
1. Export PDF and Share are real 48 dp controls.
2. Create link → open incognito (no session) → renders from **pinned bytes**.
3. Add a photo, refresh the link → **unchanged** (record, not cache).
4. Revoke → same URL → bare 404, indistinguishable from never-existed.

## J15 — Notifications, quiet hours, mute `[F8, §13]`
1. **More → Notifications**: push enrolment, the **lot-status prompt** class switch (default off),
   quiet-hours editor.
2. Quiet hours `22:00–06:00`; caption **names your device zone** (auto-detected, no 400-entry picker).
3. Opt in, grant permission, GPS at the DEV truck stop → arrival **push** prompt path fires.
4. Inbox: a suppressed row reads **"Held · not sent"**; nothing promises later delivery.
5. Facility page: **mute** this lot → prompted again? defect. **Unmute in the same place** → resumes.
6. Budget: across a full day of poking, unprompted pushes ≤ 2 (P0 exempt).

## J16 — Offline `[F12, §15.1]`
1. Network **Offline** with Map open → last region browsable; strip: **"Offline — everything saves
   to your phone"** in calm grey.
2. Submit a report + capture a photo offline → pending glyph, no error theatre.
3. Back online → drains silently, idempotent (twice offline → applied once).

## J17 — Locales + theme `[F15, §12.5, C-3]`
1. **More → Language**: all six — en, es, pa, ru, uz, so. Punjabi in Gurmukhi (no tofu/clip),
   Russian Cyrillic.
2. Jargon stays English every locale (detention, BOL, rate con, lumper).
3. Units stay imperial every locale.
3a. **The rate-con confirm step in a non-English locale `[J1-A2]`** — no flag; locale
   compliance is law, not a feature. Set the language to **Uzbek**, then run J3 step 2.
   The confirm sheet now carries a **"the money terms we read"** block above the editable
   fields, in Uzbek, with each figure beside its label. Then check the seam that matters:
   - a rate con **silent** on detention prints *"rate con'da bu ko'rsatilmagan"* — in
     Uzbek, not English, and never **$0.00**. Silent English here is unreadable as
     absence: a driver cannot tell "we found nothing" from "we did not translate this";
   - the **contract's own wording** below stays **English in every locale**, with the note
     saying why — a claim is argued from the paper's words, and a translated clause cannot
     be compared against the contract in your hand. This is deliberate, not a gap.
4. **More → Appearance**: manual light/dark override persists across reload; map style pairs.

---

# TIER P2 — breadth and guards

## J18 — Accessorials `[M4]`
File a TONU from a cancelled DEV load; a layover from an overnight dwell; snap a lumper receipt →
OCR draft → each rides the same pipeline into Money with its own type.

## J19 — Decision tools `[M8]`
`/load/calc` states its **basis** (sample sizes / heuristic), never fakes precision; Map →
sleep-solver ranks tonight's options.

**Fuel economy `[J1-A3]`** — no flag; the disclosure is honesty, not a feature.
1. Fresh account → `/load/calc` → Calculate. The basis list ends with **"Fuel figured at 6 mpg
   — ours, not yours."** That line is the whole point: the calculator burned a hardcoded 6.0
   for the life of the project and nothing on screen ever said so.
2. **More → Equipment → Miles per gallon**, enter `5.2`, Save. Back to `/load/calc` →
   Calculate: the fuel cost **changes** and the "ours, not yours" line is **gone** — a driver
   who told us 5.2 does not need telling we used 5.2.
3. Type `60` (the pickup's figure) → the range message appears **in your locale** and Save is
   disabled. Clear the field → saves as blank, and the calculator goes back to saying the
   number is ours. Blank and 6.0 are different answers and the screen must keep them apart.

## J20 — Settlement auditor `[M9]`
`/money/audit` → upload a settlement PDF → parse → discrepancy report against your own stop history
(thin on demo data — the *flow* is the test), "review with your carrier" tone.

## J21 — Community `[M10]`
Two profiles/drivers. A (present at DEV truck stop) broadcasts **"leaving in 15"** → B nearby claims
it → both earn points on B's confirmed ENTER. Q&A: B asks, A (present) answers. Review — one per
driver per window enforced.

## J22 — Fleet `[M12]`
`/fleet` → create fleet as A, invite B, B consents → A's workspace shows B's stops/claims **only
after consent**; claims desk lists across drivers.

## J23 — Admin console `[F14]` (admin sign-in)
1. **Flags**: every flag shows description + gates; `m13_vendor` and `m13_service_center` both off.
2. **Config**: declared keys listed unset (`a01.capture_checklist`); edit → driver side changes.
3. **Data / facility editor**: merge two duplicates → both old ids resolve to the winner on driver
   side **and** in admin URLs.
4. **Accounts**: deactivate a test account → login blocked, sessions killed, rows survive;
   reactivate. **Impersonate** → banner shows it; actions land in **Audit** with before/after.
5. Nothing here reachable by the driver account (403s, not hidden-but-live).

## J24 — Public scorecard `[M2-FR5]`
`/scorecard` logged out — aggregates with sample sizes, methodology visible, nothing
driver-identifiable.

## J25 — Negative: the food half is dark `[v2.0 §4]`
1. Driver app: no Food chip, no vendor sections, no "suggest a cook".
2. Admin → Flags → enable `m13_vendor` (dev only) → reload → **Food chip returns**, Dallas demo
   vendors surface (code carried, not deleted). **Turn it back off.** Verify the flag change wrote
   an **audit row**.

---

## Known desktop limits (NOT defects — this is the handset pass)
- **DRIVING/corridor mode**: needs sustained motion; static spoofing won't trigger it reliably.
- **The background sensor itself** — whether `/location/ping` fires on its own while the app is
  backgrounded, screen off, over hours — **cannot be tested in a desktop tab.** J4/J7-AP prove the
  *logic* (given a position, everything reacts). The *"positions arrive unprompted"* question is the
  Capacitor Android drive test, and the iOS background answer is separate (v2.0 DoD #8).
- Locked-phone tray actions and real camera EXIF richness — handset only.

## Defect log (append rows — this drives the next session)
| # | Journey·Step | Surface | What I saw | Expected | Severity (blocks money / blocks daily / cosmetic) |
|---|---|---|---|---|---|
| 1 | | | | | |
