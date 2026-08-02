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
3. Seed demo data. **For the auto-pilot journeys, seed a WISCONSIN origin** so you can arm a fake
   stop and leave it from your desk (WI is real ingested data, but the `DEV —` fakes are what you
   freely arm/leave):
   `docker compose -f infra/docker-compose.yml run --rm -e DEV_SEED=1 -e DEV_SEED_ORIGIN=43.0731,-89.4012 api python scripts/seed_demo.py`
   (Madison WI. `make seed` works if it passes the env through — verify once.)
   → Plants the Dallas demo set **plus** three **"DEV —"** facilities (shipper, truck stop,
   bookable yard) around Madison.
4. Admin sign-in needed later and `/admin` refuses? Run `scripts/seed_admin.py` the same compose-run
   way (the /dev button can only *register* a plain account, not mint an admin).
5. Browser: `http://localhost:9008/dev` — the dev directory. Two sign-in buttons (driver / admin),
   link cards for `/map /load /money /docs /more /load/calc /money/audit /protection/condition
   /fleet /owner /admin /scorecard /login`.
6. DevTools: device mode 360×800 · **Sensors → Location → Other** · grant location permission.
7. Second tab: `http://localhost:8038` (Mailpit — every outbound email lands here).
8. Convention: **always enter surfaces from `/dev`** — you never guess a URL.

---

# TIER P0 — the money path (Phase DoD #3) + the automation rework

## J1 — First run, auth, empty product `[F1]`
1. Incognito → `localhost:9008` → login/register (no activation step).
2. Register fresh → signed in in well under 60s, no verification email.
3. Walk all five tabs. Each empty state = one sentence of purpose + one action (§15.3). No fixture
   money, no fake meter (the Load meter **rests** — em dash, no status).
4. Tab bar: 5 tabs, icons **with labels**, on every root. No hamburger anywhere.

## J2 — Map read: presets, pins, honesty `[M1-FR1..5, §11]`
1. `/dev` → driver → **Map**. GPS at Madison → the three **DEV —** pins render.
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

## J4 — Arm, arrive, The Meter `[M3-FR1..2, F3, §9]`
1. On the load: **Arm stop** for the **DEV — shipper** (Madison trio). Sensors = Madison origin.
2. Pre-arrival shows **"I've arrived"** CTA (§15.5). Preferred: nudge Sensors onto the shipper pin
   and wait ≤ ~1 min for geofence ENTER. Fallback: tap **I've arrived**.
3. → **The Meter** foregrounds: mono, fixed-width, counting **free time down**. No layout shift.
4. Boundary colours: free-time turns **amber** in the last 30 min; detention counts **money up** in
   green. (If there's no quick way to compress free-time to watch this, that's a **dev-tooling gap**
   — log it; it blocks testing the signature element.)
5. `docker compose stop api` → Meter **keeps ticking** from local state; calm offline strip.
   Restart → silent recovery.

## J5 — Notice → exit → claim pack → invoice `[M3-FR3..6, F4, §17]`
1. Detention accruing → **Send notice**. Confirmation reuses the verb ("Notice sent"); checklist
   flips that row.
2. **Mailpit**: notice email — plain, professional English, one link, no images, load ref in subject.
3. Move Sensors away (or **End load**) → EXIT closes the stop.
4. Generate claim → **PDF**: header Meter figures, parties & refs, mono timeline w/ hairlines, map
   trace, artifact thumbnails, hash block. AP-clerk-readable in 30s.
5. Invoice **in the driver's name** (billing-agent), conventional layout.
6. Money tab: receivable, `invoiced`, aging in mono.

## ⭐ J7-AP — The stop auto-pilot (THE REWORK) `[A1, M3-FR5, M5-FR5, F8, §10.2]`
> This is the new-work journey. It proves the automation's *result arrives on the Load tab as a
> card*, not as a link to a separate screen. Run it after J4 (you need an armed, arrived stop with
> at least one captured document).

**Setup:** driver signed in, load active, armed at the **DEV — shipper** (Madison), Sensors on it
so you're ENTERed, at least one BOL/seal captured via the checklist.

1. **Leave the dock.** Move Sensors well away from the shipper. Within a moment the EXIT fires and
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
7. **Send.** **Mailpit**: the packet email to the counterparty, **load reference in the subject
   line**, neutral tone (a handoff, not a claim). **Open the PDF behind the link** — this is the
   step that matters most this pass:
   - It must be titled **"Stop paperwork packet"** (not "Stop record").
   - It must **name the broker, the load reference, the facility and the appointment**.
   - **Your BOL photo and cargo photos must be IN it.** Until HANDOFF-115 the document held zero
     artifacts and one row — a blank page with a hash block. If it is empty again, that is a
     blocks-money defect, not cosmetic.
   - It must carry **no detention figure** — the packet is explicitly not a claim.
8. **Idempotency:** tap Send again (or double-tap) → **no second document** in Mailpit.
9. **Notification: N/A this pass.** The EXIT push needs a new `f08` notification class and the
   owner chose **Option A — no new class this session** (design-prd §23 entry 121). There is
   deliberately no push; the card is the surfacing. Do not log its absence as a defect.
10. **Offline variant:** with the card showing, go **Network → Offline** and reload. The card
    **still renders from cache** (§15.1). **Send does NOT queue** — by design: a queued send would
    report success from a dead dock and leave you believing your paperwork went out (§12.4). You
    should see a plain *"No signal. Send this when you're back online."* and the packet still
    waiting. A silent success here is the defect.
11. **DRIVING variant:** with the app in a DRIVING state, the card must **not** offer Send — it
    shows *"Paperwork ready — review it when you stop."* and no button (Forbidden #11). (Hard to
    trigger on desktop — approximate or defer to handset; don't log as a defect.)
12. **The archive still works:** `/protection/packets` still lists drafted packets as history.
    The rework *added* the inline card; it did not remove the archive door.

## J6 — Money lifecycle `[M4-FR5, M9-FR4]`
1. **Money**: month summary (Meter treatment), receivables list with status pills + aging.
2. Each receivable: one **Next action** (nudge / escalate / mark paid).
3. **Mark paid** → state flips, month total moves, paid event lands in earnings (the DDD counter).

---

# TIER P1 — the daily surface

## J8 — Report a lot status, with proof `[M1-FR7, F10, F7]`
1. Map "at" the DEV truck stop → floating **report** chip → Empty/Some/Full, big targets.
2. Submit **Full** → pin badge updates within a minute; `now · 1 driver`-shape freshness.
3. Move 50 km away, retry → refused/gated (geofence presence proof).
4. **More** → points moved for the accepted report; re-spamming hits the cooldown.

## J9 — Service & repair `[A5, DoD#6]`
1. Map → **Service** chip → repair/tire/wash/parts pins (Dallas is richer).
2. Card: **tap-to-call** where a phone exists, hours **verbatim** (never "open now"), service list,
   directions.
3. A facility with **no phone** → call row **absent, not empty**.
4. Admin → Flags → toggle `a05_service_preset` **off** → reload Map → **Service chip gone**
   (server-driven row). Back **on** → returns. If the toggle refuses on its gate: that's the
   `register_flag` bypass twin — **log exactly what happened**.

## J10 — Weigh stations `[E3.1]`
Map (Drive) around Dallas → weigh-station pins (small square) → report **open/closed** → status +
freshness update; armed load → corridor surfaces **scales ahead**.

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
4. Cancel per policy → both sides update; cancellation email in Mailpit.

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
4. **More → Appearance**: manual light/dark override persists across reload; map style pairs.

---

# TIER P2 — breadth and guards

## J18 — Accessorials `[M4]`
File a TONU from a cancelled DEV load; a layover from an overnight dwell; snap a lumper receipt →
OCR draft → each rides the same pipeline into Money with its own type.

## J19 — Decision tools `[M8]`
`/load/calc` states its **basis** (sample sizes / heuristic), never fakes precision; Map →
sleep-solver ranks tonight's options.

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
