"""AI-CONTEXT: the human timeline is ordered by the SERVER's clock (§23 entry 229).

The packet-28 shape: a photo is captured at the dock with no signal and files hours
later; `notice_sent` is written by the mail reconcile the moment the email lands, so it
carries near-server time on both clocks. Sorting that mix on the driver's phone clock
put "notice sent" ABOVE the photographs it summarises — which an AP clerk reads as
"they notified us before they had proof", a denial pretext built out of correct data.

These tests are the causal invariant. They do not care how the rows are drawn; they
care that a conclusion never precedes its evidence.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.foundation.f01_identity import public as identity
from app.foundation.f04_evidence import public as evidence
from app.foundation.f04_evidence.domain.models import EvidenceRecord

T0 = datetime(2026, 7, 20, 7, 58, tzinfo=UTC)
TERMINAL = ("notice_sent", "pack_shared", "stop_packet")


def _account(db, email="ordering@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _set_received(db, log_id, event: str, received_at):
    record = db.scalars(
        select(EvidenceRecord).where(EvidenceRecord.log_id == log_id)
    ).all()
    for r in record:
        if (r.payload or {}).get("event") == event:
            r.received_at = received_at
    db.flush()


def _events(pack):
    from app.foundation.f04_evidence.domain.render import _chronological

    return [(r.get("payload") or {}).get("event") for r in _chronological(pack.timeline)]


def _packet_28(db, account):
    """The two ways the phone clock disagrees with the server about ORDER, together.

    The notice carries `08:30` because `reconcile_delivered_notices` stamps it with the
    message's own `sent_at` — "the pack states when the broker was reached, not when a
    janitor noticed" — while the ROW is appended when the sweep runs, at 14:28.

    The driver's phone is running two hours fast, so a seal photographed at 08:02 real
    time carries `10:02`. It is captured in a dead zone and files at 14:22.

    On the phone clock the notice (08:30) therefore sorts ABOVE the photo (10:02): the
    conclusion above its own evidence. On the server's clock the photo (14:22) sorts
    below the notice (14:28) — the order things actually happened in.
    """
    log = evidence.create_log(db, account.id, label="stop-0")
    evidence.append_record(
        db, log, evidence.RecordType.GEOFENCE, {"event": "arrived"}, occurred_at=T0
    )
    evidence.append_record(
        db,
        log,
        evidence.RecordType.USER_ACTION,
        {"event": "notice_sent"},
        occurred_at=T0 + timedelta(minutes=32),
    )
    # the phone is two hours fast: photographed at 08:02, stamped 10:02
    evidence.append_record(
        db,
        log,
        evidence.RecordType.PHOTO,
        {"event": "seal_photo"},
        occurred_at=T0 + timedelta(hours=2, minutes=4),
    )
    _set_received(db, log.id, "arrived", T0 + timedelta(hours=6, minutes=24))
    _set_received(db, log.id, "seal_photo", T0 + timedelta(hours=6, minutes=24))
    # the reconcile sweep appends the notice AFTER the photo has landed
    _set_received(db, log.id, "notice_sent", T0 + timedelta(hours=6, minutes=30))
    return log


def test_a_conclusion_never_precedes_the_evidence_it_summarises(db):
    """THE PACKET-28 REGRESSION. On the phone clock `notice_sent` (08:30) sorts above a
    photo captured at 08:00 but filed at 14:22. On the server's clock — the one clock
    that is the same for an offline photo and a server-written record — it sorts below.
    """
    account = _account(db, "packet28@example.com")
    log = _packet_28(db, account)
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.stop_record)

    events = _events(pack)
    assert events.index("seal_photo") < events.index("notice_sent"), (
        "the notice summarises the photo and must never be rendered above it"
    )


def test_the_old_phone_clock_order_would_have_misordered_it(db):
    """The bug, stated as a fact about the data rather than about the code: sorted on
    `occurred_at` this fixture DOES invert. If this ever stops being true the fixture
    has drifted and the test above proves nothing."""
    account = _account(db, "packet28proof@example.com")
    log = _packet_28(db, account)
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.stop_record)

    by_phone = sorted(pack.timeline, key=lambda r: r["occurred_at"])
    phone_events = [(r.get("payload") or {}).get("event") for r in by_phone]
    assert phone_events.index("notice_sent") < phone_events.index("seal_photo")


def test_no_terminal_record_outranks_a_capture_at_the_same_instant(db):
    """§1.3: when both clocks tie exactly, the conclusion still sorts last. A tiebreak
    in the sort key, not a special case in the renderer."""
    account = _account(db, "tie@example.com")
    log = evidence.create_log(db, account.id, label="stop-0")
    for event, rtype in (
        ("pack_shared", evidence.RecordType.SYSTEM),
        ("notice_sent", evidence.RecordType.USER_ACTION),
        ("seal_photo", evidence.RecordType.PHOTO),
        ("stop_packet", evidence.RecordType.SYSTEM),
    ):
        evidence.append_record(db, log, rtype, {"event": event}, occurred_at=T0)
    for event in ("pack_shared", "notice_sent", "seal_photo", "stop_packet"):
        _set_received(db, log.id, event, T0)

    pack = evidence.compose_pack(db, log, evidence.PackTemplate.stop_record)
    events = _events(pack)
    for terminal in TERMINAL:
        assert events.index("seal_photo") < events.index(terminal), (
            f"{terminal} is a conclusion and must sort after a same-instant capture"
        )


def test_a_record_missing_its_server_clock_is_not_dropped_or_thrown_to_1970():
    """Null-safety, asserted where a null can actually occur.

    `evidence_record.received_at` is NOT NULL with a server default, so the DATABASE
    cannot produce this row — an earlier draft of this test tried and was refused by the
    constraint, which is the right answer. The exposure is the dict: `compose_grouped_pack`
    merges timeline dicts from several packs, and any producer that omits the key hands
    the sorter a `None`. A missing clock must fall back to the row's own capture time —
    never drop the row, never sort it to the epoch ahead of everything.
    """
    from app.foundation.f04_evidence.domain.ordering import timeline_key

    rows = [
        {"seq": 0, "occurred_at": T0, "received_at": T0, "payload": {"event": "arrived"}},
        {"seq": 1, "occurred_at": T0 + timedelta(minutes=10), "payload": {"event": "orphan"}},
        {
            "seq": 2,
            "occurred_at": T0 + timedelta(minutes=20),
            "received_at": T0 + timedelta(minutes=20),
            "payload": {"event": "departed"},
        },
    ]
    events = [(r["payload"]).get("event") for r in sorted(rows, key=timeline_key)]

    assert "orphan" in events, "a missing clock must never delete a row from the timeline"
    assert events.index("arrived") < events.index("orphan") < events.index("departed"), (
        "the fallback is the row's own capture time, not the epoch"
    )


def test_naive_and_aware_stamps_sort_together():
    """A latent crash, not a nicety: all three sorts today compare datetimes straight,
    and mixing a naive stamp with an aware one raises TypeError mid-render. Every clock
    is normalised to UTC before it is compared."""
    from app.foundation.f04_evidence.domain.ordering import timeline_key

    naive = T0.replace(tzinfo=None)
    later = T0 + timedelta(minutes=5)
    rows = [
        {"seq": 0, "occurred_at": naive, "received_at": naive},
        {"seq": 1, "occurred_at": later, "received_at": later},
    ]
    assert [r["seq"] for r in sorted(rows, key=timeline_key)] == [0, 1]


def test_a_stop_pack_orders_by_the_server_clock_too(db):
    """Both layers, or they disagree: `compose_stop_pack` merges several logs and
    re-sorts, so the composition must use the same key the renderer does."""
    import uuid

    account = _account(db, "stoppack@example.com")
    stop_ref = uuid.uuid4()
    photo_log = evidence.create_log(db, account.id, stop_ref=stop_ref, label="condition")
    evidence.append_record(
        db,
        photo_log,
        evidence.RecordType.PHOTO,
        {"event": "seal_photo"},
        occurred_at=T0 + timedelta(hours=2, minutes=4),
    )
    _set_received(db, photo_log.id, "seal_photo", T0 + timedelta(hours=6, minutes=24))

    stop_log = evidence.create_log(db, account.id, stop_ref=stop_ref, label="stop-0")
    evidence.append_record(
        db,
        stop_log,
        evidence.RecordType.USER_ACTION,
        {"event": "notice_sent"},
        occurred_at=T0 + timedelta(minutes=32),
    )
    _set_received(db, stop_log.id, "notice_sent", T0 + timedelta(hours=6, minutes=30))

    pack = evidence.compose_stop_pack(db, stop_ref, evidence.PackTemplate.stop_record)
    events = [(r.get("payload") or {}).get("event") for r in pack.timeline]
    assert events.index("seal_photo") < events.index("notice_sent"), (
        "the MERGE must order by the server clock too, or the two layers disagree"
    )


def test_a_route_pack_keeps_its_stops_apart(db):
    """§23 entry 78 is not collapsed by this change: server-time ordering applies WITHIN
    a group, exactly as phone-time ordering did. A driver who doubles back must not get
    two docks interleaved into one confused visit."""
    import uuid

    account = _account(db, "route@example.com")
    first, second = uuid.uuid4(), uuid.uuid4()
    for stop_ref, event, minute in (
        (first, "pickup_photo", 2),
        (second, "delivery_photo", 200),
    ):
        log = evidence.create_log(db, account.id, stop_ref=stop_ref, label=event)
        evidence.append_record(
            db,
            log,
            evidence.RecordType.PHOTO,
            {"event": event},
            occurred_at=T0 + timedelta(minutes=minute),
        )
    # the DELIVERY files first — a route sorted by time alone would invert the stops
    _set_received(db, log.id, "delivery_photo", T0 + timedelta(minutes=5))

    pack = evidence.compose_grouped_pack(
        db,
        [("Pickup · Dallas", first), ("Delivery · Houston", second)],
        evidence.PackTemplate.load_record,
    )
    groups = [r["group"] for r in pack.timeline]
    assert groups == ["Pickup · Dallas", "Delivery · Houston"], (
        "stop grouping outranks time, in both sort keys"
    )
