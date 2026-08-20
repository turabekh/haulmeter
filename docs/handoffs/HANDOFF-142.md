# HANDOFF-142 — the pack stopped saying it notified them before it had proof

One slice, one defect, one reversal: **decision 229**, which overturns the 2026-07-26
entry on the evidence pack's timeline order. The kickoff was right about the defect and
stale about half of the fix — §1.2 was already built and shipping.

The through-line this time is smaller and sharper than 141's: **the fixture that proves a
bug can stop proving it, and it fails green.**

---

## 1. State at the break

```
local  gates 2639 pytest (2632 + 7) · 1125 vitest · 32/32 contracts · ruff clean
local  stack UP — api 8008 · ui 9008 · db 5438 · alembic 0094_f03_attested_presence
prod   UNCHANGED — no deploy, out of scope by kickoff §3
git    committed locally, NOT pushed (rule 3 — the owner's call)
```

No layout-harness run is owed: **no UI file changed.** The pack renderer is English-only —
there is no locale mechanism in `render.py` — so no i18n sweep applies either.

## 2. What was actually wrong

The human timeline sorted on `occurred_at`, the driver's phone clock. Two stop packets
rendered **"notice sent" and "pack shared" above the photographs they summarise**, which
an AP clerk reads as *notified before proof existed*. Correct data, nothing fabricated,
nothing lost — a render/ordering bug that hands a broker a denial pretext.

**Two causes, both structural rather than freak, and the packet had both:**

1. `occurred_at` is the driver's device and **nothing in F4 corrects its skew** —
   `attach_artifact` takes `captured_at` from the client verbatim.
2. Records carry the moment they *describe*, not the moment they were *written*.
   `reconcile_delivered_notices` (`m03_detention/domain/service.py:465`) passes
   `message.sent_at` deliberately — "the pack states when the broker was reached, not when
   a janitor noticed" — so the row is appended hours after the instant it carries.

## 3. Sort keys, before and after

**Three sort sites, not the two the kickoff listed.** `compose_grouped_pack` — the route
pack M4.R will render — was the one it missed.

| site | before | after |
|---|---|---|
| `service.py:369` `compose_grouped_pack` | `(group_order, occurred_at is None, occurred_at)` | `ordering.timeline_key` |
| `service.py:427` `compose_stop_pack` | `(occurred_at is None, occurred_at)` | `ordering.timeline_key` |
| `render.py:319` `_chronological` | `key="occurred_at"` param | `ordering.timeline_key` |

The key is `(group_order, server, client, terminal, seq)` — new module
`f04_evidence/domain/ordering.py`, imported by both layers, because **two sorts that must
agree and are written separately will drift**, and the way you find out is a broker
reading a document that contradicts itself down the page.

- `server` = `received_at` falling back to `occurred_at`; `client` the reverse. **Never
  the epoch** — a record must not leave a timeline, or leap to the top of one, because a
  stamp is absent.
- `terminal` = 1 for `payload["event"] in {notice_sent, pack_shared, stop_packet}`. These
  are **payload event strings, not `RecordType` members** — the kickoff called them record
  types; the enum has only six members and none of them says "conclusion".
- `group_order` stays leftmost, so **§23 entry 78's stop grouping is untouched.**
- A latent crash fixed on the way through: all three sorts compared datetimes straight,
  and a naive stamp against an aware one raises `TypeError` mid-render. Every clock is
  normalised to UTC in the key.

## 4. The divergence threshold: 300 s, unchanged and deliberately

**§1.2 of the kickoff was stale — `_divergence_note` already existed and already shipped**
(`render.py:339`, `DISCLOSE_DIVERGENCE_S = 300` at `render.py:95`), with two tests pinning
it. The work was a **polarity flip**, not a build: primary stamp is now the server's clock
and the annotation is the driver's.

```
before   2026-07-20 08:06:00 UTC · filed 14:22        (ordered by 08:06)
after    2026-07-20 14:22:00 UTC · captured 08:06     (ordered by 14:22)
```

The primary stamp is the clock the rows are **ordered by**, or the document argues with
itself down the page. **The threshold stays 300 s** against the kickoff's proposed 60 s
(owner-confirmed): five minutes was reasoned about in the entry being reversed, sits above
ordinary drift and sync latency, and 60 s would annotate jitter on rows that mean nothing.

## 5. The regenerated packet, before and after

Same records, same chain, rendered both ways:

```
BEFORE — phone clock                     AFTER — server clock
07:58  arrived                           07:59              arrived
08:04  on_time_check                     08:04              on time check
08:30  notice_sent      <-- above        14:22 · cap 10:02  prompted: seals
08:38  pack_shared      <-- the photos   14:22 · cap 10:03  prompted: trailer number
10:02  seals                             14:28 · cap 08:30  notice sent
10:03  trailer number                    14:33 · cap 08:38  pack shared
```

**The PDF was regenerated and read, not just asserted on** — arrive → on-time check →
photos → notice sent → pack shared, divergent rows annotated, "Hash chain intact",
6 records, head seq 5.

## 6. Tests

`tests/foundation/f04_evidence/test_timeline_ordering.py`, 7 new:

- the packet-28 causal invariant (red-first, and it was genuinely red)
- **a companion asserting the fixture DOES invert under the old key** — see §8
- terminal events sort last at an equal instant, all three of them
- null-safety at the dict boundary, and naive/aware stamps together
- `compose_stop_pack` orders at the merge, not just at the renderer
- `compose_grouped_pack` keeps its stops apart

`test_render.py::test_a_late_filed_record_discloses_both_clocks` had its assertion flipped
(`captured 07:58` primary-stamped `14:22:00 UTC`, and `filed 14:22` asserted **absent**).
`test_ordinary_drift_is_not_announced_on_every_row` needed no change — sub-threshold rows
stay quiet in both polarities.

## 7. Preserved for M4.R

**The machine-readable dual-clock fields are intact.** `compose_pack` still emits both
`occurred_at` and `received_at` on every timeline dict (`service.py:466–475`), and
`compose_stop_pack` / `compose_grouped_pack` still carry both through the merge. The
Relay dispute pack and trace render this same timeline; nothing was narrowed for them.

## 8. What this session got wrong first

**The red-first fixture did not reproduce the bug.** I wrote the photo's phone stamp
*earlier* than the notice's, so phone-clock order was already correct, and the test that
was supposed to fail **passed against the unfixed code**. It would have passed forever
while asserting nothing.

The companion test — "assert this fixture inverts under the old key" — is what went red
and gave it away. Only after checking `reconcile_delivered_notices` did the real shape
come out: the notice carries `sent_at` and is *written* hours later, and the phone is
skewed. **Filed as TRAPS 7b.** A green red-first test is not evidence the fix works; it is
evidence the fixture no longer describes the bug.

## 9. The asymmetry this leaves — for the next session

**`stop_evidence` is deliberately NOT aligned** (owner decision, confirmed at approval).
The driver's own "what have I got" view still sorts on `occurred_at` (`service.py:196`)
and **its emitted dict carries no `received_at` at all**, so:

- `ClaimSurface.vue:230` and `EvidenceSurface.vue:244` render a **capture-time** order
- the PDF a broker receives renders a **server-time** order

The same stop can therefore read in two different orders on two surfaces. It is out of
scope here and needs a field added to the response before it can be changed — a small
slice of its own, not a tidy-up.

## 10. Untouched, and stated so it is not "fixed" later by accident

- **The hash chain stays `seq`-ordered.** The timeline is a view; the verification block
  still covers filing order. These are deliberately different lists.
- **`_located_points` keeps `occurred_at`** (`render.py:507`) — a GPS trace is a path
  through capture time, and ordering a route by filing time draws a zig-zag nobody drove.
  `test_render.py:230` pins it.
- **`_chain_time` keeps `occurred_at`** — the document's date, not its timeline, and
  determinism (PRD §11) rests on it.
- External/RFC-3161 anchoring, UTC→local display, artifact thumbnails: all still deferred,
  all still out of scope.

## 11. Still open from 141

Unchanged by this session: **the pilot day** remains the largest gap between built and
validated, and Perth Test Dock still makes it runnable. **N-06 · N-09 · N-10 PARTIAL ·
N-11 · N-18** all still open. 134 §9's owner questions still stand.
