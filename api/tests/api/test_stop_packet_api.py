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
