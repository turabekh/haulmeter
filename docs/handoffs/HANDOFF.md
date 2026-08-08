# HANDOFF.md — pointer

This file is a **pointer**, not content. The current state, decisions, per-state
results, exact next task, and blockers always live in the latest numbered handoff:

➡️ **[HANDOFF-120.md](HANDOFF-120.md)** — read this first, every session.

> **120** was one instruction — *"read the latest handoff and restart the app"*, then
> *"proceed using your best judgement"* — and it worked the audit queue: **twelve findings
> closed** — F-30, F-32, F-33, F-09, F-10, F-15, F-16, F-20, F-26, F-11, plus **N-01 and
> N-02**, which the session opened and closed itself — migration **0065**.
> **Open findings 18 → 8**, and nothing un-blocked is left that does not need the owner.
>
> **Every finding that could be closed without an owner decision now is** — again. What is
> left is four blocked on facts nobody here can get, and four needing the owner's judgement
> about intended behaviour rather than code. **HANDOFF-119 §5.1 is untouched and is still
> the highest-value thing on the board**; §22.2's carve-outs were checked against entry
> 118's delegation and a new palette colour and a new component pattern still stop and ask.
>
> **F-30's root was deeper than the audit's "English-only".** Matching asked
> `term in utterance`, so *"I am in Las Vegas"* routed to fuel and *"my sleeper berth heater
> is broken"* routed to sleep — neither in the audit. Adding five languages on top of
> substring matching would have multiplied the bug by six. Accuracy is asserted **per
> language** now, which is what the DoD always said and nothing measured.
>
> **Read §4: three times a fix here was wrong and the process caught it.** I built an inert
> mechanism — a locale fallback that made `locale` unobservable, with two API tests
> "proving" a threading that passed without the endpoint change at all — and removed it. A
> sabotage pass found the F-09 fix had **no test that the job was wired**, which is F-09's
> own shape reproduced inside its own fix. Another found an accent test that proved nothing.
> None of it was caught by the suite going green.
>
> **F-16's obvious fix shipped the hole:** stripping `"` and `\` leaves `;`, which separates
> header parameters. The test caught it only because it asserts the header PARSES rather
> than asserting the hostile text is absent.
>
> **Verified against the running system, not the suite:** the live TPIMS feed carries a
> timestamp on all 51 records (so F-32 costs nothing today); the second worker restart ran
> **only** `detention_clock` where all seven used to fire; 11 infra files including
> `deploy.sh` now enter the review dump. And F-09's risk was checked before wiring — the F4
> evidence pack does not read `location_ping`, so a purge cannot destroy a claim's proof.
>
> **N-01, opened and closed in the same session, is F15's message catalogue's FIRST
> producer** — `register_message` had been written, exported and called by nothing but its
> own test. The copilot answers in the language it understood now: verified over HTTP on the
> box, `ru` while driving returns the deferred confirmation in Russian with
> `audio_ref: audio://ru/…`. **N-02 is its sequel and closed too:** driver push
> notifications were English-only at **10 dispatch sites across 7 modules**, including M3's
> detention P0. Nine now read from F15 — **366 rows across 61 keys, seeded at boot**. The
> interpolated LABELS were the trap: *"Falta: pickup photos"* is an English fragment inside
> a Spanish alert, and the first sabotage pass **missed it** because
> `notify_protection_gap` had no test at all.
>
> **Stack UP · thirty-one commits UNPUSHED · nothing deployed.** `git fetch` still cannot
> run here — **re-fetch before pushing.**

➡️ **[HANDOFF-119.md](HANDOFF-119.md)** — the session before.

> **119** worked the 2026-08-07 audit queue: **nineteen findings closed, two partial**, and
> answered one of the audit's three open questions. Three of
> the eight criticals are closed (F-13, F-21, U-07) — **every critical that could be closed
> without an owner decision now is.** Four are blocked on things nobody in this environment
> can supply; the last, F-02, needs a decision before anyone starts.
>
> The four money races are closed **in Postgres**, because an application check reads rows a
> concurrent transaction has not committed yet: a partial unique index on the ledger, an
> EXCLUDE constraint on booking, a row lock before the points balance is read, and a log
> row written whether or not the contribution paid. Migration **0060** refuses to apply
> against data that already violates either constraint rather than failing mid-deploy.
>
> **F-21 was filing invoices for stops that never happened** — M4 kept the §23 entry 73 bug
> M3 was cured of, and M4 uses that pair to decide whether a claim EXISTS, not merely what
> it is worth. **U-07 was losing a driver's evidence and reporting "synced"** over it.
>
> **Closing a finding opened one.** Tokenising the map pin made its contrast checkable in CI
> for the first time, and white on `--marker-500` is **2.04:1** in dark theme against a 3:1
> floor — the "Some" pin and the OPEN weigh-station pin. It shipped that way; it was
> unobservable while the colour was a literal. **Owner decision needed.**
>
> **Two of the audit's own claims did not survive contact with the code** and are corrected
> in 119 §6 — the stale-pin symptom does not reproduce, and the worst-case Load stack puts
> ONE card above the Meter, not three. Every fix here was proved by restoring the defect and
> watching the new test fail, including the one where all seven pre-existing m04 tests still
> passed against the bug.
>
> **F-07 closed too: authentication had no throttle of any kind.** Bounded per identifier
> and per IP in Postgres — not Redis, which degrades silently and would fail the control
> open — and checked BEFORE the Argon2 hash, which is the half that answers the
> denial-of-service rather than only the credential stuffing.
>
> **Also closed: F-17/F-18** (the AI cost cap had never governed a call and had no period —
> and the fix that matters is the third option: a missing budget row falls back to the
> default, so there is neither uncapped spend nor an outage caused by a missing row) and
> **F-23** (the settlement audit compared one document's payments against every receivable
> the driver had ever had).
>
> **And a facility now knows what calendar it keeps (F-14, F-22).** The audit named this
> its own prerequisite: F2 had no timezone, and `home_timezone` is written by nothing
> outside the tests, so the product's only notion of local time was inert. An 8pm→4am
> Dallas layover is ONE UTC day, so real claims were being **refused**. Cost a dependency;
> the image went 4.61 → 4.83 GB, measured before deciding.
>
> **And the counterparty send path (F-03, F-04, F-06):** every successful send in the
> product's life returned the same provider ref `smtp-1`, the gateway production actually
> uses was tested by nothing, and a failed send still wrote `sent_at` — so the row claimed
> a delivery it never got. Real Message-IDs, a tested lazy gateway, and a five-minute
> retry sweep that never re-presents a bad password to Gmail.
>
> **The loading-state §23 proposal now exists** (`docs/audits/S23-PROPOSAL-loading-state.md`,
> owner-supplied, claims verified) and is **awaiting a decision**. Approving it unblocks
> U-06, U-09, U-10, U-11 and U-12 — four criticals and a High — in one session. That, plus
> seven other cheap decisions, is the whole of 119 §5.1 and the best thing to read first.
>
> **Stack DOWN · twenty-four commits UNPUSHED · nothing deployed.** `git fetch` still cannot
> run here — **re-fetch before pushing.**

➡️ **[HANDOFF-118.md](HANDOFF-118.md)** — two sessions before.

> **118** is a short session with **no source changes**: the owner asked for the stack to be
> restarted, then for a handoff and a shutdown.
>
> The stack came up clean and was verified from outside the containers — `/health` 200,
> UI 200, `0059_f13_config_decl (head)`, the Tampa origin still seeded. The four gates were
> **re-measured rather than carried forward** and hold identically to 117: **pytest 1391 ·
> vitest 689 · layout 225 · import-linter 30/30 · ruff clean.**
>
> One thing turned up, and it is neither a leak nor a defect: **`collect_files.py` is tracked
> and pushed.** Handoffs 089, 098, 099 and 117 all describe it as untracked and deliberately
> left alone — *"not ours to commit or delete."* It was swept into session 113's A6 commit
> (`9cf9775`, 2026-08-02) and has been in the public repo since. Read in full: 79 lines, no
> network, no credentials, nothing references it. **Left in place** — half that rule was
> broken by accident, which is not a licence to break the other half on purpose. 118 §4.
>
> **Stack DOWN · six commits UNPUSHED · nothing deployed.** `git fetch` could not run this
> session (no credential), so the ahead-count is arithmetic, not observation — **re-fetch
> before pushing.** The next task is still the handset background-sensor test.

➡️ **[HANDOFF-117.md](HANDOFF-117.md)** — three sessions before.

> **117** did two things the owner asked for, and both turned up something under them.
>
> **Email has a real provider.** Gmail SMTP, dev and production on one account, closing
> the question 116 §9 left open — and **verified by a real send the owner confirmed
> receiving**, which is the first time this product has reached a person outside the
> box. No code changed; the gateway already did STARTTLS and `login()`. What the owner
> had saved (`GMAIL`, `GMAIL_APP_PASSWORD`) was **read by nothing** — settings bind
> `SMTP_*` — so it would have looked configured while every send fell back to recording.
> §23 entry 126.
>
> **The Load tab, from a screenshot of a real stop.** "Tapping on photos not working"
> was real: the row was a plain `<li>` while every row above it was a button. Nothing
> failed, because nothing was wired. Under it were two larger things — §10.2's ladder
> **rendered no primary action at all** in the state covering most of a stop, and the
> card mixed facts with actions at identical weight, which is *why* it arrived as a bug
> report. §23 entries 127–129.
>
> **And the fifth built-and-inert engine: §5's ON_SITE has been unreachable in a truck
> since the deriver was written.** Presence reached the client only as an ENTER edge; a
> reload wiped it and the "I've arrived" fallback never set it — the path a driver takes
> precisely when the background sensor did not fire. The fact was in the database the
> whole time. *An edge is a fact about a moment; a state has to be askable at any moment.*
>
> **Stack DOWN · four commits UNPUSHED · nothing deployed.** The next task is still the
> handset background-sensor test.

➡️ **[HANDOFF-116.md](HANDOFF-116.md)** — four sessions before.

> **116** walked the stop auto-pilot end to end in a real browser, which is what two
> sessions of building had never been subjected to. **It works.** A human adds a load,
> arms a stop, photographs a BOL and drives away; the review card arrives on the Load tab
> about ten seconds later, the sheet opens over it, Send works, and **the driver's BOL is
> in the PDF** — 99,747 bytes, titled "Stop paperwork packet", two embedded images, naming
> the broker and the dock, with the word "Detention" nowhere in it.
>
> **Walking it also found that this product had never sent an email.** There was no SMTP
> gateway in the codebase — only the recording gateway and Web Push — and
> `smtp_host`/`smtp_port` sat in config read by nothing, while Mailpit had been in compose
> since session 0 holding **zero** messages. So Phase DoD item 1 was unreachable and the
> detention wedge's notice had never left the box. **Fixed in the same session:** Mailpit
> 0 → 1, and the link in that email returns the paperwork with the BOL in it. The whole A1
> chain now closes. That is 116 §6 and §23 entry 122 — the FOURTH built-and-inert engine,
> all four sharing one shape: *a deferral that cannot fail is indistinguishable from a
> finished feature.*
>
> Walking it also found the card showing the **oldest** waiting draft rather than the stop
> just left — two drafts at one dock gave an identical headline while the sheet opened the
> older, empty one. A driver would have sent the wrong document. Fixed. DRIVE.md's claim
> that "the three DEV pins render" was also false: they are three facility types across
> three presets, and the shipper J7-AP arms is invisible until you switch to **Work**.
>
> **Stack DOWN at 116's end · nothing deployed.** (This line read "Stack UP", which
> HANDOFF-116.md's own header contradicted, and its "everything from `a4e282c` onward
> UNPUSHED" was overtaken by the 2026-08-03 push. Corrected in 117.)

➡️ **[HANDOFF-115.md](HANDOFF-115.md)** — five sessions before.

> **115** was scoped as a **surfacing rework** — the A1 automation is built and correct,
> only the way its result reaches the driver is wrong. Re-grepping the seams before
> planning found the first half of that sentence was false. **The Stop Packet a
> dispatcher received contained zero artifacts and one row**: the driver's BOL and cargo
> photos were in the database and not in the document. Measured on the running stack
> before anything changed. Four mechanisms had to be wrong at once, and the suite was
> green over all of them — it asserted the subject line and three *absences*, never that
> the document contained anything.
>
> Also found: **the one-tap fallback drafted nothing.** Only the geofence EXIT created a
> packet, so a driver whose background sensor never fired — the mechanism v2.0 DoD #8
> records as unproven — tapped "Leave this stop" and got no paperwork, unrecoverably.
> And **`load.doc.cargo_condition` is missing from all six locales**, so drivers have
> been reading a raw translation key on the Load tab.
>
> Both halves shipped: the packet contains the paperwork now, and the paperwork **arrives
> as a card at the top of the Load tab** with one Send over a bottom sheet — no hunting,
> no separate screen. **No new notification class** (owner's Option A, §23 entry 121).
>
> **Stack UP · everything from `a4e282c` onward UNPUSHED · nothing deployed** (114 IS
> pushed; the box still serves 112). Phase DoD item 1 was
> *unreachable by construction* and is now merely unmet. **The next task is the handset
> background-sensor test** — everything here rides on a sensor no one has watched work.
>
> **114** is the second half of 113's session. The owner asked for the food half to go;
> executing that decision found, in order: **`m13_vendor` was ON in production over DEMO
> DATA** — 13 seed/probe vendors, 18 appearances still live, so a driver could see
> `Ana Tamales 46eef8` selling invented food wrapped in the §11.7 honesty apparatus;
> **`preset=food` had answered 500 since the chip shipped**, absorbed by MapSurface's own
> catch into the offline path so it looked merely empty; **the chip row never consulted a
> flag**; and **A5's validation gate has never gated anything** (`register_flag(enabled=True)`
> bypasses `can_activate`, in dev and production alike).
>
> Food is switched off in dev **and production** (audited, with an F14 audit row, verified
> from outside the box). The preset row now follows its features. **The gate bypass is
> OPEN — 114 §7**, and it is F13's central promise going unenforced.
>
> **Stack UP · one commit UNPUSHED (`f272c4a`) · nothing deployed** — so the production map
> still renders a Food chip whose feature is dark until a deploy.
>
> **113** builds **A6 — service-center vendors**, the only Group-2 requirement with no
> owner decision in front of it. The requirement asked for one thing (split `m13_vendor`
> so the food half can be deferred while repair shops run); two more were underneath it.
>
> **The shared endpoints made the split a label rather than a gate** — `/vendors/{id}`,
> review, report and confirm all take a `vendor_id`, and a `vendor_id` carries its half
> with it, so a deferred cook's whole sheet stayed readable. And **claiming was improving
> `/facility/<id>` while A6's own validation happens on the map card**: a shop could claim
> its site, enter the number it answers, and a driver tapping that pin still saw the OSM
> number — or, for 28 of 45 repair facilities, no call action at all.
>
> A6 is **pushed, not deployed** — haulmeter.online still serves 112's code, and
> `m13_service_center` does not exist on the box. **A6's validation is unmet by design** —
> it needs a real repair shop to claim a facility and take a call.
>
> 113 also carries an F13 fix with nothing to do with A6: **a flag's description was
> frozen after first boot**, so every box still called the food half "M13 Vendor Network".
> It refreshes now; `enabled` deliberately does not.
>
> **112** finishes **A1 requirement 1 — the capture checklist**, and the finding underneath
> it is that the requirement's own last clause was the hard part: "the checklist is
> configuration (F13), not code" was true in the code and **false in every interface an
> operator has**. `a01.capture_checklist` is the first config key any component in this
> product reads, and `/admin/config` listed only keys somebody had already set.
>
> *(112, still the deployed state)* **112 is pushed and deployed · haulmeter.online CURRENT at `0059_f13_config_decl`**,
> verified against the box, with the backup restored and verified at the new schema.
> (112 ended with the local stack down; 113 brought it back up and it is up now.)
>
> 110 and 111 are one working session, the first under **PRD v2.0**
> (`docs/trucker-platform-prd-v2-amendment.md`, now build law beside the v1.0 PRD).
>
> **110** builds **A5 — Service & repair discovery**, and the finding underneath it is the
> session: **six of the eight OSM service rules had never fired once**, because the extract
> filter never passed the tags they read. 12 repair facilities, 0 tire shops, and **0 phone
> numbers on 4,869 facilities**. The obvious fix would have produced exactly nothing.
>
> **111** takes the owner's delegation of **design-prd rule 6** (agents may now dispose as
> well as propose — §23 entry 118, with two carve-outs) and builds **A12 — Operational
> floor**: offsite nightly backups, a **restore that is performed and verified** (v2.0 §7
> item 7, satisfied), an alert that lives outside the box, and a snapshot identifier so
> "what is the box running" has an answer.
>
> **Stack UP · everything pushed and deployed · haulmeter.online CURRENT.**
> **A12 is COMPLETE and validated** — restore performed and verified, alert fired
> deliberately and the owner confirmed it arrived. All nine covered states were re-extracted
> through the corrected filter: **repair facilities 12 → 458, callable phones 0 → 807.**
> **A5 is still unvalidated** — no driver who is not the owner has used it. A push on a real
> handset is five sessions old.
>
> Read 110 for the starved rules and the A5 measurements; 109 for the measured flake; 108
> for the quiet-hours decision; 099 §11 for the repo being public.

Each session ends by writing the next `HANDOFF-<n>.md` in this directory and updating
this pointer to it. Full history is here in `docs/handoffs/`; the Session-0 bootstrap
(ports, stack, working rules, target layout) is `HANDOFF-000.md`.
