# HANDOFF-123 — the constitution said so, and nothing had built it

> **Stack DOWN · everything PUSHED · DEPLOYED · `haulmeter.online` CURRENT at `0070`.**
> Nine commits, §23 entries **135–143**, four migrations applied on the box (`0067`→`0070`),
> backup taken first and verified offsite.
>
> One session, driven entirely by the owner looking at real screens on a real phone and
> saying what was confusing. Every finding below started as "this is hard to use" and
> ended somewhere further down than that.
>
> ---
>
> **THE ONE THING TO CARRY FORWARD.** HANDOFF-122's pattern was *a mechanism built,
> correct, exported — and reached by nothing.* **This session's is its twin and it is
> worse: a thing the governing documents SPECIFY, that shipped as done, and that had
> never existed at all.**
>
> | Specified | Where | Reality until this session |
> |---|---|---|
> | "Loading state = inline spinner replacing label" | §8 | never built anywhere; `button:disabled` styled nowhere |
> | "bottom-anchored primary action (56 dp + 16 gutter)" | §7.2 | never built; the only `position: fixed` in the codebase was `BottomSheet` |
> | "Primary action: per-receivable Next action" | §10.3 | Money rows had no tap target at all |
> | an installable PWA (and iOS push depends on it) | index.html's own comment | `"icons": []`, and **not one image asset in the entire UI** |
>
> **Three times the document describing the requirement sat directly above the code that
> made it impossible.** index.html says *"iOS requires an INSTALLED PWA for push at all"*
> four lines above the manifest that could never install. §10.3's "next action" was in the
> spec above rows that did nothing. That is the shape to hunt: **a comment or a spec line
> that asserts a capability, with nothing under it.**
>
> **And the twin, in the tests again — a SELECTOR standing in for an IDEA stops standing
> for it the moment the page grows.** `.cta:not(.cta--text)` was read across the suite as
> "the filled Primary"; it never was, and the day a Secondary existed it counted one as a
> rival. `load-dock-actions` asserted "no `.cta` at all" as a proxy for "no on-site
> shortcut" — that proxy would have hidden the leave control from a driver who stepped
> outside the geofence. **And the mocks: every packet harness state mocked a LIVE load,
> every live Load state mocked `phase: "accruing"`.** So the two states a driver is in
> most often — paperwork waiting with no load, and standing at a dock before arrival —
> had never been rendered by anything.

---

## 1. Current state

| | |
|---|---|
| Branch | `main`, **0 ahead / 0 behind `origin/main`** at `7db728c` (OBSERVED — `git fetch` works) |
| Gates | **pytest 1842 · vitest 885 (49 files) · layout 325 · `make ui-pwa` · import-linter 30/30 · ruff clean** |
| Migrations | local **and production** at **`0070_m05_packet_discarded`**. Nothing pending |
| Working tree | clean |
| Stack | **DOWN** (owner asked for it at session end) |
| Deploy | **DONE and verified.** Backup `haulmeter-20260811T164115Z.dump` (9.9 MB) taken first and uploaded to `gs://haulmeter-backups` |
| Email | **dev still points at live Gmail. A send from dev is a real send.** |

**Baseline at session start: pytest 1813 / vitest 796 / layout 289.**
Net: **+29 pytest, +89 vitest, +36 layout, +1 make target.**

### `make ci` gained a step

`make ui-pwa` builds the app, serves it, and drives a real browser **offline**. It is in
`make ci` now. It is the only check that can catch a PWA defect — every other assertion
about a manifest reads the manifest, which is precisely how `"icons": []` shipped.

---

## 2. What each entry closed

**135 — the Load tab said two things at once.** Paperwork waiting + no load rendered two
identical filled Primaries with nothing to rank them (§8 allows one), over a resting Meter
reading "No load —" directly beneath "You left Harvest Foods DC". The em-dash sits where
this product puts money, so the screen a driver opens straight after a drop could read as
their detention having vanished. Sequenced, not stacked.

**136 — §8's button loading state, built for the first time.** ~35 buttons; a seven-word
`busy.*` vocabulary in six locales. **Nine handlers had no in-flight guard at all** —
`onSendNotice` genuinely sent a broker two emails on a double tap. `HandoffSheet`'s guard
read a flag written *after* the await. Plus the stop packet gained a **discard** with a
confirm inside the existing sheet (§8 wants a confirm sheet; §8 caps sheets at 1 deep).

**137 — a past load can be read before it is downloaded, and sent at all.** New
`GET /load/{id}/record` and a `/load/:loadId/record` screen. **`/protection/{kind}/{ref}/share`
has accepted `kind="load"` since the whole-route pack was written and the only caller
passed `"stop"`** — the eighth built-and-inert mechanism, and the first found by asking
what a feature would need rather than by auditing.

**138 — the arrival record was a fiction.** `arrive` called `evaluate_ping` with **the
facility's own coordinates**; the client had a real fix and posted an empty body. So the
position fix a detention claim rests on, on the path taken *because the sensor did not
fire*, was a reading of where the warehouse is. New F3 seam `assert_presence` opens the
visit and emits a GeofenceEvent **only where there is a real position**. Too-far is a
question at 1000 m, never a gate.

**139 — the collapse went both ways.** `evidenceOpen` was one-way.

**140 — §7.2's bottom-anchored action zone, built for the first time.** Measured: the
Primary rendered at **y = 1055 in an 800 dp viewport**.

**141 — leaving the stop is a control, not a sheet item.** **Entry 140's own justification
was wrong**: it claimed the anchored row was "where Leave this stop lives". It was the
fourth item inside the More sheet. Corrected to a §8 Secondary with a confirm.

**142 — the Money tab, rebuilt.** The hero was `recovered + fuel_saved + flagged` labelled
**"Delivered to you"** — a *lifetime* total including money an audit merely suspects is
owed, telling a driver they had received **$1,432.50 when they had received $987**.
"Money owed" listed money that was not owed. Rows had no tap target.

**143 — the PWA.** `"icons": []`, no image asset anywhere, so **the app has never been
installable and Web Push on iOS has never been reachable**. The worker was registered only
inside `push.js`'s `enable()`.

---

## 3. Exact next task

**The owner's one action, unchanged since HANDOFF-121 §11.1 and NOT fixed by this deploy:**

**`SMTP_HOST` on the VM (F-01).** Production still points at the Mailpit container, so every
counterparty email lands on the box. One `.env` edit; rule 9 makes it yours. The worker's
own log names the scale of it — the post-deploy run reported
`dunning … skipped_no_email: 11` out of 14 scanned.

**Then the first live send should be a rehearsal to an inbox you control.** Create a load
with your own address as the broker email, run a stop past free time, tap Send, confirm
what arrives. Two independent blockers lift at once and it is the only test covering both.

**The oldest unmet item is still v2.0 DoD #8 — the handset background-sensor test.** Named
as next since session 115, deferred eight times. It needs a human, a handset and a drive.
**It is now also the only way to validate entry 138**: the arrival record's device fix,
accuracy and distance have never been produced by a real phone.

### Owner decisions still open

| | |
|---|---|
| **`--marker-500` at 2.04:1 in dark** | A §22.2 palette colour, open since 119 |
| **Email verification at signup** | Owner-LOCKED. Gates three things (see 122 §4) |
| **External anchoring** | Two options costed in the evidence report |
| **A second alert channel** | A12 has exactly one |
| **The f03 knobs** | `exit_confirm_pings` / `accuracy_gate_m`, declared and OFF. **Entry 138 changes what is possible here:** real device fixes and accuracies now enter the chain, so after the handset test there will finally be data to set a threshold from |
| **A far-future appointment overflows the Meter** | A six-digit hour blows past 360 dp at 200% text. Real appointments do not; a mis-parsed rate con could. Capping the figure changes §9 |
| **§7.2's anchored action on the other surfaces** | Built on Load only (owner's scope choice). Evidence, Booking, Fuel, Load record, Condition and Auth have the same unbuilt anatomy |

---

## 4. Things a later session will trip over

1. **`make ui-pwa` needs the BUILT app**, not the dev server — the dev build generates no
   service worker at all, deliberately, so a precache can never flake the 325-check sweep.
2. **Adding a UI dependency needs `--renew-anon-volumes`.** `infra/docker-compose.yml`
   mounts `/app/node_modules` as an anonymous volume, so a rebuilt image is shadowed by the
   old one and the dev server dies with `ERR_MODULE_NOT_FOUND`. Cost twenty minutes and a
   full red layout sweep this session.
   `docker compose up -d --force-recreate --renew-anon-volumes ui`.
3. **`ui/src/sw.js` is a bundler ENTRY now**, not a static file. It moved out of `public/`
   and has `import`s. `tray-answer.test.js` compiles those two lines away to keep unit-testing
   the push handlers.
4. **The service worker no longer `skipWaiting`s on install.** A new build waits; the status
   strip offers the restart. Anything that assumed instant activation will not see it.
5. **`.cta:not(.cta--text)` is NOT "the filled Primary".** Use
   `:not(.cta--text):not(.cta--outline)`. Two suites read it the old way.
6. **`money_owed` returns EVERY receivable**, settled included, newest-first. The Money tab
   splits and re-sorts; anything else reading it must too.
7. **New i18n strings must survive the pseudo-locale, and placeholders are the budget.**
   `"{done} of {all}"` is 11 characters of placeholder against roughly 7 — no amount of
   prose saves it. The fix is shorter placeholder names, or §10.2's "0/2" figure shape.
8. **A dynamic key family (`t(\`ns.${x}\`)`) cannot be checked statically.** An invented
   `cond.prompt.*` threw inside an `alt` and killed a whole render function — the send
   sheet silently never opened. Guard with `has()`.
9. **`@click="handler"` passes the MouseEvent as the first argument.** It made the first tap
   of "I've arrived" arrive as `confirmed = <MouseEvent>` and skip the too-far question.
10. **The API wedges mid-reload if SSE streams are open.** `/health` hangs;
    `docker compose restart api` clears it. (Carried from 122 §5.10.)

---

## 5. Known gaps this session left

- **The update strip has no layout state.** It is driven by module state a real service
  worker sets, which the dev-server harness cannot reach. Covered at DOM level; it shares
  its geometry with the three strip items that ARE measured.
- **The icon is honest placeholder art**, drawn from §6.1 token literals. It satisfies
  installability and reads at 48 dp. It is not a commissioned mark.
- **`make ui-pwa` proves the shell caches and the app opens offline.** It does not prove the
  install PROMPT appears on a real Android handset, or that iOS push now works — both need
  a device.
- **`SESSION-REPORT*.md` still live at the repo root** (six of them, from 122).

---

## 6. Restarting

```
make up                              # preflight, then the full stack
make seed-where                      # the Tampa origin — paste into Sensors
make test                            # 1842 pytest + 885 vitest — do NOT pipe it
make lint                            # ruff + import-linter (30 contracts)
make ui-layout                       # 325 checks, ~3.3 min, runs ALONE
make ui-pwa                          # builds, previews, drives a browser offline
make down
```

`make ui-layout-only STATE=<name>` measures one state in ~45 s — use it while building.

**Do not run pytest while `make test` is running** — same database, phantom failures. And
do not start a background full-suite run and then edit.

`infra/.env` carries the live Gmail block and is gitignored. **A send from dev is a real send.**

---

Each session ends by writing the next `HANDOFF-<n>.md` here and updating `HANDOFF.md` to
point at it. Full history is in `docs/handoffs/`; the Session-0 bootstrap is `HANDOFF-000.md`.
