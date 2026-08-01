"""AI-CONTEXT: A1 requirement 5 — "The driver reviews before it sends. Nothing leaves
silently. A packet the driver did not see is a document they cannot vouch for."

That sentence is the whole design of this piece. The obvious build — EXIT fires, packet
sends — is the one A1 forbids, and it forbids it for a reason the rest of the product
agrees with: every counterparty artifact in this codebase is something the driver
approved (M3-FR6 "driver approves before send", M11-FR3's ghostwriter, M5-FR1's per-load
opt-in). A document going to a broker under a driver's name, describing a stop the driver
has not looked at, is the one thing none of those would allow.

So EXIT DRAFTS. Sending is a separate act by a person.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
from app.modules.m05_protection import public as m5

T0 = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
DOCK = (41.8781, -87.6298)


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _stop(db, account, kind=None):
    broker = loads.create_counterparty(
        db, "Bolt Logistics", loads.CounterpartyKind.broker, contact_email="ap@bolt.example"
    )
    load = loads.create_load(db, account.id, counterparty_id=broker.id, reference_number="BL-1")
    fac = facility.create_facility(
        db, kind or facility.FacilityType.shipper_receiver, "Dock 4", *DOCK
    )
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery)
    # F3 only emits geofence events for ARMED facilities, so an unarmed stop could
    # never reach this path in production — arming it is what makes the test real
    loads.arm_stop(db, stop)
    return broker, load, stop, fac


def test_leaving_a_dock_DRAFTS_a_packet_and_sends_nothing(db):
    """The requirement, stated as a test: nothing leaves silently."""
    account = _account(db)
    broker, load, stop, fac = _stop(db, account)
    gateway = notify.RecordingNotificationGateway()

    packet = m5.draft_stop_packet_on_exit(db, account.id, fac.id, T0 + timedelta(hours=2))

    assert packet is not None
    assert packet.state is m5.StopPacketState.draft
    assert gateway.sent == [], "a packet left before the driver saw it"


def test_leaving_a_TRUCK_STOP_drafts_nothing(db):
    # A1 scopes this to `shipper_receiver`. A driver leaving a Pilot has no paperwork
    # to hand anyone, and a draft per fuel stop would train them to ignore the queue.
    account = _account(db)
    broker, load, stop, fac = _stop(db, account, kind=facility.FacilityType.truck_stop)
    assert m5.draft_stop_packet_on_exit(db, account.id, fac.id, T0) is None


def test_a_second_exit_does_not_draft_a_second_packet(db):
    """Geofences bounce. Two drafts for one stop is two documents a driver has to
    reject, and the second one teaches them the queue is noise."""
    account = _account(db)
    broker, load, stop, fac = _stop(db, account)
    first = m5.draft_stop_packet_on_exit(db, account.id, fac.id, T0)
    second = m5.draft_stop_packet_on_exit(db, account.id, fac.id, T0 + timedelta(minutes=3))
    assert second is not None
    assert second.id == first.id


def test_only_the_driver_sending_it_puts_it_on_the_wire(db):
    account = _account(db)
    broker, load, stop, fac = _stop(db, account)
    gateway = notify.RecordingNotificationGateway()
    packet = m5.draft_stop_packet_on_exit(db, account.id, fac.id, T0)

    sent = m5.send_drafted_packet(db, packet, gateway=gateway, now=T0, base_url_required=False)

    assert sent.state is m5.StopPacketState.sent
    assert len(gateway.sent) == 1
    assert "BL-1" in gateway.sent[0].subject


def test_a_packet_cannot_be_sent_twice(db):
    # the driver taps send, the request retries, the broker gets two documents
    account = _account(db)
    broker, load, stop, fac = _stop(db, account)
    gateway = notify.RecordingNotificationGateway()
    packet = m5.draft_stop_packet_on_exit(db, account.id, fac.id, T0)
    m5.send_drafted_packet(db, packet, gateway=gateway, now=T0, base_url_required=False)
    m5.send_drafted_packet(db, packet, gateway=gateway, now=T0, base_url_required=False)
    assert len(gateway.sent) == 1


def test_the_template_says_what_this_document_IS(db):
    """§23's reasoning for `incident`: the template picks the title, which is the first
    line a clerk reads. A handoff announcing itself as a "Stop record" — an export the
    DRIVER reaches — is wrong on the one line whose whole job is to say what this is."""
    from app.foundation.f04_evidence import public as evidence

    assert evidence.PackTemplate.stop_packet
    assert "packet" in evidence.template_title(evidence.PackTemplate.stop_packet).lower()
