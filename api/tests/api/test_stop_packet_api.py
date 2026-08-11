"""AI-CONTEXT: A1 requirement 5 over HTTP — the driver's review surface.

The queue is only worth building if a driver can see WHAT they are about to send and
to WHOM before they send it. A list that says "1 packet" and a Send button would
satisfy the letter of "the driver reviews" and none of its point: §11.7's rule that a
figure travels with what produced it applies to a document even more than to a number.

So the route returns the reference an AP clerk files by, the recipient, and the stop —
and the send route refuses anything already sent, because a retried tap must not put a
second document in a dispatcher's inbox.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.foundation.f05_load import public as loads
from app.main import app
from app.modules.m05_protection import public as m5

DOCK = (41.8781, -87.6298)


@pytest.fixture(autouse=True)
def _addressable(monkeypatch):
    """A packet's whole content is the link, so these tests run in a deployment that can
    address itself. The refusal path when it cannot is asserted separately."""
    from app.core import config

    monkeypatch.setenv("PUBLIC_BASE_URL", "https://haulmeter.online")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client, email="driver@example.com"):
    # the id comes back as a STRING in JSON; every production caller passes the UUID off
    # the Account object, and an ownership check comparing UUID to str fails silently
    import uuid as _uuid

    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    return _uuid.UUID(resp.json()["account_id"]), {
        "Authorization": f"Bearer {resp.json()['token']}"
    }


def _drafted(db, account_id, now):
    broker = loads.create_counterparty(
        db, "Bolt Logistics", loads.CounterpartyKind.broker, contact_email="ap@bolt.example"
    )
    load = loads.create_load(db, account_id, counterparty_id=broker.id, reference_number="BL-77")
    fac = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Dock 4", *DOCK
    )
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery)
    loads.arm_stop(db, stop)
    return m5.draft_stop_packet_on_exit(db, account_id, fac.id, now), broker


def test_the_queue_shows_what_is_about_to_be_sent_and_to_whom(db, client):
    from datetime import UTC, datetime

    account_id, headers = _auth(client)
    _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))

    rows = client.get("/protection/stop-packets", headers=headers).json()
    assert len(rows) == 1
    row = rows[0]
    assert row["reference"] == "BL-77", "an AP clerk files by this; the driver should see it"
    assert row["recipient"] == "ap@bolt.example", "a driver must see WHO receives it"
    assert row["facility_name"] == "Dock 4"
    assert row["state"] == "draft"


def test_a_sent_packet_leaves_the_queue(db, client):
    from datetime import UTC, datetime

    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))

    resp = client.post(f"/protection/stop-packets/{packet.id}/send", headers=headers)
    assert resp.status_code == 200
    assert client.get("/protection/stop-packets", headers=headers).json() == []


def test_sending_twice_does_not_send_twice(db, client):
    from datetime import UTC, datetime

    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))
    first = client.post(f"/protection/stop-packets/{packet.id}/send", headers=headers)
    second = client.post(f"/protection/stop-packets/{packet.id}/send", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200, "a retried tap is not an error"
    assert second.json()["state"] == "sent"


def test_one_driver_cannot_send_anothers_paperwork(db, client):
    from datetime import UTC, datetime

    account_id, _ = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))
    _, other = _auth(client, email="other@example.com")

    assert client.post(
        f"/protection/stop-packets/{packet.id}/send", headers=other
    ).status_code == 404
    assert client.get("/protection/stop-packets", headers=other).json() == []


def test_a_deployment_that_cannot_address_itself_REFUSES(db, client, monkeypatch):
    """For a detention CLAIM the notice still means something without a link. For a
    HANDOFF the link IS the document, so sending would deliver an empty promise. The
    draft stays in the queue, and the driver is told plainly rather than shown a 500."""
    from datetime import UTC, datetime

    from app.core import config

    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))

    monkeypatch.setenv("PUBLIC_BASE_URL", "")
    config.get_settings.cache_clear()
    resp = client.post(f"/protection/stop-packets/{packet.id}/send", headers=headers)

    assert resp.status_code == 503
    assert len(client.get("/protection/stop-packets", headers=headers).json()) == 1


# AI-CONTEXT: the fallback path, which is the one that had to work and did not.
#
# Only the F3 geofence EXIT drafted a packet. §15.5's rule is "build for auto, degrade
# to one-tap, never to nothing", and the background sensor everything here rides on is
# the mechanism v2.0 DoD #8 records as UNPROVEN — so a driver whose phone never fired
# an EXIT tapped "Leave this stop" and got no paperwork at all, with no way to recover
# it afterwards: departing ends the stop's armed life, and the draft finds the stop
# through `active_stop_for_account`.
def _armed_stop(db, account_id):
    broker = loads.create_counterparty(
        db, "Bolt Logistics", loads.CounterpartyKind.broker, contact_email="ap@bolt.example"
    )
    load = loads.create_load(db, account_id, counterparty_id=broker.id, reference_number="BL-88")
    fac = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock 9", *DOCK)
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery)
    loads.arm_stop(db, stop)
    return stop


def test_leaving_the_stop_BY_HAND_drafts_the_packet(db, client):
    account_id, headers = _auth(client)
    stop = _armed_stop(db, account_id)

    assert client.get("/protection/stop-packets", headers=headers).json() == []
    assert client.post(f"/load/{stop.id}/end", headers=headers).status_code == 201

    rows = client.get("/protection/stop-packets", headers=headers).json()
    assert len(rows) == 1, "the one-tap fallback produced no paperwork"
    assert rows[0]["facility_name"] == "Dock 9"


def test_the_geofence_and_the_hand_do_not_produce_two_packets(db, client):
    """One stop is one document. A driver whose EXIT fired and who then taps the
    control anyway must not send their broker the same paperwork twice."""
    from datetime import UTC, datetime

    account_id, headers = _auth(client)
    stop = _armed_stop(db, account_id)
    m5.draft_stop_packet_on_exit(
        db, account_id, stop.facility_id, datetime(2026, 8, 1, 12, tzinfo=UTC)
    )

    client.post(f"/load/{stop.id}/end", headers=headers)

    assert len(client.get("/protection/stop-packets", headers=headers).json()) == 1


# AI-CONTEXT: what the review CARD and its sheet read. A1 req 5 is "the driver reviews
# before it sends", and a review of a document whose contents are not stated is a
# confirmation dialog with extra words.
def test_the_queue_says_WHAT_is_in_each_packet(db, client):
    from datetime import UTC, datetime

    PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))
    stop = loads.get_stop(db, packet.stop_ref)
    m5.capture_document(db, account_id, "bol", PNG, filename="bol.png", stop_ref=stop.id)

    row = client.get("/protection/stop-packets", headers=headers).json()[0]

    assert "bol" in row["contents"], "the driver cannot see what they are about to send"
    assert "pod" not in row["contents"], "an uncaptured item was reported as captured"


def test_a_packet_with_no_claim_at_all_says_so(db, client):
    """`None` means nothing is FILED — never that nothing is owed."""
    from datetime import UTC, datetime

    account_id, headers = _auth(client)
    _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))

    row = client.get("/protection/stop-packets", headers=headers).json()[0]

    assert row["claim"] is None


def test_a_FILED_claim_rides_along_as_its_own_section(db, client):
    """The bundle (owner decision, 2026-08-02): the review moment shows the paperwork
    AND the claim, two labelled sections, one Send."""
    from datetime import UTC, datetime

    from app.foundation.f08_notifications import public as notify
    from app.modules.m03_detention import public as m3

    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))
    stop = loads.get_stop(db, packet.stop_ref)
    loads.record_stop_event(db, stop, "arrived")  # the chain a pack is composed from
    claim = m3.start_claim(db, stop)
    m3.generate_pack(
        db, claim, now=datetime(2026, 8, 1, 18, tzinfo=UTC),
        gateway=notify.RecordingNotificationGateway(),
    )

    row = client.get("/protection/stop-packets", headers=headers).json()[0]

    assert row["claim"] is not None, "a filed claim did not reach the review sheet"
    assert row["claim"]["state"] != "open"


def test_a_claim_still_RUNNING_is_not_offered_as_one_to_send(db, client):
    """An `open` claim is a clock, not a document. Reporting it as a section would put
    a Send beside money the driver has not filed — §12.2: the button says what it does."""
    from datetime import UTC, datetime

    from app.modules.m03_detention import public as m3

    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))
    m3.start_claim(db, loads.get_stop(db, packet.stop_ref))  # started, never filed

    row = client.get("/protection/stop-packets", headers=headers).json()[0]

    assert row["claim"] is None


def test_the_driver_can_correct_the_address_it_goes_to(db, client):
    """A1 requirement 6: recipients come from the F5 registry and are DRIVER-EDITABLE.
    The address on file is a default, not a verdict."""
    from datetime import UTC, datetime

    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))

    resp = client.post(
        f"/protection/stop-packets/{packet.id}/send",
        headers=headers,
        json={"recipient": "night.desk@bolt.example"},
    )

    assert resp.status_code == 200
    from app.foundation.f04_evidence import public as evidence

    shared = db.get(evidence.SharedPack, packet.shared_pack_ref)
    assert shared.recipient == "night.desk@bolt.example"


def test_omitting_the_address_still_uses_the_one_on_file(db, client):
    from datetime import UTC, datetime

    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))

    assert client.post(
        f"/protection/stop-packets/{packet.id}/send", headers=headers
    ).status_code == 200


# AI-CONTEXT: the review's SECOND exit (owner request, 2026-08-11).
#
# A1 req 5 is "the driver reviews before it sends", and until now a review could only
# conclude one way. A packet the driver did not want stayed on the Load tab forever, and
# the only control that could clear it was Send — so the product's answer to "I don't
# need to send this" was to send it.
#
# The invariants worth asserting are what discard must NOT do: it must not deliver, it
# must not destroy the driver's evidence, and it must not be undoable by driving through
# the same geofence again.
def test_a_discarded_packet_leaves_the_queue(db, client):
    from datetime import UTC, datetime

    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))

    resp = client.post(f"/protection/stop-packets/{packet.id}/discard", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["state"] == "discarded"
    assert client.get("/protection/stop-packets", headers=headers).json() == []


def test_discarding_sends_NOTHING(db, client):
    """The whole point. `sent_at` and `shared_pack_ref` stay empty, because nothing left
    the box — a row that recorded a delivery here would be F-03's defect inverted."""
    from datetime import UTC, datetime

    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))

    client.post(f"/protection/stop-packets/{packet.id}/discard", headers=headers)
    db.refresh(packet)

    assert packet.sent_at is None, "a discarded packet claimed a delivery"
    assert packet.shared_pack_ref is None, "a discarded packet produced a shared pack"
    assert packet.discarded_at is not None, "the decision left no timestamp"


def test_discarding_keeps_the_drivers_EVIDENCE(db, client):
    """A packet is a pointer to a stop. The BOL the driver photographed belongs to them
    and to the stop, not to the envelope they declined to post — and this is the
    assertion that would fail if `discard` were ever implemented as a delete."""
    from datetime import UTC, datetime

    PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))
    stop = loads.get_stop(db, packet.stop_ref)
    m5.capture_document(db, account_id, "bol", PNG, filename="bol.png", stop_ref=stop.id)

    client.post(f"/protection/stop-packets/{packet.id}/discard", headers=headers)

    assert m5.has_bol(db, stop.id), "discarding the packet destroyed the driver's BOL"


def test_a_later_EXIT_at_the_same_dock_does_not_resurrect_it(db, client):
    """A discard that a geofence bounce can undo is not a decision. `stop_ref` is
    uniquely constrained and drafting is get-or-create, so this is enforced by the
    schema rather than by a rule somebody has to remember — asserted because that is
    exactly the kind of guarantee a later refactor removes without noticing."""
    from datetime import UTC, datetime

    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))
    stop = loads.get_stop(db, packet.stop_ref)

    client.post(f"/protection/stop-packets/{packet.id}/discard", headers=headers)
    m5.draft_stop_packet_on_exit(
        db, account_id, stop.facility_id, datetime(2026, 8, 1, 14, tzinfo=UTC)
    )

    assert client.get("/protection/stop-packets", headers=headers).json() == []


def test_discarding_an_ALREADY_SENT_packet_does_not_rewrite_it(db, client):
    """The sharper half of idempotency. Send guards a double tap to keep a second
    document out of an inbox; this guards one to stop a row claiming the driver declined
    paperwork a dispatcher is already holding."""
    from datetime import UTC, datetime

    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))
    client.post(f"/protection/stop-packets/{packet.id}/send", headers=headers)

    resp = client.post(f"/protection/stop-packets/{packet.id}/discard", headers=headers)

    assert resp.status_code == 200, "a late tap is not an error"
    assert resp.json()["state"] == "sent", "a sent packet was rewritten as discarded"
    db.refresh(packet)
    assert packet.discarded_at is None


def test_discarding_twice_is_not_an_error(db, client):
    from datetime import UTC, datetime

    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))

    first = client.post(f"/protection/stop-packets/{packet.id}/discard", headers=headers)
    db.refresh(packet)
    stamped = packet.discarded_at
    second = client.post(f"/protection/stop-packets/{packet.id}/discard", headers=headers)
    db.refresh(packet)

    assert (first.status_code, second.status_code) == (200, 200)
    assert stamped is not None
    # the second tap must not restamp: the decision happened once, and moving the
    # timestamp would make the record disagree with when the driver actually decided.
    assert packet.discarded_at == stamped


def test_one_driver_cannot_discard_anothers_paperwork(db, client):
    """The same ownership scope Send has. Declining another driver's paperwork would
    delete a task from their queue that they never saw."""
    from datetime import UTC, datetime

    account_id, headers = _auth(client)
    packet, _ = _drafted(db, account_id, datetime(2026, 8, 1, 12, tzinfo=UTC))
    _, other = _auth(client, email="thief@example.com")

    assert client.post(
        f"/protection/stop-packets/{packet.id}/discard", headers=other
    ).status_code == 404
    assert len(client.get("/protection/stop-packets", headers=headers).json()) == 1
