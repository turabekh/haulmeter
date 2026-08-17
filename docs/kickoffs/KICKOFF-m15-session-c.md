# KICKOFF — M15 Session C: the surface that makes it reachable

**Status: APPROVED 2026-08-18 (owner), AMENDED mid-session — see §0.** D14 is signed at
**scope (b) — Session A only**, with "B and C authorized against this entry by their own
kickoffs." This document is that kickoff for C. Decision-log entry **179** records the
approval, the signed band thresholds and the amendment; entry **180** records the defect
that forced it.

---

## 0. What the owner signed, and the one thing that changed

**Signed as written:** the scope in §2, **band thresholds `m15.band_green_min` 80 /
`m15.band_yellow_min` 55**, and **six locales + pseudo** with the seven-locale DoD line
recorded as OPEN rather than claimed.

**Amended, on a finding:** the **F14 content review/publish surface joins this session's
scope.** The reason is in §4a. Without it every surface below renders its empty state
permanently — there is no path, anywhere in the product, for content to become `released`,
so the driver screens would have nothing to show on production or on the owner's own
machine.

---

## 1. The premise, stated so it can be challenged

M15 has 12 module files, 10 test files, 12 tables, a scored session loop, a rubric bridge,
and this codebase's first WebSocket. **No human outside the build has ever used any of it,
and none can** — there is no UI, no locale string, and every route is gated on
`m15_roadside`, which is OFF.

By the validation law that is the whole problem. More engine does not shorten the distance
to a validated driver outcome; **a surface does.** So Session C builds the driver surface
and nothing else, and the module becomes something a person can be handed.

---

## 2. Scope — what Session C does

The smallest slice that turns "unreachable" into "used by someone who is not the owner."

1. **Entry: a More row.** §10.5 keeps More a plain 64 dp row list — **no cards, no promos,
   no badges** — so this is a row ("Roadside Ready" + one-line caption). **No new
   bottom-nav tab**: tab changes remain the standing A8/D7 owner decision.
2. **Consent surface**, in every locale shipped. E3's consent flow is a Phase A DoD line and
   it gates recording a driver's voice.
3. **Session surface** — full-screen S1 shape, optional oversized officer-line text mirror,
   56 dp mic, live listening state, **hard pause on DRIVING**. This is where the WebSocket
   carries its first frame.
4. **Result surface** — strengths / needs-practice per phrase family, claim prompt for
   guests, "Start my plan" as the primary CTA (the CTA lands; the plan itself is Session D).
5. **Paperwork in the same commits, not after:** layout-harness registration for every new
   surface, all four states on every fetching surface (loading / data / empty / failed — a
   fixture is never one of them), DRIVE.md's Readiness journey, decision-log entries for the
   P-3 composition.

**Everything is composed from existing tokens and components.** If a new token, colour, type
size, spacing value, component pattern or navigation structure proves necessary — **STOP and
ask**, per §22.2. That is not a formality here: a full-screen voice surface with a 56 dp mic
is the kind of screen that invites invention.

## 3. What Session C explicitly does NOT do

- **No notifications of any kind.** P-1 `readiness_reminder` and P-2 `readiness_invite` are
  **PROPOSED, NOT APPROVED** (entry 177) and a notification class is a §22.2 never-improvise
  category. No class is registered and no call site exists; it stays that way.
- **No FR5 teaching loop, no FR6 drill plan, no FR7 record or `/verify` edge change.** The
  tables exist; the logic is Sessions D and E.
- **No payment code paths.** Phase A carries zero, and `m15_billing` does not exist.
- **No flag flip.** `m15_roadside` stays OFF at the end of Session C. Turning it on opens
  the free Roadside Check platform-wide and is the owner's call, made once there is
  something worth opening.
- **No deploy.** Production does not have the m15 flag row or migrations 0084–0087, and that
  stays true until you ask.

## 4a. The amendment: the publish path, and why it is not scope creep

Two facts, both found by reading rather than assuming:

- **Nothing is released and nothing can be.** The DEV_SEED scenario is draft by explicit
  design — *"DRAFT, and it stays draft… which is exactly what makes it safe to seed"* — and
  Q-6 forbids draft reaching a driver.
- **`mark_reviewed` and `release` exist in `domain/content.py` and nothing exposes them.**
  `admin.py` carries no m15 reference. The review pipeline has no operator surface, so no
  human can move content forward through any screen in the product.

Add the entry-180 fix — a client could previously set `allow_draft` itself, and now cannot —
and the driver surfaces would be permanently empty. So Session C also builds the **F14
content review/publish surface** that E3 §E3.1.5 already specifies: list draft/reviewed
content, mark reviewed with a named human, release with a version bump.

**The officer lines are English.** Q-6 requires a *named human* reviewer, not a native Uzbek
speaker, so the owner can review and release scenario 1 himself. The Uzbek dependency stays
on Session D's coaching content, where it belongs.

It also needs **`GET /roadside/scenarios`**: the probe finds a scenario by querying the
database directly, and there is no HTTP route by which a client could ever learn one. A
surface cannot open a session it has no way to name.

## 4. Three things that block the Phase A DoD, and none of them are code

Naming these now because "complete M15" is not reachable this session, and a plan that
implies otherwise is the deferral-that-cannot-fail the validation law warns about.

| blocker | what it stops | who can clear it |
|---|---|---|
| **Tajik has no native review** (`docs/i18n-drafts/tg.draft.json`, needs a paid reviewer) | the **seven-locale gate**, which is a Phase A DoD line. Session C can ship six + a pseudo-locale pass, but the gate stays open | owner — it costs money, not time |
| **Uzbek voices unheard, content unreviewed** — `docs/voice-samples/`, and the DoD wants **≥40 intents released** through the review pipeline | FR5/FR6 content, and any claim that coaching is usable | a native speaker |
| **Band thresholds and calibration floor are my numbers** — `m15.band_green_min` 80, `m15.band_yellow_min` 55, `m15.calibration_min_samples` 30 | what a driver is TOLD they are. The result surface renders these | owner (tunable without a deploy) |

The third one lands inside Session C's scope: the result surface displays a band. **I would
rather show a band the owner has signed than one I invented.**

## 5. Order of work

Plan-first, then in this order, each with tests alongside:

1. Locale keys for every string in the slice, all shipped locales + pseudo-locale — **first**,
   because retrofitting strings is how a locale gate goes red at the end.
2. The More row + routing + flag gating (nothing visible while `m15_roadside` is OFF).
3. Consent surface.
4. Session surface — and **the first real WebSocket frame is its own checkpoint**, exercised
   against the running stack, not asserted in a unit test.
5. Result surface.
6. DRIVE.md journey + layout-harness registration + decision entries, same commits.

## 6. Definition of done for THIS session

- A person who is not the owner can open the app with the flag on locally, reach Roadside
  Ready from More, consent, hold a spoken session, and see a band — **observed in a browser
  on a 360 × 800 viewport, not in a suite.**
- Every surface registered in the layout harness, four states each, seven-or-six locales
  passing per §4's decision, DRIVING policy verified, a11y pass.
- `make ci` green; import-linter 32/32.
- `m15_roadside` still OFF; nothing deployed; no notification class registered.
- The next session's kickoff written.

## 7. What I need from you before I start

1. **Approve or cut this scope.** In particular: is UI-only the right slice, or do you want
   FR5/FR6 folded in — which makes it two or three sessions of work under one heading?
2. **The band thresholds** (§4, row 3) — sign the numbers or give me different ones.
3. **The locale decision** — ship six and hold the seven-locale gate open, or fund the Tajik
   review first.

Nothing else is blocking, and none of it is blocked on D15/D18/D19 — those govern billing,
neutral brand and assessment mode, all outside Phase A.
