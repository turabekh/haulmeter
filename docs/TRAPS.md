# TRAPS — things that have already cost this project time

**One deduplicated list, replacing the "things a later session will trip over" sections
that nine handoffs (119–127) each rewrote.** Roughly 60% of that content was repetition —
*"the API wedges mid-reload"* was carried forward six times, *"the two image URL schemes"*
twice, `alembic_version` three times — so a session reading the latest handoff met a list
whose oldest entries had been copied more often than they had been read.

**Every trap here was paid for.** Each one names what it cost and where the evidence is.
Nothing is speculative and nothing is style advice.

**Read this when you are about to touch something, not cover to cover.** It is indexed by
what you are doing.

**When you find a new one:** add it here, in the right section, with its evidence — and put
only the session-specific ones in your handoff. A handoff records what happened *that
session*; this file records what is permanently true.

> **The one that catches everything else.** Six of the eight sessions that kept these lists
> ended up writing some version of it, so it goes first:
>
> **A check can pass while asserting nothing about the thing it is named for.** A stub that
> agrees with another stub, a test that calls the function *under* the button, a CDP call
> that returns `[]` for every input, a sabotage that silently did not apply. Before trusting
> a green check on something that matters: **break the thing and watch the check go red.**

---

## 1 · Migrations and schema

1. **`alembic_version.version_num` is `varchar(32)`.** A 38-character revision id applied
   its `DELETE` and then failed writing its own version row. Keep ids short.
   *(124, 125, 127)*

2. **A bare `sa.Enum` inside `create_table` emits its own `CREATE TYPE`.** Create the type
   explicitly, then reference it with `postgresql.ENUM(name=…, create_type=False)`.
   **How it fails is the lesson:** alembic printed `Running upgrade` for *both* pending
   migrations and rolled the whole transaction back — the log said two migrations ran and
   the database had neither. Migration 0057 wrote this down; 0079 re-learned it. *(127)*

3. **A migration-only constraint is invisible to the suite.** The test database is built by
   `Base.metadata.create_all`, so a constraint that exists only in a migration is never
   exercised. **Declare it on the MODEL too.** *(Checked across the whole schema once: 130
   unique indexes identical in both; this was the only deviation, not a systemic gap.)*
   *(124, 125)*

4. **A new module must be added to `MODEL_MODULES`** (`api/db_registry.py`). It is what
   `Base.metadata` is built from, so alembic autogenerate and the test harness both read
   it. Omitting it **fails remotely**: `cannot drop table f01.account`, every test in
   unrelated suites erroring at fixture setup. It hides because pytest *collecting* the new
   module's own test file imports the models as a side effect — so the full suite passes
   and a subset fails. *(127)*

4a. **A unique index over a NULLABLE column is not unique for the rows where that column
   is null — and those are usually the ordinary rows.** m15's "one entitlement per subject
   × kind × window" was written as one `UniqueConstraint` over both subject columns; a
   subject is an account OR an org, so one is always NULL, Postgres treats NULLs as
   distinct, and two identical grants both inserted. Splitting it by subject then left
   `ends_at` doing the same thing one column over — an open-ended grant has no end date —
   and **the suite was green while a live database still accepted the duplicate**, because
   the test happened to set an end date. **Use `NULLS NOT DISTINCT` (PG15+) or COALESCE to
   a sentinel, and prove it by inserting a duplicate rather than by reading the index
   definition.** The general form: every nullable column in a unique index is a hole, and
   the test that would find it is the one using the DEFAULTS a caller actually passes.
   *(132)*

5. **Rebuilding an enum needs the column DEFAULT dropped first.** Postgres refuses to
   re-type a column whose default is expressed in the type being replaced. *(124, 125)*

6. **Verify a migration by querying the schema, never by reading the exit line.** See
   trap 2 for why, and §3 for the production version of the same rule.

---

## 2 · The test harness will lie to you

7. **A fixture that supplies a field the API does not send is invisible until something
   asserts at the HTTP boundary.** Two fixtures agreed with each other about
   `profile.name` for the life of the product, and every facility page shipped with a blank
   `<h1>`. **When a surface reads a field, assert the ENDPOINT returns it.** *(126)*

7a. **A harness fixture that omits a key measures a screen your change never reached.** Two
   states passed green this way in one session: `sheet-confirm` stops before a dock is
   chosen, so the pre-acceptance lines it was meant to measure did not exist; and
   `load-calc-result`'s mock carried no `mpg_basis`, so the MPG disclosure never rendered
   and the state went green over a screen without it. Neither was caught by the harness —
   both by asking *"would this have gone red?"*. The identical failure is recorded two
   fixtures away in the same file about `rate_cents`, which tells you how easy it is to
   repeat. **After adding an element, check the fixture actually produces it, and make
   `ready:` point AT the new element.** *(128)*

8. **A test that calls the function *under* a control proves nothing about the control.**
   Every facility test called `askQuestion()` while the button that calls it was disabled in
   every state it rendered in — nobody could ask a question, and the suite was green.
   **A test that proves a button works has to press the button.** *(126)*

9. **`Page.getInstallabilityErrors` is inert in headless Chromium.** It returns `[]` for
   everything — the real app and `setContent("<html>bare</html>")` alike, measured both
   directions. A check built on it passed against a manifest sabotaged back to
   `"icons": []`. **Do not re-add it**; `pwa/offline.spec.js` argues the case at the top.
   *(126)*

10. **A layout state without a `ready` selector cannot tell a screen from its own error
    message.** `facility` proved it by passing while measuring §15.4's error line. *(121)*

11. **A layout state that holds a request open sets `hang: [fragments]`**, gets no
    networkidle wait, and **must** carry a `ready` selector naming the skeleton class.
    *(121)*

12. **A layout state that seeds the write queue must also hang the replay.** The harness's
    app is online, so `flushQueue` drains the queue before the first assertion and the state
    measures an empty surface under a name claiming otherwise. `docs-queued` and
    `facility-queued` both hit this. *(125)*

13. **The layout harness 404s any path it has no mock for.** Do not write `{__status: 404}`
    to force an empty state — it is fulfilled as a **200 carrying that object**, and the
    state measures a screen full of `undefined`. *(120)*

14. **Adding a class to `TARGET_EXEMPT` removes it from the 48 dp check.** If it is a map
    marker, add it to `MAP_TARGET` too or it becomes unmeasured — which is exactly how
    `.cluster` shipped at 36 dp. *(121)*

15. **A stub returning `{}` where the endpoint returns `null` can crash a render.**
    `/vendors/service-center/{id}` returns `null` for an unclaimed facility;
    `serviceCenter.services.length` on a truthy `{}` throws and collapses every branch below
    it. Both the unit stub and the harness mock carry the note. *(121)*

16. **`ui-components.test.js`'s facility fixture is WRONG-SHAPED and still is.** It nests
    the profile under `facility` while the surface reads `profile.name` and
    `profile.reviews` flat — so it renders an empty `<h1>` and no reviews list, and every
    assertion in that file passes because none of them read the name. `dwell.overall` is
    also required or the render throws. `facility-queued-contributions.test.js` has the
    correct shape; copy from that one. *(125)*

16a. **A Vue render error is INVISIBLE to `expect` unless a test installs an
    `errorHandler`.** It becomes an unhandled rejection: vitest prints `Errors 1 error`,
    the process exits non-zero, and every assertion still passes — so the suite reports
    green while a driver-facing screen is broken. `FleetWorkspaceSurface` threw on
    `holds.holds.length` this way for several sessions, and the only symptom was **`make
    ci` exiting 1 with 1020/1020 green**, which reads as flakiness and trains everyone to
    ignore the red. **Mount with `global: { config: { errorHandler } }` and assert the
    collected errors are empty** — that one line is what makes this whole class assertable.
    Entry 16's fixture is why nothing caught it: the tests passed *because none of them read
    the value*. *(133)*

17. **A sabotage that comes back green is not a safe fix; it is a check that does not
    exist.** And **verify the sabotage applied** — a shell variable once made six reverts
    silently not happen. *(121, 122)*

17a. **"Flaky" is usually a wrong diagnosis. A test green ONLY in the full suite is
    order-dependent, and that is worse.** `food-decide`'s origin check was carried for three
    handoffs as timing-flaky; it was deterministic all along — red **5 runs out of 5** in
    isolation, green only among its 62 neighbours. **Run a suspect file alone, five times,
    before believing the word flaky**: a clean 5/5 red tells you it is order-dependence, and
    a check that passes on another file's timing asserts nothing about the thing it names.
    *(132)*

17b. **A test that sleeps against a debounce races everything else that RESTARTS that
    debounce.** The same check slept 350 ms for a 300 ms `onBounds` debounce and read
    `.at(-1)`. The 50 ms was never the margin: `located` makes MapCanvas recenter and emit
    its **own** `bounds` a beat later, which `clearTimeout`s the debounce and restarts it, so
    the request lands past 600 ms and against a bbox the test never emitted. **Wait for the
    request, not for a duration**, and assert that *a* request carries the thing — never that
    the LAST one does, when which is last is another component's business. The cheapest way
    to see it: stub `fetch` to push `Date.now()-t0` plus the URL into an array, wait
    generously, and print every call in order. It took one run. *(132)*

---

## 3 · Deploy, the box, and the edge

18. **A single-file bind mount goes stale on deploy, and the deploy reports success.**
    `deploy.sh` replaces files by unpacking a tar — a new inode — while a file bind mount
    stays pinned to the one it was created with. `up -d --build` will not recreate a service
    whose definition has not changed, and `caddy reload` re-reads the same stale inode and
    logs *"using config from file"*. **Anything mounted as a FILE rather than a directory
    hits this.** `deploy.sh` force-recreates caddy for exactly this reason. *(124, 125, 127)*

19. **The edge is invisible to every test in the suite**, because they all talk to the
    router directly, where a missing proxy route cannot be seen. Every pack link emailed to
    a broker returned **HTTP 200 with the driver app's sign-in screen** for months.
    `test_broker_link_is_reachable.py` asserts against `infra/Caddyfile`, mounted at
    `/repo/infra` beside the compose files. *(124, 125, 127)*

20. **Verify a deploy by reading the SERVED artifact, not the exit line.** Twice a deploy
    reported success and changed nothing. Read the bundle the browser receives; query the
    schema on the box. *(125)*

21. **`infra/.env` on the VM is `0600 root:root`.** `sudo` the `grep` too, not just the
    `docker compose` — a bare grep fails and psql then eats the flags as a port number.
    `deploy.sh` excludes the file, so a deploy cannot overwrite the box's secrets.
    *(124, 125, 127)*

22. **The API wedges mid-reload if a connection is open, and it looks like a slow
    endpoint.** Measured: `/intel/true-profit` timed out at 60 s wedged and returned in
    **0.24 s** after `docker compose restart api`. **Restart before believing a latency
    number.** *(122, 123, 124, 125, 126 — carried six times)*

23. **Dev's `migrate` service mounts the source; production correctly mounts nothing.**
    Before that fix a newly written migration was invisible to it, and once the database was
    stamped ahead of the image, api *and* worker refused to start. *(122)*

24. **Debug files copied into the api container land in the repo** — `/app` is the mounted
    tree in dev. `ruff` has caught them. *(127)*

---

## 4 · Flags, gates and modules

25. **`register_flag` takes `default_on`, never `enabled`.** Only `enable()` / `disable()` /
    `clear_decision()` may write `enabled`. A flag born enabled never passes through
    `enable()`, which is the only function that reads a validation gate — that is how six
    gates across M3, M6 and M7 came to have never been read while their modules ran
    (audit F-02). **A capability that has never shipped declares nothing and lets its gates
    govern.** *(121)*

26. **`enabled` is nullable and NULL means "no operator decision".** Every read goes through
    `is_enabled` / `is_switched_off`, never the column, or NULL is read as off. *(121)*

27. **An absent gate is unsatisfied, not satisfied.** Treating "I could not find the
    precondition" as "the precondition is met" is F-02's exact shape. *(127)*

28. **`Job.flag_key = None` means always run.** `is_enabled` answers False for an
    unregistered flag, so giving a foundation safety net a flag is how it becomes another
    built-and-inert engine. *(119)*

29. **`register_all` seeds an F9 spend budget for every module**, so a new module gets one
    for free and `test_module_flags` asserts the invariant. F9's cost control had never
    governed a single call before this, because a module with no budget row returned
    silently (audit F-17). *(119)*

30. **The worker's schedule lives in Postgres.** A new job needs no migration —
    `_seed_schedule` writes its row on first boot — but a **renamed** job leaves its old row
    behind and starts due immediately. *(120)*

---

## 5 · Data semantics — where a number lies

31. **A zero from the server may mean "not measured".** `expected_detention_cost` returns
    `(0, 0)` with no samples; `route_fuel_cost` returns `(0, None, "no_network_fuel")`.
    Rendered as `−$0.00` and folded into a headline, that is indistinguishable from a dock
    that never detains anyone. **Render from `basis`, never from the number.** *(126)*

32. **The two image URL schemes are NOT an inconsistency to tidy up.** Signed `/media` URLs
    go in an `<img src>` and are fast; the wallet's `/protection/documents/{id}` is
    session-authenticated, needs a fetch-to-blob, and is the **right** one there — a signed
    URL's `exp`/`sig` change per render, so the immutable cache is never hit twice and the
    offline guarantee dies silently. **Anyone "unifying" these makes the wallet fast on a
    good connection and empty at a scale house.** Argued at the top of
    `test_document_thumb.py`. *(124, 125)*

33. **A queued-item row must live OUTSIDE its surface's load-state chain.** Inside it, the
    row renders in every case except the offline one it exists for. `DocsSurface` and
    `FacilityProfileSurface` do this correctly; any third must follow. *(125)*

34. **`apiGet` serves its cache offline**, so "offline" is not "every read fails". A
    facility or wallet already opened still renders; the endpoints that do **not** cache are
    the ones that fail around it. A test that rejects every fetch is testing the COLD case,
    which is different and rarer. *(125)*

35. **`money_owed` returns EVERY receivable**, settled included, newest-first. The Money tab
    splits and re-sorts; anything else reading it must too. *(123)*

36. **`m3.clock` derives arrival from GEOFENCE PRESENCE**, not from `claim.clock_since`. A
    test that sets the column and expects the clock to run is arranging the *appearance* of
    the condition rather than the condition. *(127)*

37. **`start_claim` defaults `clock_since` to `now()`.** Pass `started_at` when drafting
    from a historical arrival, or the clock records as starting when the poller ran — and an
    evidence window anchored on it finds no pings and mislabels the pack. *(127)*

38. **`f02.coordinates` returns `(lat, lon)`** despite unpacking ST_X/ST_Y — it swaps them
    back. Getting it wrong put a probe's truck at latitude −82 and produced **zero events
    with no error anywhere**. *(127)*

39. **`/facility/search` is a semantic search over REVIEW TEXT**, not a name lookup. The
    name search is `/public/facilities?q=`. *(126)*

40. **`derive_parking_status` RAISES** for a status with no usable reading; gate on
    `has_usable_reading` first. `DynamicStatus.reported_at` and
    `ProfitResult.rpm_after_cents` are both `| None`. *(120)*

---

41. **A per-driver key in localStorage must go under `CACHE_PREFIX`** (`longhaul.cache.`)
    or **logout will not sweep it** — a phone passed between team drivers was handing the
    next one the previous driver's active stop (audit U-02). The layout harness plants these
    keys directly and has to move with them. *(119)*

42. **`F2.Facility.timezone` is resolved lazily and stored.** The first caller to ask pays
    for the lookup; everything after reads the column. A test that creates a facility and
    asserts on `timezone` before anything asks will see `None`, and that is correct. *(119)*

43. **Two sweeps, both 60 s, both unflagged:** `outbound_mail` and `push_delivery`. The
    interval is **first-delivery latency**, not retry cadence — it is how long a screen
    reads `queued`. *(124, 125)*

44. **The password floor is 8 and is never retroactive**; it lives in `register_account`, so
    direct service callers are covered. **Three throttle kinds share `f01.login_attempt`** —
    `login`, `register`, `password_change` — with separate F13 keys so one cannot lock out
    another, and a test must breach the *real* ceiling to prove it. *(122)*

40a. **A new row TYPE inherits every existing query, including the ones written before
    it existed.** `ReceivableKind.fee` is money the driver owes the PLATFORM; every other
    kind is money a broker owes the driver. `money_owed` had no kind filter and the Money
    tab sums its non-settled rows into the "what you are owed" hero — so switching the fee
    on would have added our own fee to the figure telling a driver what brokers were
    sitting on. **When you add a value to an enum, grep every reader of that column before
    you ship the writer**, and carry direction in the KIND rather than a sign on the
    amount: a negative row would have made every existing sum silently wrong instead.
    *(129)*

40b. **A gate that is never satisfied makes the rung it guards a no-op, and the counter
    says so quietly.** Day-21 dunning was gated on `collection_partner_agreement`,
    unsatisfied since the migration that added it, so every claim reaching day 21 was
    counted `skipped_ungated` and the column was NULL on every row in the database — the
    product's last word on an unpaid invoice was silence. **A skip counter climbing is not
    the same as a feature working**; check whether the gated branch has EVER run before
    assuming the gate is the only thing standing in the way. *(129)*

40c. **Audit counterparty wording against RENDERED output, not source.** The escalation
    sweep asserted the banned words absent from all three dunning rungs by rendering them
    and reading the messages — which also caught a driver-facing string in six locales
    (`money.ev.escalation_offered` → "Collection offered") describing a step that had never
    once occurred. A source grep for the send path would have missed it entirely. *(129)*

## 6 · SQLAlchemy and Postgres

45. **Relationship collections are not trustworthy when the service writes with `db.add`.**
    `audit_settlement` writes discrepancies with `db.add`, not through
    `settlement.discrepancies`, so the collection can be stale on a re-used object — it
    produced `[15000, 15000, 30000]`, right twice and wrong on the third. **Delete by
    statement, then `db.expire`.** The same caution applies to `HeldClaim`. *(126, 127)*

46. **Deleting through a `delete-orphan` collection AND `db.delete` issues a second DELETE**
    for a row that has already gone. Detaching is what deletes. *(126)*

47. **`evaluate_ping` returns `PingResult`, not a list.** It is iterable over `.events` so
    old callers work. *(122)*

48. **`append_record` retries once on a seq collision** inside a savepoint;
    **`share_pack` refuses an invalid chain** and any new pack path inherits the gate.
    *(122)*

49. **`revoke_sessions` expires in place, never deletes.** Assert the invariant ("no session
    resolves"), not a row count. *(122)*

---

## 7 · Vue, the browser, and the driver app

50. **Vue's deep reactivity hands back PROXIES**, so `s !== shot` compares a proxy against
    its own target and is true for every element — a filter by identity silently removes
    nothing. **Use an id.** *(124, 125)*

51. **`@click="handler"` passes the MouseEvent as the first argument.** It made the first tap
    of "I've arrived" arrive as `confirmed = <MouseEvent>` and skip the too-far question.
    *(123)*

52. **A dynamic key family (`t(\`ns.${x}\`)`) cannot be checked statically.** An invented
    `cond.prompt.*` threw inside an `alt` and killed a whole render function — a sheet
    silently never opened. **Guard with `has()`.** *(123)*

53. **A Worker reply is structured-cloned**, so a passed-through blob is a different object
    with the same contents. **Assert on bytes, never on identity.** *(124, 125)*

54. **`crypto.subtle` is undefined in the browser harness** — the dev server is plain http,
    so it is not a secure context. Compare bytes, do not hash. *(124, 125)*

55. **A grid track needs `minmax(0, 1fr)`, not `1fr`**, for the same reason a flex item
    needs `min-width: 0`. Both forms of this defect have appeared in three surfaces;
    a fourth is expected. *(121)*

56. **`.app-content` declares `overflow-x: hidden` and must keep declaring it.**
    `overflow-y: auto` alone makes the other axis compute to `auto`, and the harness reads
    that as a deliberate scroller — which silently exempted **the entire app** from LAW 0's
    only mechanical check. Pinned by a unit test. *(121)*

57. **`.cta:not(.cta--text)` is NOT "the filled Primary".** Use
    `:not(.cta--text):not(.cta--outline)`. **More generally: name controls, do not index
    them** — `findAll(".cta--ghost").at(-1)` selected the wrong button the moment a second
    ghost button appeared on the surface. *(123, 126)*

58. **A new driver route must declare `meta.driving` AND back it** by consulting
    `isDriving`, and must be added to `driving-posture.test.js`'s `SOURCE` map. The guard
    has already caught a route that declared it and did not honour it. *(122)*

59. **The service worker no longer `skipWaiting`s on install.** A new build installs, WAITS,
    and the status strip offers the restart — so a driver photographing a BOL at a dock is
    never swapped mid-task. Anything assuming instant activation will not see it.
    `ui/src/sw.js` is a bundler ENTRY now, not a static file: it has `import`s, and
    `tray-answer.test.js` compiles those two lines away to keep unit-testing the handlers.
    *(123)*

60. **`--on-accent` is the only fill that works over a basemap in both themes.** A colour
    can be a legitimate token, correctly applied, and still be invisible where it is used —
    skeleton pins in `--line-1` were six pucks in the DOM, `visibility: visible`, counted by
    the harness, and invisible to a human. *(121)*

61. **Never put a skeleton on The Meter** (§9). Replace the card. *(121)*

62. **A new fetching surface must declare all four states** — it is on the §22.3 DoD.
    `core/load-state.js` has `LoadState`, `Failure` and `failureOf(err)`, and `failureOf`
    reads two signals because `apiGet` callers flip `online` and direct-`fetch` callers do
    not. *(121)*

63. **`ui/src/core/fixtures.js` is deliberately empty and says so.** Do not add to it; the
    five alternatives are listed in the file. `livePins ?? SAMPLE_PINS` showed fabricated
    truck stops on every cold open. *(121)*

---

## 8 · i18n

64. **New strings must survive the pseudo-locale's +40% inflation, and placeholders are the
    budget.** `"{done} of {all}"` is 11 characters of placeholder against roughly 7 of prose
    — no amount of rewriting saves it. The fix is shorter placeholder names, or a figure
    shape like `0/2`. *(122, 123)*

64a. **The placeholder budget is about 7 characters, and it bites more than once.** The
    pseudo-locale generator inflates only the VISIBLE text while the test measures the
    whole string, so the two disagree by 0.4 × placeholder length. Two placeholders of
    normal length already break it; three are unreachable. **A summary line with several
    slots is label-plus-figures in separate elements** — which is right anyway, since a
    figure is data and not part of a translated sentence. *(128, and 138 before it)*

64b. **THERE IS NO ICU PLURAL SUPPORT. `t()` does `replace(/\{(\w+)\}/g, …)` and nothing
    else** — design-prd §12.5 says "full ICU messages with placeholders", and the runtime
    implements the placeholder half only. A `{count, plural, one {…} other {…}}` string
    renders to the driver **literally, braces and all**, and no test in the suite says so:
    the catalogue contained no plural at all until M15, so nothing had ever exercised it.

    **The pseudo-locale test is what actually catches you, and it names the wrong thing.**
    `pseudoInflate` splits on `/(\{[^}]+\})/g`, so an ICU plural's first `}` ends the
    "placeholder" and almost the whole message is treated as untranslatable — the inflation
    lands far under +40% and the failure reads *"roadside.result.review_needed not
    inflated: expected 95 to be greater than or equal to 124"*. That is a message about
    padding, arriving for a reason that has nothing to do with padding.

    **Write the string so no runtime has to inflect it.** `"Waiting on a human check: {n}"`
    is correct at 1 and at 7, in six languages, and needs no plural rules — the same
    label-plus-figure shape 64a already arrives at from the other direction. Adding real
    ICU is a change to `i18n.js` with its own tests, not something to assume works. *(135)*

65. **A driver-facing string belongs in a `messages.py` beside its module**, registered with
    `f15.register_catalogue(db, prefix, mapping)` and read with
    `notify.localized_text(db, account_id, key, fallback, **values)` — not in a literal at
    the dispatch site. Seven modules use this. *(120)*

65a. **A throwaway check written to audit other checks is not exempt from being wrong.** A
    one-off script reported an i18n key missing from all six catalogues; it was a false
    positive from a regex matching the `t(` inside `emi`**`t(`**`"created")`. The standing
    test in `locale-completeness.test.js` requires a dotted key and never had the bug.
    **If a quick script disagrees with a long-standing test, suspect the script first** —
    and check whether the standing test already covers what you were about to write by
    hand. In that session it did, and more thoroughly. *(128)*

65b. **A reader that reconstructs state from EDGES is wrong wherever the state is a
    row.** `dwell_samples` replayed ENTER/EXIT events while `GeofencePresence` held the
    visit directly, so visits closed by `disarm_geofence` — which writes no EXIT event —
    vanished: 35 of 58 on production. The identical defect had already been found and
    fixed for M3's clock (`visit_window`, entry 73) and never carried across. **When you
    fix a reader, grep for the other readers of the same idea** — one fixed reader is not
    a fixed defect. *(129)*

66. **Six identical holes are perfect parity.** A JS-side parity test cannot see a key
    missing from all six locales; the check that catches it enumerates the vocabulary from
    Python. `resolve()` returns the RAW KEY when a string is missing everywhere, and 13
    were. *(120)*

---

## 9 · Local tooling

67. **`make ui-image` needs the DEV server** (it imports `src/core/*`); **`make ui-pwa` needs
    the BUILT app** — the dev build generates no service worker at all, deliberately, so a
    precache can never flake the layout sweep. *(123, 124, 125)*

68. **Adding a UI dependency needs `--renew-anon-volumes`.** `infra/docker-compose.yml`
    mounts `/app/node_modules` as an anonymous volume, so a rebuilt image is shadowed by the
    old one and the dev server dies with `ERR_MODULE_NOT_FOUND`. Cost twenty minutes and a
    full red layout sweep. *(123)*

69. **An ad-hoc Playwright probe must run `playwright install --with-deps chromium` first**,
    the way the Makefile targets do — and **EVERY invocation**, because `run --rm` gives a
    fresh container and the system libraries never persist. Without it the browser dies
    with `Target page, context or browser has been closed` and a wall of Chromium flags,
    and the real cause — `libglib-2.0.so.0` missing — is buried far below. Session 129 hit
    it by copying a working command without its install prefix on the RE-RUN, so a spec
    that had just passed failed instantly and looked like a regression in the page.
    **If a Playwright run fails instantly where the previous identical run passed, suspect
    the missing install line before touching anything else.** Cost five wasted runs across
    four sessions. *(126, 127, 129)*

69a. **`exec` into the long-lived `ui` container is not exempt, and it fails in a shape
    that argues against 69.** The browser BINARY survives — it lives in the `playwright`
    named volume, mounted precisely so `make down` cannot throw away 111 MB. The system
    LIBRARIES do not: they were `apt` packages inside the container filesystem, and
    `make up --build` replaced it. So the cache looks warm, the binary is present, and
    Chromium still dies on `libglib-2.0.so.0`. **A rebuilt container needs
    `npx playwright install-deps chromium` again even though nothing re-downloaded.**
    Hit on the first browser probe after a cold `make up`. *(135)*

70. **A probe hitting the real API from inside the container needs `page.route` to rewrite
    `localhost:8008` → `api:8008`**, must `route.abort()` on failure so one stalled
    background write cannot kill the page, and **must not use `waitUntil: "networkidle"`** —
    SSE keeps it busy forever. Use `domcontentloaded` plus an explicit wait. *(127)*

71. **`timeout` is not on macOS.** `timeout 300 docker compose …` fails with "command not
    found", and a wrapper's `echo` can make that look like success — it produced a false
    "migration re-applied" once. *(127)*

**`observe-loading.spec.js` runs inside `make ui-layout` deliberately** — an observation
nobody re-runs decays into a screenshot in an old handoff. Its screenshots are opt-in behind
`OBSERVE_SHOTS=1` so a sweep leaves the tree clean. *(121)*

**Do not run pytest while `make test` is running** — same database, phantom failures.

72. **The api container mounts `ui/src/core/i18n` read-only** at `/repo/ui-i18n` so a Python
    test can check dynamic key families against the vocabularies that produce them. It
    **fails rather than skips** when the mount is absent. *(120)*

---

73a. **UNCOMMITTED WORK IS NOT SAFE WHILE AN AGENT BELIEVES THE TREE IS FROZEN — it can
    and will be deleted.** A session told a verification agent "the tree is frozen at
    `0d11a8c`, stop if it moves", then kept WRITING new files into that tree while the
    agent ran. The agent did the reasonable thing: it tried to restore the state it had
    been promised, ran `git clean`, and destroyed **four modules and three test files**
    that had never been staged. Git could not help — unstaged, untracked work has no
    reflog. Its report described the files as being of "unknown source"; they were the
    session's own.

    The failure has two halves and both are worth naming. **A "frozen tree" instruction is
    a promise about your own behaviour, not just the agent's** — and it is broken by
    `Write`, not only by `docker`. The session had carefully avoided running containers
    during the verification and did not notice that authoring files was the same
    violation. **And a long-running verification is exactly when a session feels most free
    to write code**, because it is blocked on everything else.

    **Commit before you delegate anything that reads or cleans the tree, and keep
    committing while it runs — or do not write at all until it returns.** A `wip` commit
    with an honest message costs nothing and is recoverable; an untracked file is not.
    *(133)*

---

77. **`make ci` cannot be run twice in a row — the second run fails on ports the FIRST run
    bound.** `ci` opens with `preflight`, which requires every published host port free,
    and it ends with `ui-layout`/`ui-image`, which do `compose up -d ui` and leave it
    running; `test-api`'s `compose run` leaves its postgres and redis dependencies up too.
    So back-to-back runs produce `PREFLIGHT FAILED: UI_PORT=9008 BUSY` and a red result
    that says nothing about the code.

    This matters because the thing most likely to be run repeatedly is a **repeatability
    check**, and four identical failures in runs 2–5 look exactly like a finding.
    **`make down` between runs is part of the harness, not tidying up** — the comment above
    the `ci` target already says preflight runs "while everything is still down", and that
    is a precondition each run has to re-establish for itself. *(135)*

79. **A scripted string replacement that finds no anchor CHANGES NOTHING AND REPORTS
    SUCCESS** — and the second edit to the same region is where it happens. M15's session
    surface got `playInOrder` defined and never called, and `echoText` declared and never
    assigned, because an earlier replacement in the same handler had already rewritten the
    text the later one was matching on. The file compiled, lint passed, **2350 python tests
    and 1053 vitest passed**, the server frame carried the fields faithfully, and the
    driver heard silence between questions.

    **`assert OLD in t` before every replace, and re-read the file after.** Both are one
    line. The failure is otherwise invisible: nothing errors, nothing is red, and the only
    symptom is a person saying "it still does not do that".

    **The check that actually found it was grepping the DEPLOYED BUNDLE for the field
    names** — `grep -c echo_audio_url` on what the CDN serves. That is the only artifact a
    driver's browser ever sees, and the only one no local green can lie about. *(137)*

80. **A frame the surface does not read is a feature that does not exist, and no server
    test can see the difference.** M15's socket was tested to carry `echo`, `ack` and
    `opening`; every one of those tests passed while the UI ignored all three. **When a
    server field exists to be RENDERED, the test that matters mounts the surface, pushes
    the frame, and asserts the text appears.** Stub `WebSocket`, `Audio`, `MediaRecorder`
    and `navigator.mediaDevices` — the last one matters because a hands-free surface opens
    the mic itself and without it the test measures the mic-denied screen instead. *(137)*

81. **The obvious latency lever on an LLM turn is usually not the latency.** M15's
    improvising officer measured 2.0–6.8s per turn and the diagnosis picked itself: Claude
    Opus 5 thinks by default at `high` effort, and a two-sentence in-character line is not
    a reasoning task, so `effort=low` looked like free seconds. **Measured against the live
    API, five calls each: no effort 2.91s median, `effort=low` 3.07s — inside the noise.**
    ~2.8–3.0s is that model's round-trip floor for that prompt and no request-shaping
    recovers it. **Then the second measurement corrected the first.** TTS looked like the
    culprit at ~1.2s — measured from a laptop in Tashkent. On the box (us-central1, next
    door to Azure) the same call takes **0.25s**, and 0 when the text cache hits. So the
    turn is the MODEL almost entirely: 3.3–4.7s end to end on production, of which a
    quarter second is the voice. **Three rules fall out.** (1) Measure each leg — a
    per-turn number with two network calls inside it names neither. (2) **Measure from
    where the code runs.** A network-bound leg timed from your own machine tells you about
    your own machine; the same call from the box was 5× faster and inverted the diagnosis.
    (3) When the legs are serial and one is slow anyway, splitting the frame is still
    right — but bank it as correctness (a failing TTS no longer takes the turn down), not
    as the second it turned out not to buy. *(138)*

82. **A model swap is a content decision wearing a performance costume.** Haiku 4.5 answers
    the same officer prompt in 1.4s against Opus 5's 3.0s, which is the whole latency
    problem solved for free — except its line came back *"Good. I'll need to see your
    logbook to verify…"*. "Good." marks the driver's answer, which is Q-1; "to verify"
    edges toward stating what the law requires, which is the prompt's first prohibition.
    **The prohibitions in `officer_prompt.py` are the review a human would otherwise have
    done, and how reliably they hold is a property of the MODEL, not of the text.** A
    cheaper model is an owner decision with a driver-facing consequence, not a tuning
    knob — and if one is ever taken, the eval fixtures are what has to be re-run. *(138)*

83. **A pytest run you kill leaves a backend `idle in transaction`, and every later run
    then hangs with NO OUTPUT.** The next `pytest` blocks in `create_all`/`DROP TABLE`
    waiting on the lock the dead run still holds — before it prints a single line, so it
    looks like a wedged container or a broken import, not a database problem. It cost most
    of an afternoon and produced two confident wrong diagnoses on the way. **Symptom:
    `--collect-only` finishes in a second while a plain run produces an empty log.** Check
    for it before touching any code:

    ```
    docker compose -f infra/docker-compose.yml exec -T api python -c "
    from app.core.db import engine; from sqlalchemy import text
    with engine.connect() as c:
        print(c.execute(text(\"select pid, state, left(query,50), \"
          \"extract(epoch from now()-state_change)::int from pg_stat_activity \"
          \"where pid <> pg_backend_pid() and datname is not null order by 4 desc\")).fetchall())"
    ```

    Anything `idle in transaction` is the culprit; `pg_terminate_backend(pid)` on it frees
    every run queued behind. Killing the *containers* does not do this — the backend
    survives them. *(138)*

84. **`ui-components.test.js` → MapSurface "refetches (debounced) on bounds change" is
    load-flaky.** It failed once in a full `vitest run`, then passed in isolation (189/189)
    and passed again on a second full run. It asserts on a debounce timer, so it is
    sensitive to how loaded the machine is rather than to anything in the diff. **Do not
    "fix" it in response to a single red run** — reproduce it first, and if it needs
    fixing, the fix is fake timers rather than a longer wait. Recorded so a later session
    does not spend an hour attributing it to their own change. *(138)*

85. **`docker compose exec … python` DOES NOT WIRE OBJECT STORAGE, and anything you write
    from it goes to memory and dies with the process.** The servers call
    `wire_object_storage` at startup; a one-off exec imports the app and runs, so
    `default_storage()` is still `InMemoryObjectStorage`. The database row survives,
    pointing at a storage key that was never written.

    **It reports success the whole way.** Re-recording M15's content this way printed
    `{'synthesized': 25, 'failed': 0}`, gave every row an `audio_ref`, and left **all 31
    audio objects missing from MinIO** — every play button on production 404'd with
    `{"detail":"no image"}` and nothing was red anywhere. The owner found it by tapping one.

    Two rules. **Never run a document-writing job through a bare exec** — let the worker do
    it, or call `wiring.require_object_storage()` first, which scripts now do and which
    refuses to run rather than writing to nowhere. And **when audio 404s, check the object
    is in MinIO before checking anything else**:

    ```
    m.get(db.get(documents.Document, ref).storage_key)   # KeyError == written to memory
    ```

    A `KeyError` from storage is a dict lookup — that is the in-memory store, and the
    tell that a process wrote bytes nobody kept. Note also that a fresh exec always
    *reports* in-memory, so it cannot tell you what the running server is using; that
    measurement fooled this session for several minutes. *(138)*

78. **A browser walking the REAL app must run where BOTH locked ports are `localhost`** —
    which means the host, not a container. Cost four attempts and three dead ends, each of
    which looked like a different bug:

    · Served from `ui:9008`, every API call dies `net::ERR_FAILED`. That is **CORS**, not a
      network fault: `main.py` allows `http://localhost:9008` and `http://localhost:3008`,
      and the page's origin is neither. The surface renders its OFFLINE state, so the
      screenshot shows a working screen and says "No connection" — which reads as a bug in
      the app.
    · `page.route` rewriting `localhost:8008` → `api:8008` fixes XHR and **cannot touch a
      WebSocket**. If the socket is the thing you are proving, this fix hides the problem
      until the moment it matters.
    · `--host-resolver-rules=MAP localhost …` is **ignored**: Chromium special-cases
      loopback below the resolver.
    · Sharing the API's network namespace (`--network container:longhaul-api-1`) gets
      `localhost:8008` right and `localhost:9008` wrong, so it just moves the origin
      problem.

    **Install Playwright on the host and point it at `localhost:9008`.** The layout harness
    is exempt from all of this because it mocks the API rather than talking to it. *(136)*

## 10 · Live-fire, and things that reach the outside world

73. **Every environment is live-fire for email.** Dev and production both point at the same
    live Gmail account — an owner decision of 2026-08-15, recorded so no session reverses it
    as a drift. **Any action that could trigger a send is production-grade wherever it runs,
    and nothing is ever addressed to an inbox the owner does not control.** *(127)*

74. **A connector ships with an end-to-end proof against the real provider, observed, before
    its flag is eligible.** F8 recorded every detention notice as `sent` while every one of
    them went to a container on the VM, and the suite was green throughout because it
    asserted against the gateway it faked. *(127)*

75. **A provider's 200 response shape is unverified until a real key returns one.** A 401
    proves reachability and nothing more. *(127)*

76. **`m14_overlay` is OFF on production and that is the FINISHED state.** No `default_on`,
    NULL decision, both gates unsatisfied. Do not "finish" it by enabling it — that is an
    operator decision gated on D13. *(127)*

---

## Provenance

Distilled 2026-08-16 from the "things a later session will trip over" sections of
`HANDOFF-119` through `HANDOFF-127` (25 KB, 9 sections, ~60% duplication). The originals are
untouched — a handoff is a dated record. Numbers in *(italics)* name the handoff that first
recorded the trap, or all of them where it was carried forward.

86. **A lookup that matches content by its TEXT dies the day something starts improvising,
    and it dies silently.** M15's coaching screen found the "replay the question you
    missed" audio by matching the officer's transcript against the released
    `PhraseVariant` rows. Correct while every line he spoke came out of that table.
    The moment he composed his own (entry 194), the match never succeeded again,
    `missed_question_audio` became structurally `None`, and the button stopped rendering
    on every stop. **No error, no log, no red test** — `v-if` on a null is not a failure,
    it is a button that was never there.

    Grep for `.text ==`, `.transcript ==` and `next((x for x in pool if ...))` whenever
    something upstream gains a generative path. The fix here was that the audio had been
    sitting on the officer's own `Turn.audio_ref` the whole time — **the record of what
    actually happened beats re-deriving it from the content library.**

87. **"The play button doesn't work" is usually the app never admitting it was touched.**
    `new Audio(src).play().catch(() => {})` is the pattern, and it has three faults at
    once: the element is referenced by nothing, so a phone may collect it mid-clip; a
    second tap talks over the first; and every rejection is swallowed, so a real bug
    report arrives with **no evidence attached at all**.

    Do not start by suspecting the URL. Drive the real screen with Playwright and
    instrument `window.Audio` — record `created` / `playing` / `error` / resolved /
    rejected per src. Here all seven buttons played correctly (HTTP 206, `playing`,
    resolved) on desktop *and* a Pixel 5 profile, which is what redirected the search to
    the buttons that were missing instead. A muted phone, a dead bluetooth route, an
    expired signature and a broken URL are indistinguishable to a driver **and to you**
    unless the tap changes something on screen. Give playback a `data-playing` state and
    one-at-a-time semantics; the transcript surface already had it, the coach surface did
    not, and only the second one got reported.
