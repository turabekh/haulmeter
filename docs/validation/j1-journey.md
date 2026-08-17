# Journey 1 — validation log

**Living checklist. Journey 1 is BUILT and deployed; none of the seven below has happened
yet.**

v2.0's validation law: *done = a paying party used it and the outcome is in the database*.
Everything on this page is the world, not the suite. As of 2026-08-16 the suite is green —
pytest 2130, vitest 1020, layout 365, import-linter 31/31 — and that proves **nothing here**.

**Nothing is ticked by a session.** A session may add an OBSERVED row with its evidence;
whether that clears a line is the owner's reading. Each line is dated **when the world does
it**, not when the code shipped.

➡️ **[`j1-pilot-runbook.md`](j1-pilot-runbook.md)** — the operator's preflight and evidence
sheet for the afternoon that closes five of these seven. It carries the production state as
measured on 2026-08-17 and the two decisions the owner must make before the day.

---

## The seven

| # | Observation | State | What would clear it |
|---|---|---|---|
| 1 | **A contact parsed off a real rate con** | ☐ open | A driver who is not the owner photographs a real rate con; the broker's address lands in the confirm field with **no manual typing**, and the F5 counterparty row carries it afterwards |
| 2 | **The money terms read in Uzbek by a real driver** | ☐ open | A driver whose locale is `uz` reads a real rate con's money terms off the confirm screen **without help**, and finds the English original in one tap. Watched, WATCH.md style: record where they stop, not what they say |
| 3 | **The risk line seen at a real load decision** | ☐ open | A driver mentions the raw pair **unprompted** while deciding on a load. Needs a dock with ≥5 completed visits — see the note below |
| 4 | **A packet confirmed usable by a real dispatcher** | ☐ open | An AP clerk or dispatcher who is not the owner reads a generated pack and says it is enough to act on. The pack states the visit window and who reported the departure |
| 5 | **The arrival path observed on a real handset** | ☐ open | The push arrives at T−15 on a real phone, the deep link lands with the arrival CTA in view, and **no push arrives** for a stop whose visit is already open. **This gates `j1_arrival_nudge` ON** — a class nobody has watched arrive is a class nobody has validated |
| 6 | **The first real claim sent** | ☐ open | A real detention claim leaves the box to a real broker's inbox, from `claims@haulmeter.online`, and the broker has it |
| 7 | **The first real claim PAID** | ☐ open | A broker pays. The fee receivable posts, the Money row shows **gross · fee · net**, and the year figure moves by exactly the **net**. See the dormancy note below — the observable is the Money row |

---

## Three things a reader needs to know before ticking anything

**Line 3 has a data precondition, not a code one.** The pre-acceptance pair renders only at
n≥5 completed visits, and on 2026-08-16 production had **four** facilities clearing that
floor, all of them carrying walkthrough traffic (median completed visit: **0.9 minutes**;
3 of 58 exceeded a 120-minute free time). So the line will render honestly and say almost
nothing until real drivers make real stops. That is the floor working, not a fault.

**Line 7's observable is the Money row, NOT the notification.** The claim-paid P0 is
correct and **dormant by design** (001-116 era decision): `mark_receivable_paid` notifies
only when someone *other than the driver* records payment, and the only endpoint is
driver-only. It will first fire when M12 fleet payments or a collection-partner seam
exists. The body is built to spec and pinned by a test precisely because nothing exercises
it — a dormant path drifts in silence, and this one will first run in front of a driver
being told about their own money.

**Line 5 is the only line that gates a flag.** `j1_arrival_nudge` stays OFF until it is
observed on a handset. `j1_contact_parse` and `j1_fee_disclosure` are ON; both are prefill
and disclosure surfaces where the driver's confirm is the safety.

---

## Observations

*(none yet — a session adds rows here with evidence, and the owner decides what they clear)*

| date | line | what was observed | evidence |
|---|---|---|---|
| | | | |
