# HANDOFF-102 — the session where the events turned out to be missing, not the notifications

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 29 July 2026 · **Stack:** UP locally (`make down` to stop) · **Deployed:**
https://haulmeter.online (GCE, `uzimiz-prod`) — **current**, migration at head, zero
errors, `detention_clock` alerting nobody from the backlog.

**State in one line:** all three of §13.2's P0 examples now exist — and two of the three
turned out to need the EVENT built first, which is the thing this handoff is for.

> **This continues HANDOFF-101, which is the same session.** 101 has the detention P0,
> the freshness window and the anchor rule; several of its corrections are load-bearing
> here, because the same class of defect recurred twice more.

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0054_m03_driver_clock_alerts** (unchanged since 101) |
| Tests | **pytest 1164 · vitest 559 · layout 177 · ruff + import-linter 30/30** |
| §23 decision log | **110 entries** (106–110 this session) |
| Handoffs | 000 → 102 |
| Git | pushed; in sync with `origin/main` (public) |
| Deployed | **current with this handoff's work**, verified on the box |
| Working tree | clean except untracked `collect_files.py` (not mine) |

## 2. What shipped after 101

| Commit | What |
|---|---|
| `0f48db2` | The other two P0s, built against the events that exist (§23 108) |
| `ba08887` | The two controls that make those events reachable (§23 109) |
| `cbe4eb3` | A driver can finally see their own bookings (§23 110) |
| `eb7453d` | CLAUDE.md rule 3 now describes how this project actually works |

## 3. The correction this handoff exists to make

**HANDOFF-101 §7.2 said "booking failed" and "claim paid" needed no owner decision
because both instants were unambiguous. That was wrong, twice, in the same way: neither
EVENT existed.** Detention was the easy one — a real computable boundary sitting unused.
These two had nothing to hook.

- **Nothing could ever pay a claim.** `ReceivableState.recovered` and F7's
  `record_recovery` have existed since the ledger shipped with **zero non-test
  callers**. So M9's own `recovered_cents` was $0 by construction and M12's fleet
  rollup counted a state nothing could reach. The notification was not missing a
  dispatch site; the money was missing an ending.
- **"Booking failed" names a failure that does not exist.** `book()` has exactly one —
  `SpotUnavailable` on a double-book — raised inside the driver's own request and
  answered by §12.4 error copy on the screen they are already reading. **A P0 there
  would push someone what they are looking at.**

**Both owner decisions are in §23 entry 106's successor, entry 108:** the DRIVER marks a
claim paid (the money lands in their bank; nobody else can know), and "booking failed"
was replaced by the real money event — M6-FR7's cancellation, whose whole refund engine
had been written, tested and **left with no endpoint calling it**.

## 4. The rule worth carrying forward

**A P0 announces money that moved WITHOUT you.**

A notification exists to tell someone something they do not already know. The driver who
taps "the broker paid this" is told nothing; the driver who cancels their own booking is
told nothing. The fleet manager, the M3-FR7 collection partner, and the property owner
taking someone's spot are exactly what the tier is for. Both silence tests were proved
RED by deleting the actor check.

**Consequence, stated plainly: "claim paid" is correct and DORMANT.** The only endpoint
that can mark a receivable paid is driver-only, so nothing reaches the notifying branch
today. It is built so the P0 is right the moment a second actor exists — but it will not
fire until M12 or the partner seam can record a recovery.

## 5. Three judgement calls, so they can be overruled

- **A constitutional guard was narrowed rather than dodged.** `test_settability` forbids
  any mutating route naming a `receivable`. The easy way past was renaming the route —
  which hides the mutation from the one check built to find it. The principle is about
  POSTINGS; a receivable's STATE is what F7 ships an `ALLOWED_TRANSITIONS` table for.
  Carve-out: **one exact path**, plus a test that fails if the exception outlives the
  route, and one asserting the route takes no request body so an AMOUNT still cannot be
  edited by anything.
- **No ledger entry is posted on a driver's own recovery.** A broker paying the driver's
  own invoice moves no cash across this platform; posting an entry saying it did would
  invent a movement we never handled. `record_recovery` remains right for the collection
  partner, where the money does pass through us.
- **Both irreversible actions arm before they act.** Pausing a spot is one tap because
  it is reversible; cancelling refunds money, pushes a P0, and has no un-refund in F7.
  That is a behaviour on an existing button, not an invented component — the line §22
  actually draws.

## 6. `/bookings`, and who decided it

**A §22.2 never-improvise decision, made on the owner's explicit delegation** ("use your
best judgement and proceed") and logged as §23 entry 110 anyway, because delegation
changes who decides, not whether it is written down.

A driver could not see a booking they had paid for: `owner_bookings` shipped with M6 and
the driver-side read never did. **Decision: `/bookings`, a records screen reached from
More.** NAV-1 fixes five tabs; Map is the live map, not a list; Money is the driver's P&L
and a parking reservation is not a receivable. The cancellation P0 now deep-links there
instead of at `/book/<spot>`, the checkout flow.

## 7. Method notes

- **The layout harness earned its keep the moment the new screen was registered in it.**
  Both controls were built at 44 dp — the WCAG number — and **§6.5's glove spec is 48**.
  A back button and a cancel button, on a screen for someone in winter gloves at a truck
  stop. They take `--touch-min` now, so the next screen cannot inherit the mistake by
  copying this one. **169 → 177 states** across this session.
- **A green harness run that does not know about your screen says nothing about it.**
  The first run after building the mark-paid sheet passed 169 and covered none of it.
  Registering a new surface is part of building it, not a follow-up.
- **Every guard was proved RED first**, including both silence rules and the
  freshness/anchor rules from 101.
- **One test was superseded rather than deleted quietly**: the cancellation P0's
  deep-link assertion named `/book/<spot>` and now asserts the weaker, durable property
  (not a tab root), because entry 110 changed where it points.
- **Verified live on the real stack** after each piece, then rolled back; and verified
  on the DEPLOYED box after shipping.

## 8. Exact next task

**1. Web Push (VAPID).** Unchanged from 101 §7.3 and still not blocked on credentials.
Everything dispatched today reaches the inbox and nothing else. **What these two
sessions changed is that there is now something real to push** — three P0 classes, two
of them live. Needs: a VAPID keypair in `infra/.env` (rule 9 — `.env.example` documents
the names only), a service worker + web manifest (the app becomes a PWA), a
`push_subscription` table, a `WebPushNotificationGateway` implementing the existing
`gateway.py` Protocol, and a permission-request flow whose TIMING is a §22 design
question — asking on first launch is the dark pattern §21.8 forbids in spirit.

**2. Give "claim paid" a second actor**, or accept it stays dormant. M12 fleet is the
nearest: a fleet manager recording that a broker paid one of their drivers is the exact
case the P0 was built for, and M12 already reads recovered receivables for its rollup.

**3. Coverage.** 9 states (WI IN IA MN KS KY MI OH TX). Unchanged.

## 9. Debt

**New this session (102):**
- **"Claim paid" is dormant** — see §4. Correct, tested, and unreachable until a second
  actor exists.
- **`recovered` is terminal with no operator path back.** A driver who marks the wrong
  claim paid cannot undo it, and no admin surface can either. That was acceptable while
  nothing could reach the state at all; it is a real edge now that a mis-tap can.
- **A booking cannot be checked in or out from anywhere.** `check_in` and `check_out`
  are written in M6's domain and, like `cancel` before this session, have no endpoint —
  so `checked_in`/`checked_out` are states the product can display but never produce.
- **The M6 take rate is not shown on the driver's bookings list.** Correct per §21.8
  (one transparent price, no checkout surprises), noted so nobody "fixes" it.

**Carried from 101 and still open:** `trigger_time = arrival or now` is still the money
core's behaviour, so `/detention/{id}/clock` answers "accruing · $0.00" for a claim F3
cannot place · the 30-minute `ALERT_FRESHNESS` window is a judgement, not an owner
decision · `dispatch_clock_alerts` costs one `clock()` per open claim · M5's expiry
reminders deep-link to `/docs`, a tab root, which §13.5 forbids · notification copy is
English-only, server-side.

**Carried and still open:** `/events/stream` is not flag-gated · the SSE session travels
in the query string · the SSE generator is synchronous · `_enrich` is per-pin · beliefs
written against merged ids before §23 95 · the flaky `login · pa` layout state ·
`/admin/facilities/*` does not resolve merged ids · M2-FR4 does not exist · per-stop
detention terms not expressible in the UI · the profit calculator opens on invented
defaults · dwell-risk thresholds unvalidated · `pin.shape` read by nothing · all live
API keys on an internet-facing VM · **no backups** · **no monitoring**.

## 10. Restarting

```
make up                              # local stack
make test                            # pytest + vitest
make ui-layout                       # 177, ~2.3 min — run it alone
make lint                            # ruff + import-linter
./scripts/deploy.sh                  # ship to haulmeter.online
docker compose -f infra/docker-compose.yml logs worker | grep detention_clock
```

**The standing warning, in the form this session found it.** 1,111 green tests did not
know that nothing had ever sent a P0. Then 1,137 did not know that eleven of them were
about to be sent three days late, or that five more were about to announce detention at
a dock nobody arrived at. Then a green 169-state harness said nothing at all about the
screen that had just been built, because it had not been told the screen existed. **Each
time, the code did exactly what it was written to do. The question a suite cannot ask is
whether anyone wrote the thing at all** — so read the real data, drive the real screen,
and when you add a surface, add it to the harness in the same commit.
