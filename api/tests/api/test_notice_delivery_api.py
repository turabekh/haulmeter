"""Finding F5 over HTTP — what the route asserts when the send FAILS.

Every other notice test in this suite runs against the recording gateway, which always
succeeds — so `message is not None` and `message.sent_at is not None` agree, and the
defect is invisible to all of them. That is precisely how it shipped. These tests make
the gateway fail, which is the only condition under which the two differ.
"""


import pytest
from fastapi.testclient import TestClient

from app.api import load as load_api
from app.api.deps import get_db
from app.foundation.f08_notifications import public as notify
from app.main import app

DALLAS = (32.7767, -96.7970)


class FailingGateway:
    """A gateway may never fail its caller — it returns the outcome as the ref (F-06)."""

    def __init__(self, kind="SMTPServerDisconnected"):
        self.kind = kind
        self.sent = []

    def send_email(self, to_ref, subject, body):
        self.sent.append(to_ref)
        return f"smtp-failed-{self.kind}"


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client):
    reg = client.post("/auth/register", json={"email": "oo@example.com", "password": "pw-123456"})
    return {"Authorization": f"Bearer {reg.json()['token']}"}


def _arrived_stop(client, headers, db, email="ap@broker.example"):
    body = {
        "facility_name": "Dock",
        "lat": DALLAS[0],
        "lon": DALLAS[1],
        "counterparty": "Broker",
        "free_time_minutes": 0,  # accrues immediately, so a notice is due
    }
    if email is not None:
        body["counterparty_email"] = email
    stop_id = client.post("/load", json=body, headers=headers).json()["stop_id"]
    client.post(f"/load/{stop_id}/arrive", headers=headers)
    return stop_id


def _timeline(client, headers, stop_id):
    body = client.get(f"/load/{stop_id}/evidence", headers=headers).json()
    return [e["event"] for e in body["timeline"]]


def test_a_failed_send_is_not_reported_as_sent(client, db, monkeypatch):
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)
    gateway = FailingGateway()
    monkeypatch.setattr(load_api, "_GATEWAY", gateway)

    resp = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert gateway.sent == ["ap@broker.example"]  # it was attempted, at a real address
    assert resp.json()["sent"] is False
    assert resp.json()["delivery"] == "retrying"


def test_a_failed_send_puts_nothing_in_the_evidence_log(client, db, monkeypatch):
    """The one that matters most: this record goes into the legal pack.

    "We notified the broker at 10:05" is the fact a detention dispute turns on, and it was
    being appended to the hash-chained log for mail that never left the box. The chain is
    append-only, so a log this has polluted stays polluted.
    """
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)
    monkeypatch.setattr(load_api, "_GATEWAY", FailingGateway())

    client.post(f"/load/{stop_id}/notice", headers=headers)

    assert "notice_sent" not in _timeline(client, headers, stop_id)


def test_a_failed_send_leaves_the_meter_saying_the_broker_was_not_notified(
    client, db, monkeypatch
):
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)
    monkeypatch.setattr(load_api, "_GATEWAY", FailingGateway())

    client.post(f"/load/{stop_id}/notice", headers=headers)
    meter = client.get(f"/load/{stop_id}/meter", headers=headers).json()

    assert meter["notice_sent"] is False
    assert meter["notice_delivery"] == "retrying"


def test_the_retry_sweep_turns_it_into_sent_on_the_meter(client, db, monkeypatch):
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)
    monkeypatch.setattr(load_api, "_GATEWAY", FailingGateway())
    client.post(f"/load/{stop_id}/notice", headers=headers)

    notify.retry_unsent_messages(db, notify.RecordingNotificationGateway())
    meter = client.get(f"/load/{stop_id}/meter", headers=headers).json()

    assert meter["notice_delivery"] == "sent"
    # ...and the evidence pack still does not claim it. Understating is the correct
    # direction for a legal document; see `notice_delivery`'s note.
    assert "notice_sent" not in _timeline(client, headers, stop_id)


def test_a_load_with_no_broker_email_sends_nothing_and_says_why(client, db, monkeypatch):
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db, email=None)
    gateway = FailingGateway()
    monkeypatch.setattr(load_api, "_GATEWAY", gateway)

    resp = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert gateway.sent == []  # no address, so the gateway is never reached
    assert resp.json()["sent"] is False
    assert resp.json()["delivery"] == "no_email"
    assert "notice_sent" not in _timeline(client, headers, stop_id)


def test_tapping_send_twice_while_retrying_does_not_queue_a_second_notice(
    client, db, monkeypatch
):
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)
    gateway = FailingGateway()
    monkeypatch.setattr(load_api, "_GATEWAY", gateway)

    client.post(f"/load/{stop_id}/notice", headers=headers)
    second = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert len(gateway.sent) == 1
    assert second.json()["delivery"] == "retrying"
    assert len(notify.unsent_messages(db)) == 1


def test_a_successful_send_still_records_the_moment(client, db):
    """The other half: the fix must not have made `notice_sent` unreachable."""
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)

    resp = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert resp.json() == {"sent": True, "delivery": "sent"}
    assert "notice_sent" in _timeline(client, headers, stop_id)
