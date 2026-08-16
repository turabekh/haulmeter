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

17. **A sabotage that comes back green is not a safe fix; it is a check that does not
    exist.** And **verify the sabotage applied** — a shell variable once made six reverts
    silently not happen. *(121, 122)*

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
