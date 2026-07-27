"""AI-CONTEXT: the route that lets geofence EXIT happen at all.

F3 was complete from the Foundation and had no inbound seam: in application code
`evaluate_ping` had exactly one caller, `POST /load/{stop}/arrive`, which passes the
facility's own coordinates and can therefore only ever produce an ENTER. EXIT existed
in tests and in the demo seeder and nowhere else, which quietly emptied F3's dwell
pairing (ENTER->EXIT), M2's dwell stats, and M3's departure.

These tests assert the thing that was missing, not just the thing that works: a
driver who leaves gets an EXIT.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.main import app

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _driver(client, db, email="pinger@example.com"):
    reg = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    account = db.get(identity.Account, uuid.UUID(reg.json()["account_id"]))
    return account, headers


def _armed_facility(db, account):
    fac = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Ping Dock", *DALLAS
    )
    location.arm_geofence(db, account.id, fac.id)
    return fac


def test_ping_requires_a_session(client):
    resp = client.post("/location/ping", json={"lat": DALLAS[0], "lon": DALLAS[1]})
    assert resp.status_code in (401, 403)


def test_ping_inside_an_armed_facility_emits_enter(client, db):
    account, headers = _driver(client, db)
    fac = _armed_facility(db, account)

    resp = client.post(
        "/location/ping", json={"lat": DALLAS[0], "lon": DALLAS[1]}, headers=headers
    )

    assert resp.status_code == 201
    events = resp.json()["events"]
    assert [e["event_type"] for e in events] == ["ENTER"]
    assert events[0]["facility_id"] == str(fac.id)
    assert location.is_present(db, account.id, fac.id) is True


def test_leaving_emits_exit_which_production_could_never_do(client, db):
    """The whole point. Before this route existed there was no path in the running
    application that could produce an EXIT — `/load/{stop}/arrive` passes the
    facility's own coordinates, so it can only ever land inside."""
    account, headers = _driver(client, db)
    fac = _armed_facility(db, account)

    client.post("/location/ping", json={"lat": DALLAS[0], "lon": DALLAS[1]}, headers=headers)
    resp = client.post("/location/ping", json={"lat": FAR[0], "lon": FAR[1]}, headers=headers)

    assert [e["event_type"] for e in resp.json()["events"]] == ["EXIT"]
    assert location.is_present(db, account.id, fac.id) is False

    # and the pair is now a dwell sample, which is what M2's dwell stats read. This
    # list was empty in production for every real stop ever made.
    assert location.dwell_samples(db, fac.id) != []


def test_server_time_is_authoritative_and_client_skew_is_recorded(client, db):
    """PRD §7.3: server time is authoritative; the client's clock is measured, not
    trusted. A device ten minutes behind does not get to backdate its arrival."""
    account, headers = _driver(client, db)
    _armed_facility(db, account)
    behind = datetime.now(UTC) - timedelta(minutes=10)

    resp = client.post(
        "/location/ping",
        json={"lat": DALLAS[0], "lon": DALLAS[1], "client_time": behind.isoformat()},
        headers=headers,
    )

    body = resp.json()
    assert body["client_skew_ms"] < -9 * 60 * 1000  # roughly ten minutes behind
    # the EVENT still happened now, not ten minutes ago
    recorded = datetime.fromisoformat(body["recorded_at"])
    assert abs((recorded - datetime.now(UTC)).total_seconds()) < 60


def test_a_ping_outside_every_armed_facility_is_still_recorded(client, db):
    """A trace point is worth keeping even when it crosses no boundary — F3 stores the
    trace, and M9's IFTA mileage reads it."""
    account, headers = _driver(client, db)
    _armed_facility(db, account)

    resp = client.post("/location/ping", json={"lat": FAR[0], "lon": FAR[1]}, headers=headers)

    assert resp.status_code == 201
    assert resp.json()["events"] == []
    assert location.last_known_position(db, account.id, timedelta(minutes=5)) is not None


def test_unknown_sampling_mode_does_not_cost_the_fix(client, db):
    """An unrecognised mode is not worth refusing a position over — dropping it would
    lose an arrival to a typo."""
    account, headers = _driver(client, db)
    _armed_facility(db, account)

    resp = client.post(
        "/location/ping",
        json={"lat": DALLAS[0], "lon": DALLAS[1], "mode": "not_a_mode"},
        headers=headers,
    )

    assert resp.status_code == 201
    assert [e["event_type"] for e in resp.json()["events"]] == ["ENTER"]


def test_high_accuracy_mode_is_carried_onto_the_trace(client, db):
    account, headers = _driver(client, db)
    _armed_facility(db, account)

    client.post(
        "/location/ping",
        json={
            "lat": DALLAS[0],
            "lon": DALLAS[1],
            "mode": "high_accuracy",
            "accuracy_m": 4.5,
            "speed_mps": 0.0,
        },
        headers=headers,
    )

    ping = db.scalars(
        select(location.LocationPing)
        .where(location.LocationPing.account_id == account.id)
        .order_by(location.LocationPing.occurred_at.desc())
    ).first()
    assert ping.mode == location.LocationMode.high_accuracy
    assert ping.accuracy_m == 4.5
