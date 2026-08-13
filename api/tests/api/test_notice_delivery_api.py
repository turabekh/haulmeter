"""Finding F5 over HTTP — what the route asserts when the send FAILS.

Every other notice test in this suite runs against the recording gateway, which always
succeeds — so `message is not None` and `message.sent_at is not None` agree, and the
defect is invisible to all of them. That is precisely how it shipped. These tests make
the gateway fail, which is the only condition under which the two differ.

AI-CONTEXT: sending is ASYNCHRONOUS now, so the route no longer knows the outcome and
these tests read in two beats: the POST records, `flush_outbox` delivers. The gateway is
handed to the SWEEP rather than patched onto the route module, because that is where the
transport now lives — patching `load_api._GATEWAY` would patch something nothing calls,
which is the shape of test this codebase keeps finding (a stub the code under test never
consults).
"""


import pytest
from fastapi.testclient import TestClient

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


def test_the_route_reports_queued_rather_than_guessing(client, db):
    """The route cannot say `sent` any more, and must not say `failed` either."""
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)

    resp = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert resp.json()["sent"] is False, "nothing has left the box yet"
    assert resp.json()["delivery"] == "queued"


def test_a_failed_send_is_not_reported_as_sent(client, db, flush_outbox):
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)
    gateway = FailingGateway()

    client.post(f"/load/{stop_id}/notice", headers=headers)
    flush_outbox(gateway)

    assert gateway.sent == ["ap@broker.example"]  # it was attempted, at a real address
    meter = client.get(f"/load/{stop_id}/meter", headers=headers).json()
    assert meter["notice_sent"] is False
    assert meter["notice_delivery"] == "retrying"


def test_a_failed_send_puts_nothing_in_the_evidence_log(client, db, flush_outbox):
    """The one that matters most: this record goes into the legal pack.

    "We notified the broker at 10:05" is the fact a detention dispute turns on, and it was
    being appended to the hash-chained log for mail that never left the box. The chain is
    append-only, so a log this has polluted stays polluted.
    """
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)

    client.post(f"/load/{stop_id}/notice", headers=headers)
    flush_outbox(FailingGateway())

    assert "notice_sent" not in _timeline(client, headers, stop_id)


def test_a_failed_send_leaves_the_meter_saying_the_broker_was_not_notified(
    client, db, flush_outbox
):
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)

    client.post(f"/load/{stop_id}/notice", headers=headers)
    flush_outbox(FailingGateway())
    meter = client.get(f"/load/{stop_id}/meter", headers=headers).json()

    assert meter["notice_sent"] is False
    assert meter["notice_delivery"] == "retrying"


def test_the_sweep_turns_it_into_sent_on_the_meter_AND_writes_the_evidence(
    client, db, flush_outbox
):
    """AI-CONTEXT: the second assertion is INVERTED from what it used to be, deliberately.

    It read `"notice_sent" not in timeline` and called that "the correct direction for a
    legal document" — a pack that understates costs the driver an argument, one that
    overstates costs them the claim. True, and tolerable while the sweep only caught the
    rare failure.

    Asynchronous sending makes the sweep the ONLY path, so understating would become
    universal: no detention pack would ever again say the broker was told. The asymmetry
    is closed by `reconcile_delivered_notices`, and this is the test that says so.
    """
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)
    client.post(f"/load/{stop_id}/notice", headers=headers)
    flush_outbox(FailingGateway())

    flush_outbox(notify.RecordingNotificationGateway())
    meter = client.get(f"/load/{stop_id}/meter", headers=headers).json()

    assert meter["notice_delivery"] == "sent"
    assert meter["notice_sent"] is True
    assert "notice_sent" in _timeline(client, headers, stop_id)


def test_a_load_with_no_broker_email_sends_nothing_and_says_why(client, db, flush_outbox):
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db, email=None)
    gateway = FailingGateway()

    resp = client.post(f"/load/{stop_id}/notice", headers=headers)
    flush_outbox(gateway)

    assert gateway.sent == []  # no address, so no row exists to deliver
    assert resp.json()["sent"] is False
    assert resp.json()["delivery"] == "no_email"
    assert "notice_sent" not in _timeline(client, headers, stop_id)


def test_tapping_send_twice_while_QUEUED_does_not_queue_a_second_notice(client, db):
    """AI-CONTEXT: the window widened from one round trip to a whole sweep interval.

    §23 entry 136 fixed a double-send at the UI, where `onSendNotice` had no in-flight
    guard and "genuinely sent a broker two emails on a double tap". That guard covered the
    request. A QUEUED notice stays un-sent for up to a minute, and a replayed offline
    write reaches straight past any client-side guard — so the refusal has to live in
    `_existing_start_notice`, which now treats a never-attempted row as an existing one.
    """
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)

    client.post(f"/load/{stop_id}/notice", headers=headers)
    second = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert second.json()["delivery"] == "queued"
    assert len(notify.unsent_messages(db)) == 1, "one stop, one notice"


def test_tapping_send_twice_while_retrying_does_not_queue_a_second_notice(
    client, db, flush_outbox
):
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)
    gateway = FailingGateway()

    client.post(f"/load/{stop_id}/notice", headers=headers)
    flush_outbox(gateway)
    second = client.post(f"/load/{stop_id}/notice", headers=headers)

    assert len(gateway.sent) == 1
    assert second.json()["delivery"] == "retrying"
    assert len(notify.unsent_messages(db)) == 1


def test_a_successful_send_still_records_the_moment(client, db, flush_outbox):
    """The other half: the fix must not have made `notice_sent` unreachable."""
    headers = _auth(client)
    stop_id = _arrived_stop(client, headers, db)

    resp = client.post(f"/load/{stop_id}/notice", headers=headers)
    flush_outbox()

    # `already_sent` is what stops the control being dead: a notice the broker already
    # has returns the existing message, and without this the route reported exactly what
    # a real send reports. `forced` echoes the driver's deliberate override.
    assert resp.json() == {
        "sent": False,
        "delivery": "queued",
        "phase": "start",
        "already_sent": False,
        "forced": False,
    }
    meter = client.get(f"/load/{stop_id}/meter", headers=headers).json()
    assert meter["notice_delivery"] == "sent"
    assert "notice_sent" in _timeline(client, headers, stop_id)
