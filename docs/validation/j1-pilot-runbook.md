# Journey 1 — the pilot day, as an operator runbook

**What this is.** The technical half of the afternoon that closes five of the seven lines in
[`j1-journey.md`](j1-journey.md). It is the preflight, the sequence, and the evidence to
capture per line.

**What it is not.** It is not the driver's copy — [`j1-pilot-driver-pack.md`](j1-pilot-driver-pack.md)
is what the driver is handed, and it deliberately withholds the tap-by-tap money flow so
lines 1–3 can still be observed. It is not the observation protocol — [`../WATCH.md`](../WATCH.md) owns
that, and its ONE RULE (*give the instruction, then say nothing*) governs the whole day.
This page never says what to say to the driver; WATCH.md does. **Nothing here ticks a line.**
A session adds an OBSERVED row; whether it clears anything is the owner's reading.

**Why it exists.** Five of the seven need one driver, one broker and one afternoon. The way
that afternoon is lost is not the driver — it is a flag that was off, a handset that never
registered for push, or a parse with no key behind it. All of that is checkable in advance,
and on 2026-08-17 it was.

---

## 1. Preflight — measured on production, 2026-08-17

Every row below was read off `haulmeter-test` (`uzimiz-prod`, `us-central1-a`) with a
read-only `select`. Re-run them the morning of; a fact from a page is a fact from a page.

| what | measured | reading |
|---|---|---|
| `j1_contact_parse` | `enabled = t` | **line 1 is live** |
| `j1_fee_disclosure` | `enabled = t` | **line 7's Money row is live** |
| `j1_arrival_nudge` | `enabled = NULL` → `default_on = f` | **OFF — line 5 cannot be observed.** §2 |
| `f09.ai_call` `f05.document_parse` | 57 calls, last **2026-08-16** | **the rate-con parse works on the box with a real key** |
| `f08.push_subscription` | **0 rows** | **no handset has ever registered.** §2 |
| `f05.stop` | 27 armed · 18 with an appointment · **0 in the future** | the flag flip in §2 fires for nobody |
| `f08.outbound_message` | **0 unsent** of 62 | the queue is clean; nothing drains under a live identity on recreate |
| services | api · caddy · postgres · redis · worker · minio · mailpit all Up | — |
| alembic head (prod) | `0083_receivable_kind_fee` | local is `0087_m15_hidden`; **0084–0087 are unshipped M15** and none of J1 needs them |
| `f13.validation_gate` | no row for any `j1_*` flag | `enable()` will not refuse §2's flip |
| accounts | 181 | — |

The query, verbatim:

```
gcloud compute ssh haulmeter-test --project=uzimiz-prod --zone=us-central1-a --quiet \
  --command="cd /opt/haulmeter/infra && sudo docker compose -f docker-compose.deploy.yml \
  --env-file .env exec -T postgres psql -U longhaul -d longhaul -p 5438 \
  -c \"select key, enabled, default_on from f13.feature_flag order by key;\""
```

**The local stack is not this.** All four `j1_*` flags resolve OFF locally (`enabled` NULL,
`default_on` false), so a rehearsal on `localhost:9008` shows a product without the contact
prefill or the fee disclosure. Match dev to prod before rehearsing, or don't rehearse.

---

## 2. Two things the owner must decide BEFORE the day

**Neither is a session's call.**

**(a) `j1_arrival_nudge` — line 5 is self-blocking as written.** The line says the
observation *gates the flag ON*, and `dispatch_arrival_reminders` returns `[]` while the
flag is off. Nothing can be observed. The flag is **global**, not per-account — so the
question is blast radius, and it was measured: **27 armed stops, 18 with appointments, 0
with an appointment in the future**, and the reminder window is `[now, now + 15 min]`.
Turning it on today sends nothing to anyone. It would fire for the pilot driver's stop and
no other. There are **no validation gates** on the flag, so `/admin/flags` will enable it.

The honest sequence: **enable it for the pilot window on `/admin/flags`, observe, then
decide whether it stays.** `clear_decision` hands it back to the code default afterwards —
`disable()` would write False and the declared default could never apply again.

**(b) The broker's inbox for line 6.** LIVE-FIRE: the claim leaves the box for real, from
`claims@haulmeter.online`, under the owner's identity. **A real broker who has agreed to
receive it, named before the day starts.** Nothing is addressed to an inbox the owner does
not control without that agreement.

---

## 3. What the day cannot close

Say this before it feels like failure.

- **Line 3 (the risk line)** has a data precondition, not a code one: the pre-acceptance
  pair renders at n≥5 completed visits, and the docks that clear that floor carry
  walkthrough traffic. It will render honestly and say almost nothing. That is the floor
  working.
- **Line 7 (the first claim PAID)** is a broker's decision on a broker's calendar. Line 6
  is the send; line 7 arrives days later, and its observable is the **Money row showing
  gross · fee · net** with the year figure moving by exactly the net — not a notification.

So: **five lines, and two that start their clock.**

---

## 4. The afternoon, in order

Run them in this order — each leaves the state the next one needs. Bring: a **real rate
con** on paper, the driver's **own handset** (WATCH.md rule 2), and the broker contact
from §2(b).

### Line 1 — a contact parsed off a real rate con

1. Driver signs in on their own account. `/load` → add a load by rate-con photo.
2. **They photograph the paper. Nobody types.**
3. The confirm screen is the feature: every parsed value lands editable and labelled as
   read from the rate con.

**Capture:** a screenshot of the confirm screen **before any edit**, with the broker's
address in the contact field. Afterwards, the F5 counterparty row carrying it.
**Disqualified if:** anyone types into the contact field, or the driver is the owner.
**If the parse fails:** the document is still filed and the manual form takes over. That is
a designed state, and it is a result worth recording — not a retry.

### Line 2 — the money terms read in Uzbek

Same screen, no navigation. Locale `uz` set before the session, not during.

**Capture:** where they stop, WATCH.md style — not what they say. Whether they reach the
English original in **one tap**.
**Disqualified if:** anyone translates, points, or explains. Rule: *say nothing*.

### Line 5 — the arrival path on a real handset

**Preconditions, both:** §2(a) done, **and the handset has granted notification permission
so a `f08.push_subscription` row exists** — production has zero today, so this will be the
first. Check the row before waiting on a push.

1. Arm a stop with an appointment ~20 minutes out.
2. Wait for T−15 on the driver's phone. Do not open the app.
3. **The negative half is half the line:** a stop whose visit is already open must produce
   **no push** — presence suppresses the nudge.

**Capture:** a screen recording of the push arriving and the deep link landing **with the
arrival CTA in view**; the `f08.notification` row; the push-subscription row.

### Line 4 — a packet confirmed usable by a real dispatcher

Generate the pack, send it to an AP clerk or dispatcher who is not the owner.

**Capture:** their words, verbatim, on whether it is enough to act on. Confirm the pack
states **the visit window and who reported the departure**.
**Do not treat a link open as evidence of who opened it** — finding F4-1; `opened_count`
answers a different question than the one you are asking.

### Line 6 — the first real claim sent

1. **Check the outbound queue before**: it was 0 unsent of 62.
2. File the detention claim to the broker from §2(b).
3. **Check it left**: the `f08.outbound_message` row carries a `sent_at` and a
   `provider_ref`.
4. **The line is not the row.** It closes when *the broker has it* — confirmed out of band,
   in their words.

---

## 5. After

Add one row per observation to the **Observations** table in
[`j1-journey.md`](j1-journey.md), with the evidence named. **Do not tick a line.** The owner
reads the evidence and decides what it clears.

If the day produces stop-points rather than closures, they belong in WATCH.md's log — two
drivers stopping in the same place is a defect row, and that is a result, not a wasted
afternoon.
