# HANDOFF-103 — push is live, and the prompt it must not waste

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 29 July 2026 · **Stack:** UP locally (`make down` to stop) · **Deployed:**
https://haulmeter.online (GCE, `uzimiz-prod`) — **current, and Web Push is ENABLED**:
`/api/notifications/push/key` answers `enabled: true`, the gateway resolves to
`WebPushNotificationGateway`, `sw.js` and the manifest are served.

**State in one line:** §13's unprompted half exists — a P0 can now reach a phone in a
pocket — and the single most consequential thing in it is a browser prompt that can only
be spent once.

> **This continues HANDOFF-102, which is the same session.** 102 has the "the events
> were missing, not the notifications" correction and the rule that governs all three
> P0s; read it before touching any dispatch site.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0055_f08_push_subscription** |
| Tests | **pytest 1173 · vitest 567 · layout 177 · ruff + import-linter 30/30** |
| §23 decision log | **111 entries** (106–111 this session) |
| Handoffs | 000 → 103 |
| Git | pushed; in sync with `origin/main` (public) |
| Deployed | **current**, VAPID configured **on the box only** |
| Working tree | clean except untracked `collect_files.py` (not mine) |

## 2. What shipped after 102

| Commit | What |
|---|---|
| `0ec1b41` | Web Push — a P0 that reaches a phone in a pocket (§23 111) |

## 3. Push was never blocked on a vendor

Earlier handoffs recorded push as waiting on an FCM or Apple account. **It was not.**
RFC 8292 (VAPID) identifies this application server by a P-256 keypair **we generate
ourselves** — there is no registration step and nobody to ask. Chrome/Edge/Firefox on
Android, which is LAW 0's exact target device, support it natively. iOS needs 16.4+ and
an *installed* PWA, which is why the web manifest ships with this.

```
make vapid-keys      # prints a pair; it never writes, because the private key is a secret
```

**On the deployed box the pair was generated ON the VM** (`scripts/vapid_keys.py` inside
the api container) and appended to `/opt/haulmeter/infra/.env`, `0600`. **The private key
has never been on a laptop, in the repo, or in a shell transcript** — which is the
posture `docs/deploy-testing-env.md` already sets for every other secret there.
`scripts/deploy.sh` never ships `infra/.env`, so a deploy cannot overwrite it.

**Rotating the pair invalidates every stored subscription** — browsers subscribe against
a specific application server key — so every driver must re-enable. Rotate only on a
compromise, and expect `f08.push_subscription` to drain.

## 4. The timing decision, which is the whole design

**The browser's permission prompt is ONE-SHOT.** A "no" is permanent for the origin and
there is no second ask. That single fact turns permission timing from a UX preference
into a correctness rule, and asking on first launch — the canonical dark pattern §21.8
forbids — would spend a driver's only chance before they have any idea what we send.

- **Nothing is ever requested automatically.** `enable()` runs only from an explicit tap.
- **Enrolment lives in the notifications sheet** — the one place a driver has already
  come to ask about notifications.
- **The control says what will be sent BEFORE the prompt appears**, because the prompt
  cannot say it.
- **The prompt is not reached at all when the server has no keypair.** A test holds that
  ordering and fails if the two lines are swapped.
- **Turning alerts off is one tap** and really unsubscribes rather than muting.

## 5. Rules to know before touching this

- **A secure context is required, and it is §23 entry 91's trap exactly.**
  `PushManager` and `Notification` EXIST over plain `http` and then refuse to work — the
  same shape as the microphone that shipped broken for six sessions.
  `window.isSecureContext` is the browser's own answer; a phone on a LAN IP is told a
  deployment fact rather than failing opaquely.
- **One row per BROWSER, keyed on endpoint.** A phone and a cab tablet are two and both
  should buzz. Keyed on account, a re-subscribe would clobber the second device or
  accumulate rows that all buzz the first — nagging arriving through the transport
  rather than the tiering §13.1 guards. **An endpoint that reappears under a different
  account is REASSIGNED**: one browser has one owner, and two accounts pushing to one
  device would send a driver someone else's money alerts.
- **A gateway may never make a dispatch fail.** F8 has already applied the tier, the
  budget and quiet hours by the time `send_push` runs. Verified with a real keypair
  against an unreachable endpoint: the row is still `sent`, channel `push`, and **the
  subscription survives** — a DNS failure is not a driver who left. **Only 404/410
  prunes**, the one honest signal a dead subscription ever gives.
- **`deep_link` travels WITH the push.** The Protocol carried title and body only, so
  `sw.js` would have had to invent a destination — a tab root, the one thing §13.5 names
  outright. It is optional in the signature so every existing double keeps working, and
  mandatory in practice because `dispatch` refuses to create a notification without one.
- **`sw.js` decides nothing.** Everything it shows was already decided server-side. It
  renders and routes. It is deliberately tiny and has no build step, because a service
  worker is cached on its own schedule and anything clever in it can be stale on a
  driver's phone for days.

## 6. Method notes

- **Proved end to end, not asserted.** Against a local endpoint standing in for a push
  service, the request carries `Content-Encoding: aes128gcm`, a `vapid t=…` Authorization
  JWT, a TTL, and **193 bytes of ciphertext in which the plaintext does not appear**
  (RFC 8291). The push service relays something it cannot read.
- **Three guards proved RED**: endpoint keying (drop it and re-subscribe duplicates),
  the prompt ordering (swap two lines and an unconfigured server spends the one-shot
  prompt), and the secure-context check.
- **A second expiring test was found and fixed while running this.**
  `test_overdue_moderation_finds_late_items` seeded at a fixed `T0` and compared against
  `datetime.now()`; with `MODERATION_SLA_HOURS = 72` it was true until **29 July 13:00
  UTC** and false after, and it turned red mid-session exactly as its sibling did in
  HANDOFF-100 §7. **Same pattern, same fix: anchor to the clock the assertion reads.**
  That is now twice in four days — if a third appears, make it a lint rather than a fix.
- **The new control was measured, not assumed.** `sheet-notifications` was already a
  layout-harness state, so the enrolment section was covered at 360×800, +40%
  pseudo-locale, Punjabi and 200% in the same run — unlike §23 entries 109 and 110,
  where a new surface had to be registered before the harness could say anything.

## 7. Exact next task

**1. Confirm a real push on a real handset.** Everything above is verified by
construction and against a stand-in endpoint; **nothing has yet been delivered to an
actual phone.** Open https://haulmeter.online on an Android Chrome device, sign in, More
→ notifications → "Turn on alerts", then make a claim cross its free-time boundary (or
run `run_detention_clock` against a seeded claim) and confirm the tray entry appears and
that tapping it lands on `/claim/<stop>`. **This is the one claim in §5 that a laptop
cannot check.**

**2. Give "claim paid" a second actor**, or accept it stays dormant (102 §4). M12 fleet
is the nearest: a fleet manager recording that a broker paid one of their drivers is the
exact case the P0 was built for.

**3. Coverage.** 9 states (WI IN IA MN KS KY MI OH TX). Unchanged.

## 8. Debt

**New this session (103):**
- **No push has ever reached a real handset** (see §7.1). The crypto, the headers and
  the fallbacks are verified; the last mile is not.
- **The manifest ships with `"icons": []`.** Android will use a generic glyph on the
  home screen and in the notification tray. Icons are a §22 design question — a brand
  asset, not something to improvise — and are the visible half of "installable".
- **No `push` telemetry.** `delivered` and `pruned` are counted on the gateway instance
  and thrown away; nothing records how many pushes a dispatch actually reached. The
  worker's job summary is the natural place.
- **iOS is untested and needs an installed PWA** (16.4+). The manifest is there; nobody
  has run the install flow.

**Carried from 102 and still open:** "claim paid" is dormant · `recovered` is terminal
with no operator path back · `check_in`/`check_out` have no endpoint.

**Carried from 101 and still open:** `trigger_time = arrival or now` · the 30-minute
`ALERT_FRESHNESS` window is a judgement · `dispatch_clock_alerts` costs one `clock()`
per open claim · M5's expiry reminders deep-link to `/docs`, a tab root · notification
copy is English-only, server-side.

**Carried and still open:** `/events/stream` is not flag-gated · the SSE session travels
in the query string · the SSE generator is synchronous · `_enrich` is per-pin · beliefs
written against merged ids before §23 95 · the flaky `login · pa` layout state ·
`/admin/facilities/*` does not resolve merged ids · M2-FR4 does not exist · per-stop
detention terms not expressible in the UI · the profit calculator opens on invented
defaults · dwell-risk thresholds unvalidated · `pin.shape` read by nothing · all live
API keys on an internet-facing VM · **no backups** · **no monitoring**.

## 9. Restarting

```
make up                              # local stack
make test                            # pytest + vitest
make ui-layout                       # 177, ~2.3 min — run it alone
make lint                            # ruff + import-linter
make vapid-keys                      # prints a pair; paste into infra/.env by hand
./scripts/deploy.sh                  # ship to haulmeter.online
curl -s https://haulmeter.online/api/notifications/push/key   # enabled?
```

**The standing warning, in the form this session found it.** Every defect this session
was invisible to a green suite, and each was a different kind of absence: nothing had
ever sent a P0; two of the three P0s named an event that did not exist; a harness passed
177 states while knowing nothing about the screen just built; and a test that read as
timeless quietly expired at 13:00 today. **A suite proves the code does what it was
written to do. It cannot tell you nobody wrote the thing, and it cannot tell you the
clock moved.** Read the real data, drive the real screen, register new surfaces in the
harness in the same commit — and now, since §7.1, put it on an actual phone.
