"""AI-CONTEXT: ONE sort key for the human timeline, in one place (§23 entry 229).

The chain is ordered by `seq` — filing order, the order the hashes commit to. A timeline
is ordered by TIME, and the two are deliberately different lists; `render._chronological`
has said so since the beginning and that stays true.

What changed is WHICH clock "time" means. F12 records two per record: `occurred_at`, the
client's time, and `received_at`, when the server saw it. The timeline sorted on
`occurred_at` — and a pack came back with "notice sent" rendered ABOVE the photographs it
summarises, which an AP clerk reads as *notified before proof existed*. Two real causes,
neither of them a data error:

  · a phone clock that disagrees with ours. `occurred_at` is the driver's device, and
    nothing in F4 corrects its skew.
  · records stamped with the moment they DESCRIBE rather than the moment they were
    written. `reconcile_delivered_notices` passes `message.sent_at` deliberately — "the
    pack states when the broker was reached, not when a janitor noticed" — so the row is
    appended hours after the instant it carries.

`received_at` is the one clock that is the same clock for an offline photo and a
server-written record, so it is the one that can order them against each other. This
REVERSES the 2026-07-26 decision, which chose capture time and was reasoning about
disclosure rather than causal order; the disclosure it added is kept and inverted, so the
row still says when the driver captured it.

The key is shared by `service.compose_*` and `render._chronological` because two sorts
that must agree and are written twice will eventually disagree — and the way you find out
is a broker reading a document whose order contradicts itself.
"""

from datetime import UTC, datetime

# AI-CONTEXT: the events that CONCLUDE a stop rather than happen during it. These are
# `payload["event"]` strings, not `RecordType` members — the type of a notice is
# USER_ACTION and the type of a shared pack is SYSTEM, neither of which says "this is a
# conclusion". Written where they are read: `f05_load` owns `notice_sent`, `sharing.py`
# writes `pack_shared`, `m05_protection` writes `stop_packet`, and F4 cannot import any
# of them.
TERMINAL_EVENTS = frozenset({"notice_sent", "pack_shared", "stop_packet"})


def _as_utc(value) -> datetime | None:
    """A naive stamp compared against an aware one raises TypeError mid-render, and all
    three of these sorts compared them straight. Normalise before comparing, always."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def timeline_key(record):
    """Order one row of a human-readable evidence timeline.

    `(group, server clock, client clock, conclusions last, seq)`

    · **group first.** A pack spanning a route sorts by STOP before anything else
      (§23 entry 78) — time alone interleaves two docks the moment a driver doubles back.
      Server-time ordering applies WITHIN a group, exactly as capture-time ordering did.
    · **server clock, then client clock.** The client's time breaks ties deterministically
      and is never the primary order.
    · **a missing clock falls back to the other one**, never to the epoch. A record must
      not disappear from a timeline, or leap to the top of it, because one stamp is
      absent. `received_at` is NOT NULL on the row, so this defends the dict boundary —
      `compose_grouped_pack` merges dicts from several packs and a producer can omit a key.
    · **conclusions last at an equal instant.** A notice written in the same second as the
      photo it summarises still sorts after it. A tiebreak, not a branch in the renderer.
    · **`seq` last**, so identical stamps order by filing and a regenerated pack stays
      byte-identical — which is what lets a pack's own hash identify it (PRD §11).
    """
    occurred = _as_utc(record.get("occurred_at"))
    received = _as_utc(record.get("received_at"))
    server = received or occurred
    client = occurred or received
    terminal = 1 if (record.get("payload") or {}).get("event") in TERMINAL_EVENTS else 0
    return (
        record.get("group_order", 0),
        server is None,
        server or datetime.min.replace(tzinfo=UTC),
        client is None,
        client or datetime.min.replace(tzinfo=UTC),
        terminal,
        record.get("seq", 0),
    )
