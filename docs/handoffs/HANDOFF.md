# HANDOFF.md — pointer

This file is a **pointer**, not content. The current state, decisions, per-state
results, exact next task, and blockers always live in the latest numbered handoff:

➡️ **[HANDOFF-126.md](HANDOFF-126.md)** — read this first, every session.

> **126** was three owner instructions — fix the PWA install, fix viewing and rating
> facilities, then explain and repair `/load/calc` and `/money/audit`. **§23 entries
> 152–154**, three commits, migration **0077**. Gates: **pytest 1935 → 1942, vitest
> 918 → 962, layout 333 → 349.**
>
> **Stack UP · everything PUSHED · production CURRENT at `0077`.** All three entries are
> LIVE, verified by reading the SERVED bundle and by measuring the migration's effect on
> production before and after.
>
> **THE PATTERN, and it is the fifth face of the coin 122–125 each turned — the one that
> explains why the other four survived: A SUBSTITUTE THAT ANSWERS FOR THE SYSTEM WILL
> AGREE WITH ANOTHER SUBSTITUTE BEFORE IT AGREES WITH THE SYSTEM.** Two fixtures supplied
> a facility `name` the API has never returned, so **every facility page in this product's
> life had a blank `<h1>`**. Every facility test called `askQuestion()` — the function
> *under* the button — while that button was disabled in every state it rendered in, so
> **nobody has ever asked a question.** And `test/pwa.test.js` read the manifest on disk
> while the app was installable and **nothing in it ever asked to install.**
>
> **I WROTE THE FOURTH INSTANCE MYSELF AND IT PASSED OVER THE DEFECT IT WAS WRITTEN FOR.**
> `Page.getInstallabilityErrors` reads like Chromium's own verdict and **returns `[]` for
> everything headless** — including a bare page with no manifest. Sabotaged back to entry
> 143's `"icons": []`, my new check went green. **Removed rather than annotated**, because
> a check that does not exist is worse than no check: it makes the next person stop
> looking. Every fix moved the assertion to the boundary the real thing crosses — HTTP for
> the name, a real click for the button, fetched PNG bytes for the icons.
>
> **The second finding cost a driver money: a zero that means "we did not measure this"
> was rendered as a measurement.** `expected_detention_cost` returns `(0, 0)` with no
> samples and the calculator showed a confident **−$0.00 for detention, folded into the
> headline** — on the screen used to accept or refuse a load, inside the app whose thesis
> is that detention is what costs them. **And re-running a settlement audit multiplied the
> money owed: 15000 → 30000 → 45000** over three presses of Run, which is the normal act
> because the figures are typed by hand.
>
> **Also: 41 of 18,326 facilities have a profile**, so for 99.8% of pins the facility
> screen was six cards each announcing that it had nothing, under that blank title.
>
> **The owner's next actions are unchanged and none is code: the 140 records with no
> bytes, `--marker-500`'s contrast, and the handset sensor test — now deferred eleven
> times and upstream of the whole condition flow. 126 §3.**

➡️ **[HANDOFF-125.md](HANDOFF-125.md)** — the session before, and still the reference for
the wallet, queued-capture and image-pipeline detail.

> **125** closes the session that ran to nine owner instructions and **§23 entries
> 144–151**. Gates across the whole run: **pytest 1842 → 1935, vitest 885 → 918, layout
> 325 → 333**, plus a new `make ui-image` in `make ci`. Six migrations (`0071`→`0076`).
>
> **Stack DOWN · everything PUSHED · production CURRENT at `0076`.** ~~149 and 150 are
> LIVE and verified; §23 entry 151 IS NOT DEPLOYED.~~ **Corrected in 126: 151 WAS already
> deployed.** `qa__item--pending` — a string that exists only in 151's commit `1594754` —
> was in the served bundle before 126's first deploy. 125 applied its own "read the served
> bundle" rule to 150 and not to 151. Seven deploys, a verified offsite backup before each.
>
> **THE PATTERN, and it is the fourth face of the coin 122, 123 and 124 each turned:
> A THING THAT RENDERS IN EVERY CASE EXCEPT THE ONE IT EXISTS FOR.** §15.1's queued-item
> row went inside the surface's four-state load chain — the obvious place — and that chain
> is in its FAILED branch precisely when the driver is offline, which is precisely when the
> queued item exists and is the only thing on the screen not in doubt. **It would have
> shipped rendering perfectly in every state a developer looks at.** The capture chip at
> the foot of `DocsSurface` has been outside that chain for exactly this reason since it
> was built, with a comment saying so; the reasoning had never been carried up the file.
>
> **AND THE LAYOUT HARNESS MEASURED NOTHING, TWICE — the same shape as the defect it was
> measuring.** Seeding the write queue is not enough: the harness's app is ONLINE, so
> `flushQueue` drained the queue against the mocks before the first assertion, and
> `docs-queued` cheerfully measured an empty wallet under that name. A hanging POST is what
> "no signal" actually is. *The harness is also what caught the chain defect above, because
> it could not render the state either.*
>
> **The counterweight — entry 149 is a fix deliberately NOT made.** The obvious move was to
> give the wallet the signed `/media` URLs that made the contact sheets fast. A signed URL
> carries a fresh `exp` and `sig` per render, so the browser cache key changes every time,
> and the viewer's contract — *"a document opened at home opens again at the scale"* —
> holds only while the immutable year-long cache is hit by the SAME url twice. **On the
> screen that produces a CDL to a DOT officer, a changed cache key with no signal is the
> document not existing.** Two surfaces, two mechanisms, deliberately not unified.
>
> **Measured, not asserted:** a production credential **1,836,147 → 3,988 bytes (460×)**;
> load paperwork averaging 261–853 KB and reaching **6.3 MB**, all of it previously opening
> onto "Loading…"; a camera frame **6.7 MB → 731 KB in 187 ms**; a notice tap **2,490 ms →
> 25.9 ms**. And a deploy is now verified by reading the SERVED bundle, because twice this
> session a deploy reported success and changed nothing.
>
> **The owner's next action is unchanged and is not code: 140 production records have no
> bytes** — everything uploaded 26–28 July, from the swallowed `SignatureDoesNotMatch` era.
> Leave them, purge them, or tell the drivers. **125 §3.**

➡️ **[HANDOFF-124.md](HANDOFF-124.md)** — two sessions before, and still the reference for
the email, dedupe and broker-attachment detail.

> **124** was six owner instructions — make images faster, move email to background jobs,
> deploy, stop duplicate emails, send the broker the actual PDF — and each ended somewhere
> further down than it started. Fourteen commits, **§23 entries 144–148**, six migrations
> (`0071`→`0076`). Gates went **pytest 1842 → 1929, vitest 885 → 905**, layout 325, plus a
> new `make ui-image` in `make ci`.
>
> **Stack UP · everything PUSHED · DEPLOYED.** `haulmeter.online` is **CURRENT at `0076`**,
> six deploys, a verified offsite backup before each.
>
> **F-01 IS CLOSED AND EVERY CRITICAL IN THE AUDIT IS NOW CLOSED.** Production email leaves
> the box for the first time in this product's life — the SMTP block was placed on the VM
> with the owner's explicit authorization, transferred by `scp` so the app password never
> reached a command line, and proved by a rehearsal notice to an owner-controlled inbox
> carrying a real Gmail Message-ID. All 8 Criticals, all 17 Highs, all 11 Mediums closed;
> two Lows remain.
>
> **THE PATTERN, and it is the third face of 122's and 123's coin: a thing CORRECT IN ONE
> PROCESS AND WRONG IN ANOTHER, with every test that could see it written in the process
> where it is right.** `media_url`'s path is right for the API router and wrong inside an
> `<img>`. **The pack link is right for the API router and wrong in a broker's browser.**
> `_wire_object_storage` ran in the API's lifespan and the worker is a different process. A
> unique index lived in a migration and the test database is built by `create_all`. The
> budget's `dispatched_at` equals the decision only while the send is synchronous. **Five
> instances, two of them shipped to production.**
>
> **The first of those I SHIPPED, and it broke every contact sheet in production.** Caddy's
> SPA `try_files` answered `haulmeter.online/media/…` with **HTTP 200 and index.html** —
> not a 404, a 200 — which the browser tried to decode as an image. Nothing threw, nothing
> logged. It failed identically in dev, and the curl checks that "verified" it hit
> `localhost:8008` directly, supplying by hand the one thing a browser never supplies.
> *A test that compares `src` to a STRING cannot catch this, because a string has no origin.*
>
> **THE SECOND ONE IS THE ONE TO READ, and the owner found it by asking a question.** Every
> pack link ever emailed to a broker returned **HTTP 200 with index.html** — the driver
> app's sign-in screen. It had never worked in production, and F-01 hid it: no counterparty
> mail left the box until the day before, so nobody had ever clicked one. **Then the fix
> deployed twice and did nothing** — the Caddyfile is a single-file bind mount and
> `deploy.sh` replaces files by unpacking a tar, so the container kept serving a twelve-day-
> old config while `caddy reload` logged "using config from file". A deploy that reports
> success and changes nothing is the worst failure mode available.
>
> **And the twin, in the tests: three of four race tests proved nothing.** Measured — the
> unique index could be DROPPED and all 24 dedupe tests still passed. Only the version that
> waits on `pg_stat_activity` until the loser is genuinely blocked on the index goes red.
>
> **Measured, not asserted:** a camera frame **6.7 MB → 731 KB in 187 ms** off the main
> thread; a notice tap **2,490 ms → 25.9 ms**; thumbnails **0.35 MB against 14.34 MB** of
> originals; a broker's mail now carrying **98,214 bytes** of PDF beside its link.
>
> **The owner's next action is not code and is the sharpest thing on the board: 140
> production records have no bytes** — everything uploaded 26–28 July, from the swallowed
> `SignatureDoesNotMatch` era. Leave them, purge them, or tell the drivers. **124 §3.**

➡️ **[HANDOFF-123.md](HANDOFF-123.md)** — three sessions before.

> **123** was driven entirely by the owner looking at real screens on a real phone and
> saying what was confusing. Nine commits, **§23 entries 135–143**. Gates went
> **pytest 1813 → 1842, vitest 796 → 885, layout 289 → 325**, plus a new `make ui-pwa`
> in `make ci`.
>
> **Stack DOWN · everything PUSHED · DEPLOYED.** `haulmeter.online` is **CURRENT at
> `0070`** — four migrations applied (`0067`→`0070`), backup taken first and verified
> offsite, and the deployed PWA confirmed installable and offline-capable by driving a
> real browser against the live domain.
>
> **THE PATTERN, and it is 122's twin turned inside out.** 122 found mechanisms *built,
> correct, exported and reached by nothing*. **123 found things the governing documents
> SPECIFY that had never been built at all** — §8's button loading state, §7.2's
> bottom-anchored primary action, §10.3's per-receivable next action, and an installable
> PWA. **Three times the comment asserting the capability sat directly above the code
> that made it impossible.** index.html says *"iOS requires an INSTALLED PWA for push at
> all"* four lines above a manifest with `"icons": []` — so **the app has never been
> installable and Web Push on iOS has never been reachable.**
>
> **Two figures were lying to drivers.** The Money tab's hero summed
> `recovered + fuel_saved + flagged` under the words **"Delivered to you"** — a lifetime
> total including money an audit merely *suspects* is owed — telling a driver they had
> received **$1,432.50 when they had received $987**. And `arrive` wrote a GPS ping at
> **the facility's own coordinates**, so the position fix a detention claim rests on, on
> the path a driver takes *because the sensor did not fire*, was a reading of where the
> warehouse is.
>
> **And the twin lesson, in the tests: a SELECTOR standing in for an IDEA stops standing
> for it the moment the page grows** — `.cta:not(.cta--text)` was read everywhere as "the
> filled Primary" and counted the first Secondary as a rival. Worse, **the mocks: every
> packet harness state mocked a LIVE load, every live Load state mocked `accruing`** — so
> the two states a driver is in most often had never been rendered by anything.
>
> **The owner's one action is unchanged and this deploy did not fix it:** the `SMTP_HOST`
> edit on the VM (F-01, open since 121). The post-deploy worker log names the scale —
> `dunning … skipped_no_email: 11` of 14. **123 §3.**

➡️ **[HANDOFF-122.md](HANDOFF-122.md)** — four sessions before.

> **122** was six owner-supplied work contracts run back to back, each with its own report at
> the repo root: **M3 detention**, **wedge delivery**, **location integrity**, **evidence
> integrity**, **auth boundary**, **credential control**. Gates went **pytest 1558 → 1813,
> vitest 746 → 796, layout 283 → 289**, all green, with three migrations (**0067, 0068, 0069**).
>
> **Stack UP · 43 commits UNPUSHED · NOTHING DEPLOYED.** `haulmeter.online` still serves **121
> at `0066`**, so three migrations are pending on the box.
>
> **The finding that repeated in six different subsystems: a mechanism built, correct, exported
> — and reached by nothing.** The dunning cadence, the broker's pre-detention warning,
> `needs_rehash`, `build_trace`, `complete_credential_change`, `must_change`. All tested, all
> green, none with a caller. The built-and-inert tally is now **six**.
>
> **Three were worse than their findings said.** Nothing in the product had ever written
> `contact_email`, so the detention wedge could not deliver to anybody *by construction* —
> a second, independent mechanism beside F-01. A pack whose own PDF says "HASH CHAIN BROKEN —
> do not rely on this pack" was being pinned, linked and emailed to brokers. And an
> admin-issued temporary password silently became the permanent one, because `must_change`
> reached only the admin console and the change endpoint did not exist.
>
> **And the twin lesson, in the tests: six consecutive passes caught a revert-check that proved
> nothing** — *the test arranged the appearance of the condition rather than the condition*.
> A monkeypatched name over a shared object; a flood below the ceiling it meant to breach; a
> race planted inside one session; an identity map answering for Postgres; and, finally, a
> shell variable that made six reverts silently not happen.
>
> **The owner's two actions come first and neither is code:** the `SMTP_HOST` edit on the VM
> (F-01, open since 121) and the push + deploy. Then the first live send should be a rehearsal
> to an owner-controlled inbox — two independent blockers lift at once and that is the only
> test covering both. **122 §4.**

➡️ **[HANDOFF-121.md](HANDOFF-121.md)** — five sessions before.

> **121** was two instructions. *"Approved, do the loading-state work"* closed **five
> findings — U-06, U-09, U-10 (criticals), U-11 and U-12** — every finding that decision was
> blocking; the proposal PROPOSED since 2026-08-07 is **design-prd §23 entry 131** and the
> four-state rule is now on the **§22.3 DoD**. Then *"proceed with the portal touch
> targets"* closed **U-04 and U-05** (**entry 132**).
> **Open findings 7 → 5, and NOTHING IS PARTIAL any more. Every High in both audits is
> closed;** one critical is open (F-02) and one blocked (F-01).
>
> **All five were one defect.** Every fetching surface had two states, so `null` had to
> mean either data or no-data and the codebase chose data — `livePins ?? SAMPLE_PINS`.
> That fired on **every cold open**, not only offline: the first thing a driver saw, every
> time, was fabricated truck stops they could route to. Sixteen exports across ten
> importers are gone, portals included; `fixtures.js` is kept as a tombstone because an
> absent file gets recreated without anyone reading why.
>
> **Read §4.** The skeleton pins were `--line-1` — right on a card, invisible on a night
> basemap of the same value. Six pucks in the DOM, `visibility: visible`, counted by the
> layout harness, and **invisible to a human**. 745 unit tests, 271 layout checks and two
> token-discipline sweeps all passed over it. It was found by throttling the network and
> looking at the screenshot, which the kickoff said to do twice. *A colour can be a
> legitimate token, correctly applied, and still be invisible where it is used.*
>
> **Read §5.** Removing the fixtures showed that **thirteen checks had been measuring
> them**: nine unit tests (three of which stubbed an endpoint but never set a session, so
> `apiGet` threw before the stub was consulted) and four harness states whose own comment
> admitted it. The most useful is `facility`, which **did not** go red — it had no `ready`
> selector, so it kept passing while measuring §15.4's error line under the facility's
> name. *A state with no `ready` cannot tell a screen from its own error message.*
>
> **The Meter gained no loading state** (§9, entry 52): Money replaces the card, so The
> Meter renders once with a real number rather than a confident **$0.00 in Mono** over the
> driver's month. **`money.empty` was translated into all six locales and rendered by
> nothing** — found by applying the four-state rule, which is that rule earning its place.
>
> **The last open critical is closed, and the fix is the one that does NOT make the gates
> block anything.** `enabled` was one column doing two jobs — a code default and an
> operator's decision — so `register_all` wrote it by assignment and `enable()`, the only
> function that reads a validation gate, was never on the path. Measured on the box:
> **three modules carry gates, all SIX were unsatisfied, all three were live** — M3 has
> been sending broker notices with no legal sign-off recorded. Making the gates block the
> default would have taken the detention clock dark, and satisfying one asserts a legal
> review happened, which a deploy may not decide. So the columns split, `enable()` regains
> its monopoly, and **the gate now says out loud what it cannot enforce** — reported at
> every boot. Migration **0066**, backfilled so no box changes behaviour.
>
> **The portals were worse than the audit said and the harness nearly died proving it.**
> U-05 described "two portal controls (40 dp)"; there were **seven** below §6.5's floor and
> the worst was `.switch` at **233 × 20 dp** with no height declared at all. Registering the
> two portals then found three reflow defects nothing had ever measured — a bookings table
> at **437 px** dragging the page sideways, and `min-width: auto` on an `<input>` for the
> **third session running**, plus its grid form (`1fr` → `minmax(0, 1fr)`).
>
> **And §8.2 is the section to read.** Generalising the harness's scroller exemption to walk
> ancestors — which it had to, since a table is `table > thead > tr > th` — found
> `overflow-x: auto` computed on `main.app-content`, above every element on every surface,
> because **CSS promotes `visible` to `auto` when the other axis is not visible.** That
> silently exempted **the entire app** from LAW 0's only mechanical check, and the full
> 279-check sweep **went green over it.** Caught by restoring a defect and watching the test
> pass when it should have failed. *A sabotage that comes back green is not a safe fix; it is
> a check that does not exist.*
>
> **Three findings needed a judgement rather than code, and two were judged "do not change
> the code".** F-25's profit model keeps its conservative arithmetic and gains the
> disclosure it was missing (`detention_recovery: assumed_none`) — netting in a recovery M3
> has not collected would be the worse error on the screen a driver accepts a load on.
> **F-19's premise does not reproduce:** the ingest pipeline never calls `merge_facilities`,
> it calls `add_source`, so there is no automatic destructive merge; corrected Medium → Low,
> and its review surface is left to the A9 session rather than half-built. F-27 waits on
> F-23's schema change.
>
> **Open findings 7 → 3, all Low. Every High and every Medium in both audits is closed.**
> F-01 is the only Critical left and needs one command on the box. **One owner decision
> remains — `--marker-500`'s contrast — because a palette colour is §22.2 and entry 118's
> delegation does not reach it.**
>
> **Stack UP · PUSHED · DEPLOYED. `haulmeter.online` serves 121 at head `0066`.** The owner
> pushed and then asked for the deploy: sessions **113→121 in one deploy, seven migrations
> 0060→0066**, backup taken first, verified end to end. `git fetch` also worked for the first
> time since 117, so the ahead-count is an observation rather than arithmetic and that
> four-session caveat is resolved.
>
> **The deploy answered F-01, the last blocked critical, and the answer is the bad one.**
> `SMTP_HOST='mailpit'` with `configured=True` on the box — so the gateway never fell back to
> recording, it delivered to a container on the VM. **No broker has ever received a detention
> notice from the deployed product, and F8 recorded every one as sent.** M3 is the wedge. The
> code has been correct since entry 122; the fix is one `.env` edit on the VM, which is the
> owner's action under rule 9 and is deliberately not done from here.
>
> **And it opened N-03: the worker boots against the pre-migration schema.** `depends_on`
> waits for postgres, while the migrations run inside the API's command — so all seven jobs
> failed on schema 0059, `detention_clock` included. Self-healing via backoff, but up to an
> hour for four of them. **Fixed and deployed later the same session:** the migration is its
> own one-shot `migrate` service and both the api and the worker wait on
> `service_completed_successfully`, in BOTH compose files. Proved by exercising the race — the
> local DB was downgraded a revision so the migration was genuinely pending, and the worker
> logged zero errors where it had failed all seven jobs — then observed on production, where
> `migrate` exits before api and worker start. **HANDOFF-121 §11.**

➡️ **[HANDOFF-120.md](HANDOFF-120.md)** — six sessions before.

> **120** was one instruction — *"read the latest handoff and restart the app"*, then
> *"proceed using your best judgement"* — and it worked the audit queue to the end:
> **fourteen findings closed** — F-30, F-32, F-33, F-09, F-10, F-15, F-16, F-20, F-26, F-11,
> U-03, plus **N-01 and N-02**, which the session opened and closed itself. U-04 is partial,
> its remainder blocked on a decision already on the board. Migration **0065**.
> **Open findings 18 → 7.** **Nothing un-blocked is left** — every remaining item needs an
> owner decision, a command on the box, or a judgement about intended behaviour.
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
> **U-03 found a defect visible to EVERY driver, not only the five non-English ones.**
> `resolve()` returns the RAW KEY when a string is missing from all six locales, and 13 were
> — including all nine `facility.type.*`. `money.state.acknowledged` was rendering as
> literal text on the Money tab. The JS parity test cannot see this: six identical holes are
> perfect parity, which is why the new check enumerates the vocabulary from PYTHON.
>
> **U-04 put five unmeasured surfaces into the harness (229 → 257 checks) and three defects
> came with them.** `ClaimSurface` — the screen every detention notification deep-links to —
> had a **40 dp** back button, the only one of the nine in `surfaces/` that did.
>
> **Stack UP · thirty-five commits UNPUSHED · nothing deployed.** `git fetch` still cannot
> run here — **re-fetch before pushing.**

➡️ **[HANDOFF-119.md](HANDOFF-119.md)** — seven sessions before.

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

➡️ **[HANDOFF-118.md](HANDOFF-118.md)** — eight sessions before.

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

➡️ **[HANDOFF-117.md](HANDOFF-117.md)** — nine sessions before.

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

➡️ **[HANDOFF-116.md](HANDOFF-116.md)** — ten sessions before.

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

➡️ **[HANDOFF-115.md](HANDOFF-115.md)** — eleven sessions before.

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
