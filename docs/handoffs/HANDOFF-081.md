# HANDOFF-081 — "follow this cook", and a declared law made real

**Project:** Haulmeter — Consolidated Trucker Platform (mobile-first, driver pays $0).
**Date:** 26 July 2026 · **Stack:** UP (api :8008 · ui :9008 · worker · postgres :5438 · redis · minio · mailpit).

**State in one line:** a driver could only ever be told about food they had **already found** — the one
vendor notification went to people who had confirmed a cook in person. They can now ask to hear about
one, and the geography that makes such a message worth sending is enforced rather than assumed.

Read alongside **HANDOFF-080** (distance + navigate) and **078** (consolidated platform picture).

---

## 1. Current state

| Thing | Value |
|---|---|
| Migrations | head **0046_f08_followed_subjects** |
| Tests | **pytest 885 · vitest 339 · ruff clean · import-linter 30/30** |
| §23 decision log | 37 entries |
| Handoffs | 000 → 081 |
| Git | **20 commits local on `main`, no remote configured** |

## 2. The problem, stated precisely

The `vendor_alert` class has always declared **`route_relevant_only=True`** and **nothing enforced it**.
`dispatch` checks opt-in, mute, the class cap, quiet hours, RESTING and the global budget — never
relevance. The code said why, in `notify_promotion`:

> *"The class declares `route_relevant_only`, but no live route context exists yet (M8 has no
> per-driver route feed), so a demonstrated prior connection is the honest stand-in rather than a
> claim of route targeting we cannot make."*

So *drivers who previously confirmed this vendor* was doing **two jobs at once** — standing in for
**consent** and for **geography**. That is exactly why the loop was closed: the only people reachable
were the ones who had already found the cook themselves.

## 3. What was built

| | |
|---|---|
| **F8** | `followed_subjects` on `NotificationClassPref` (migration 0046) — the mirror of `muted_subjects`, plus `follow_subject` / `unfollow_subject` / `is_following` / `followers_of`. |
| **F3** | `last_known_position(db, account_id, not_older_than)` — driver position belongs to F3, so M13 grew no location query of its own. |
| **M13** | `follow_vendor` / `unfollow_vendor`, the relevance gate, `notify_published`, and `notify_cancelled` widened to followers ∪ past confirmers. |
| **API** | `POST`/`DELETE /vendors/{id}/follow`; `following` + `alerts_on` on the sheet; both publish paths fire the event; the portal reports `followers_notified`. |
| **UI** | The Follow control on the vendor sheet, below Navigate, with the consent copy. |

### One tap does three things, deliberately

`follow_subject` records the subject, **opts the class in**, and **clears any older mute** on it. E-D1
says silence is never consent — but a deliberate tap on "follow this cook" is not silence, it is a
request to be told. The other two are failure modes a driver could never debug: a follow into a class
that is switched off, or onto a vendor they muted months ago, is a control that reports success and
does nothing. **Unfollowing does not switch the class off** — that is a separate, louder choice.

### The relevance gate

`route_relevant_only` is now real. Radius **240 km** and maximum ping age **6 h**, both **F13 config**,
not constants. Two rules:

- **A stale ping is not a location.** Past the bound F3 returns `None` and the driver is left alone
  rather than targeted on a place they left days ago.
- **No fresh position, no push.** The message is not relevant enough to spend a scarce budget on.

Where several followed cooks publish the same day and the cap allows exactly one, the audience is
**ordered by distance**, so the survivor is the nearest rather than whichever the loop reached first.

### Caps unchanged, and asserted

Opt-in · P1 · **1 per driver per day** · the §13.1 global 2/day · quiet hours · RESTING · per-vendor
mute. Following twenty cooks still cannot produce twenty pushes, and a test asserts a follower is
budget-suppressed exactly like anyone else. A weekly series announces itself **once**, not once per
occurrence — a driver asked about a cook, not about a calendar.

## 4. Verified live

```
two drivers followed; both report alerts_on=True
cook published -> followers_notified=0
  near  -> [('suppressed', 'Ana Tamales published', 'Loves ... · Sun from 05:30')]
  far   -> nothing

OK — the nearby follower passed relevance and dispatch suppressed on
'quiet_hours' (02:30 UTC). The distant one was never considered at all.
```

**Worth reading carefully.** The nearby follower produced a notification row (relevance passed) which
dispatch then suppressed for quiet hours — correct per §13.3 at 02:30 UTC. The distant follower
produced **no row at all**: relevance stopped them before dispatch ever saw them. My first smoke script
asserted delivery without accounting for the clock and failed; the code was right and the assertion was
naive. A smoke test that does not know what time it is will lie to you.

## 5. Exact next task — recommendation

1. **Promotions still use prior-confirmation as their relevance proxy.** Now that real follows exist,
   inferring consent from a crowd contribution is the wrong heuristic in the one place it still runs.
   Changing who receives promotions is its own decision — it narrows an audience a vendor may be
   counting on — so it wants an owner call, not a quiet edit.
2. **Corridor food is inert.** At speed a driver sees three cooks ahead and can do nothing, not even
   "save for the next stop" (§11.4's deferred-safe pattern). Small and well-specified.
3. **No photos anywhere.** Needs an owner decision on moderation before any driver-visible image ships.

**Carried and still first in line from 079 §5a:** the geohash-boundary duplicate miss in
`find_duplicate_candidates`, paired with the `merge_facilities` attribute staleness it compounds.

## 6. Blockers

- **No git remote — nine sessions running.** Twenty commits sit locally on `main`.
- **`find_duplicate_candidates` misses duplicates straddling a geohash cell** (079 §5a).
- **`merge_facilities` may leave the survivor's attributes stale** — urgent once the above is fixed.
- **The vendor portal does not report follower-notification delivery in its UI.** The API returns
  `followers_notified`; no screen renders it yet. The promotions screen sets the precedent for how.
- **The claimable universe is ten facilities** and the ceiling is upstream in OSM (079 §5).
- **A vendor cannot delete their own listing or account** (§17 Q16).
- **Nothing rate-limits vendor registration.**
- **`categories` is collected and unused.**

## 7. Open questions (PRD §17)

Unchanged. **Q9 truck routing** stays load-bearing for food: distance is a straight line and no arrival
time is derived from it. Also open: Q1 · Q2 · Q3 · Q4 · Q5 · Q7 · Q8 · Q13 · **Q15 conduct policy** ·
**Q16 hard delete** · Q6.

## 8. Working rules (unchanged — non-negotiable)

Docker-only · **local commits only, NEVER push** · **plan first**, owner approval, then code · **tests
with every change** · live pulls never in CI · **AI-CONTEXT comments only** · import-linter
authoritative · **design-prd governs ALL UI** · §22.2 never improvises a token, component pattern,
navigation structure or **notification class** — this session added EVENTS to an approved class, not a
class · session ends by writing the next HANDOFF.

Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`.

**Phase A holds:** no order, basket, total, checkout or billing column anywhere.

## 9. Commits this session (local only, on `main`)

```
(this commit) docs: HANDOFF-081 — follow this cook
76aeaf1 The follow control says what one tap turns on
cc75112 Follow this cook: the event the food loop was missing
6791a2c F8 learns to follow, F3 learns to say where someone was
28e1b49 docs: HANDOFF-080 — distance, the lot, and a way to go
101bfdb The vendor sheet can now take you there
53febe7 Distance was null on the map and rendered only while driving
```

## 10. Key files touched

```
F8       api/app/foundation/f08_notifications/domain/models.py (followed_subjects)
         .../domain/service.py (follow/unfollow/is_following/followers_of) · public.py
F3       api/app/foundation/f03_location/domain/service.py (last_known_position)
         public.py
M13      api/app/modules/m13_vendor/domain/service.py (CONFIG_FOLLOW_*, follow_vendor,
         _relevant_audience, notify_published, publish gateway) · public.py
API      api/app/api/m13_vendor.py (follow endpoints, following/alerts_on on the sheet)
         api/app/api/vendor_portal.py (gateway on publish, followers_notified)
MIGRATION 0046_f08_followed_subjects
TESTS    api/tests/modules/m13_vendor/test_follow.py (NEW, 11)
         api/tests/foundation/f08_notifications/test_notification_class.py (+6)
         api/tests/foundation/f03_location/test_location.py (+4)
         api/tests/api/test_vendor_distance_api.py (+4)
UI       ui/src/core/components/VendorSheet.vue (the follow control)
         ui/src/surfaces/MapSurface.vue · ui/src/core/api.js
         ui/src/core/i18n/*.json (4 keys ×6) · ui/test/food-decide.test.js (+5)
DOCS     design-prd.md §23 ×2 (entries 36–37) · HANDOFF-081.md · HANDOFF.md
```

## 11. Ports / env

**No port or env changes.** LOCKED: postgres **5438** · api **8008** · ui **9008**. Migration 0046
applied. No new F13 flags — following rides the existing `m13_vendor` flag and the existing
`vendor_alert` class. Two new F13 **config** keys: `m13_follow_radius_m`, `m13_follow_ping_max_age_s`.

`make ci` leaves Postgres running, so `make up` straight afterwards fails preflight.
**`make down && make up`** is the sequence.
