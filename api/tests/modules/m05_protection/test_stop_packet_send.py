"""AI-CONTEXT: A1 — a routine handoff document that reaches a dispatcher, and is NOT a
claim.

The amendment is explicit: the Stop Packet is "a routine handoff document, explicitly
not a claim and not a dispute", tone neutral (v1.0 §5.5). That is not decoration. The
only path a pack currently takes to a counterparty is M3's `open_receivable`, which
does two things a handoff must never do:

  · opens a RECEIVABLE in F7 — money the driver is claiming
  · calls `record_claim` on the counterparty, incrementing the claim history that
    feeds M8 pricing and M12 analytics

A broker's claim count going up because a driver sent their paperwork would be a
quiet, compounding lie about that broker — and PRD §15 names driver fear of blacklisting
as a top risk. So these tests assert the absences as hard as the presence.
"""

from datetime import UTC, datetime

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.foundation.f08_notifications import public as notify
from app.modules.m05_protection import public as m5

NOW = datetime(2026, 8, 1, 14, 0, tzinfo=UTC)


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _shipper_stop(db, account, reference_number=None):
    broker = loads.create_counterparty(
        db, "Bolt Logistics", loads.CounterpartyKind.broker, contact_email="ap@bolt.example"
    )
    load = loads.create_load(
        db, account.id, counterparty_id=broker.id, reference_number=reference_number
    )
    fac = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Dock 4", 41.88, -87.63
    )
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery)
    return broker, load, stop


def test_the_dispatcher_gets_a_link_to_the_paperwork(db):
    account = _account(db)
    broker, load, stop = _shipper_stop(db, account)
    gateway = notify.RecordingNotificationGateway()

    result = m5.send_stop_packet(
        db, account.id, stop_ref=stop.id, counterparty_ref=broker.id,
        gateway=gateway, now=NOW, base_url_required=False,
    )

    # delivery is the `outbound_mail` sweep's job now, not the request path's
    notify.retry_unsent_messages(db, gateway)
    assert gateway.sent, "nothing was sent"
    body = gateway.sent[-1].body
    assert result["shared"].token
    assert "attached" not in body.lower(), "F8 has no attachment parameter; do not claim one"


def test_it_opens_NO_receivable(db):
    account = _account(db)
    broker, load, stop = _shipper_stop(db, account)
    gateway = notify.RecordingNotificationGateway()

    m5.send_stop_packet(
        db, account.id, stop_ref=stop.id, counterparty_ref=broker.id,
        gateway=gateway, now=NOW, base_url_required=False,
    )

    assert ledger.list_receivables(db, account.id) == [], (
        "a handoff document opened a receivable — it is not a claim"
    )


def test_it_does_NOT_touch_the_counterparty_claim_history(db):
    """The quiet one. `record_claim` feeds M8 pricing and M12 analytics, and PRD §15
    names driver fear of blacklisting as a top risk. A broker's claim count rising
    because a driver sent their paperwork would be a compounding lie about that broker."""
    account = _account(db)
    broker, load, stop = _shipper_stop(db, account)
    before = broker.claim_count
    gateway = notify.RecordingNotificationGateway()

    m5.send_stop_packet(
        db, account.id, stop_ref=stop.id, counterparty_ref=broker.id,
        gateway=gateway, now=NOW, base_url_required=False,
    )

    db.refresh(broker)
    assert broker.claim_count == before


def test_the_subject_carries_the_load_reference_a_clerk_files_by(db):
    """A1 requirement 4: an accounts-payable clerk should be able to file it without
    opening it."""
    account = _account(db)
    broker, load, stop = _shipper_stop(db, account, reference_number="BL-88421")
    gateway = notify.RecordingNotificationGateway()

    m5.send_stop_packet(
        db, account.id, stop_ref=stop.id, counterparty_ref=broker.id,
        gateway=gateway, now=NOW, base_url_required=False,
    )
    # delivery is the `outbound_mail` sweep's job now, not the request path's
    notify.retry_unsent_messages(db, gateway)
    assert "BL-88421" in gateway.sent[-1].subject


def test_the_tone_is_a_handoff_not_a_demand(db):
    # v1.0 §5.5 / §12.1: relationship-preserving by default. This document exists to be
    # filed, not argued with.
    account = _account(db)
    broker, load, stop = _shipper_stop(db, account)
    gateway = notify.RecordingNotificationGateway()
    m5.send_stop_packet(
        db, account.id, stop_ref=stop.id, counterparty_ref=broker.id,
        gateway=gateway, now=NOW, base_url_required=False,
    )
    # delivery is the `outbound_mail` sweep's job now, not the request path's
    notify.retry_unsent_messages(db, gateway)
    body = gateway.sent[-1].body.lower()
    for word in ("claim", "demand", "owed", "dispute", "invoice"):
        assert word not in body, f"a handoff document should not say {word!r}"
