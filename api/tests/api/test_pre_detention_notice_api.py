"""Finding F7 — the broker's "free time is nearly up" warning, finally wired.

`send_pre_detention_notice` was written, exported, unit-tested and called by NOTHING. The
DRIVER's 30-minute warning has been wired since §23 entry 106; the broker's half of the
same moment never was — so the one notice that can still change the outcome, a dock that
hurries when told the clock is about to start, was never sent by this product.

The boundaries are the content: 31 minutes is too early, 29 is the warning, and past
expiry is the start notice, which must be untouched by any of this.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.main import app
from app.modules.m03_detention import public as m3

DALLAS = (32.7767, -96.7970)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _driver(client, db, email="oo@example.com", authority=identity.AuthorityType.own_mc):
    import uuid

    reg = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    account = db.get(identity.Account, uuid.UUID(reg.json()["account_id"]))
    identity.upsert_driver_profile(db, account, authority_type=authority)
    return account, {"Authorization": f"Bearer {reg.json()['token']}"}


def _stop_with_free_time_left(db, account, minutes_left):
    """Arrived `120 - minutes_left` minutes ago against a two-hour free window."""
    arrival = datetime.now(UTC) - timedelta(minutes=120 - minutes_left)
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    broker = loads.create_counterparty(
        db, "Acme", loads.CounterpartyKind.broker, contact_email="ap@acme.com"
    )
    load = loads.create_load(
        db, account.id, counterparty_id=broker.id,
        detention_rate_cents_per_hour=7500, free_time_minutes=120,
    )
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery, appointment_start=arrival)
    claim = m3.start_claim(db, stop, started_at=arrival - timedelta(minutes=1))
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=arrival)
    db.flush()
    return stop, claim


def test_thirty_one_minutes_out_is_still_too_early(client, db):
    account, headers = _driver(client, db)
    stop, claim = _stop_with_free_time_left(db, account, minutes_left=31)

    resp = client.post(f"/load/{stop.id}/notice", headers=headers)

    assert resp.json()["sent"] is False
    assert claim.pre_notice_sent_at is None
    assert claim.start_notice_sent_at is None


def test_twenty_nine_minutes_out_warns_the_broker(client, db, flush_outbox):
    account, headers = _driver(client, db)
    stop, claim = _stop_with_free_time_left(db, account, minutes_left=29)

    resp = client.post(f"/load/{stop.id}/notice", headers=headers)

    # AI-CONTEXT: `sent` is False at the POST because sending is asynchronous — it means
    # the broker was REACHED, and nothing has left the box yet. `pre_notice_sent_at`
    # below is a different fact and is unaffected: it means "we decided to warn, once",
    # which is exactly what has happened.
    assert resp.json()["sent"] is False
    assert resp.json()["delivery"] == "queued"
    assert resp.json()["phase"] == "warning"
    flush_outbox()
    assert claim.pre_notice_sent_at is not None
    # the WARNING is not the START. `start_notice_sent_at` means the broker was told the
    # clock had begun, and it has not.
    assert claim.start_notice_sent_at is None


def test_the_warning_leaves_the_evidence_chain_alone(client, db):
    """`notice_sent` means "the broker was told the clock STARTED" — a different fact."""
    account, headers = _driver(client, db)
    stop, _ = _stop_with_free_time_left(db, account, minutes_left=29)

    client.post(f"/load/{stop.id}/notice", headers=headers)
    timeline = client.get(f"/load/{stop.id}/evidence", headers=headers).json()["timeline"]

    assert "notice_sent" not in [e["event"] for e in timeline]


def test_the_warning_goes_out_once(client, db):
    account, headers = _driver(client, db)
    stop, claim = _stop_with_free_time_left(db, account, minutes_left=29)

    first = client.post(f"/load/{stop.id}/notice", headers=headers)
    second = client.post(f"/load/{stop.id}/notice", headers=headers)

    assert first.json()["phase"] == "warning"
    # the window is half an hour long and the driver may tap again inside it; the second
    # tap must not put a second warning in the broker's inbox
    assert second.json()["sent"] is False
    assert second.json()["phase"] == "start"


def test_past_expiry_it_is_the_start_notice_exactly_as_before(client, db, flush_outbox):
    account, headers = _driver(client, db)
    stop, claim = _stop_with_free_time_left(db, account, minutes_left=-10)  # 10 min over

    resp = client.post(f"/load/{stop.id}/notice", headers=headers)
    assert resp.json() == {"sent": False, "delivery": "queued", "phase": "start"}

    flush_outbox()
    timeline = client.get(f"/load/{stop.id}/evidence", headers=headers).json()["timeline"]

    assert claim.start_notice_sent_at is not None
    assert claim.pre_notice_sent_at is None
    assert "notice_sent" in [e["event"] for e in timeline]


def test_a_warned_stop_still_sends_its_start_notice_when_the_clock_turns(
    client, db, flush_outbox
):
    """The chain is untouched by the warning: both notices, in order, one each."""
    account, headers = _driver(client, db)
    stop, claim = _stop_with_free_time_left(db, account, minutes_left=29)
    client.post(f"/load/{stop.id}/notice", headers=headers)

    # the clock rolls past free time — re-anchor the claim rather than sleep 29 minutes
    claim.free_time_minutes = 0
    db.flush()
    resp = client.post(f"/load/{stop.id}/notice", headers=headers)
    flush_outbox()

    assert resp.json()["phase"] == "start"
    assert resp.json()["delivery"] == "queued"
    assert claim.pre_notice_sent_at is not None
    assert claim.start_notice_sent_at is not None, "the reconcile stamps it once it goes"


def test_a_company_driver_is_unchanged_by_any_of_this(client, db):
    """Evidence-only mode bills nobody; the notice path is the same for both modes."""
    account, headers = _driver(client, db, authority=identity.AuthorityType.company)
    stop, claim = _stop_with_free_time_left(db, account, minutes_left=29)

    resp = client.post(f"/load/{stop.id}/notice", headers=headers)

    assert claim.mode == m3.ClaimMode.evidence_only
    assert resp.json()["phase"] == "warning"
    assert claim.start_notice_sent_at is None
