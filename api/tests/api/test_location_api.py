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
from datetime import time as dt_time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f06_documents import public as documents
from app.foundation.f08_notifications import public as notify
from app.main import app
from app.modules.m05_protection import public as m5

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
# AI-CONTEXT: a FIXED daytime instant, because §13.3's default quiet hours are
# 22:00-06:00 and `datetime.now()` walks into them for a third of the day. The first
# run of these tests was at 04:00 UTC and every dispatch came back `quiet_hours` —
# the same shape as the m13 flake in HANDOFF-091: a clock the test does not control
# is a clock the test is at the mercy of.
NOON = datetime(2026, 7, 27, 15, 0, tzinfo=UTC)


def _awake(db, account):
    """Disable quiet hours for this account outright.

    AI-CONTEXT: this used to move the window to 02:00-03:00 and call that "somewhere
    this test is not" — which was true when it was written and false at 02:03 UTC the
    next morning, when two EXIT tests failed for an hour. That is the SAME defect the
    fixed `NOON` constant was meant to end, one layer down: a window chosen against a
    clock the test does not control is still at that clock's mercy.

    `in_quiet_hours` compares `start <= local < end`, so an empty window can never
    contain anything. No hour of the day can walk into it."""
    prefs = notify.get_or_create_prefs(db, account.id)
    prefs.quiet_start = dt_time(3, 0)
    prefs.quiet_end = dt_time(3, 0)
    db.flush()
    return prefs


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


def test_every_ping_reports_presence_as_a_state_not_only_an_edge(client, db):
    """§5's ON_SITE input, which the client could never hold onto.

    `events` fires once, on the crossing. A client that learns presence only from an
    edge knows it is on site until the tab reloads and then never again, because the
    ENTER it depended on has already been and gone — which is how every ON_SITE
    behaviour in the product came to be unreachable while looking correct. The second
    ping below carries NO events and must still say the truck is at the dock.
    """
    account, headers = _driver(client, db)
    _armed_facility(db, account)

    first = client.post(
        "/location/ping", json={"lat": DALLAS[0], "lon": DALLAS[1]}, headers=headers
    ).json()
    assert [e["event_type"] for e in first["events"]] == ["ENTER"]
    assert first["present"] is True

    # the driver has not moved: no crossing, nothing in `events`, still at the dock
    second = client.post(
        "/location/ping", json={"lat": DALLAS[0], "lon": DALLAS[1]}, headers=headers
    ).json()
    assert second["events"] == []
    assert second["present"] is True, "presence must outlive the edge that announced it"

    left = client.post(
        "/location/ping", json={"lat": FAR[0], "lon": FAR[1]}, headers=headers
    ).json()
    assert left["present"] is False


def test_presence_is_answered_for_a_driver_who_never_crossed_a_geofence(client, db):
    """A driver parked outside every armed facility is not on site, and the honest
    answer is False rather than the absence of a field."""
    account, headers = _driver(client, db)
    _armed_facility(db, account)

    body = client.post(
        "/location/ping", json={"lat": FAR[0], "lon": FAR[1]}, headers=headers
    ).json()

    assert body["present"] is False


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


class TestExitCarveOut:
    """M5-FR5's EXIT carve-out (§23 entry 56).

    An irrecoverable gap at a state transition is a deadline, not a nag: once the
    driver has pulled off the dock they cannot photograph that trailer at that
    facility, ever. Three sessions of handoffs deferred this because its precondition
    — a geofence EXIT that actually fires — did not exist until this session.
    """

    def _armed_stop(self, db, account, fac):
        cp = loads.create_counterparty(db, "Coyote", loads.CounterpartyKind.broker)
        load = loads.create_load(db, account.id, counterparty_id=cp.id)
        stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery)
        loads.arm_stop(db, stop)
        return stop

    def test_leaving_with_no_bol_warns_the_driver(self, client, db):
        account, headers = _driver(client, db)
        _awake(db, account)
        fac = _armed_facility(db, account)
        stop = self._armed_stop(db, account, fac)

        client.post("/location/ping", json={"lat": DALLAS[0], "lon": DALLAS[1]}, headers=headers)
        client.post("/location/ping", json={"lat": FAR[0], "lon": FAR[1]}, headers=headers)

        sent = db.scalars(
            select(notify.Notification).where(
                notify.Notification.account_id == account.id,
                notify.Notification.category == notify.PROTECTION_GAP_CLASS,
            )
        ).all()
        assert len(sent) == 1
        assert sent[0].status == notify.NotificationStatus.sent
        assert "BOL" in sent[0].title
        # §13.5: deep-links to the exact screen, never a tab root
        assert sent[0].deep_link == f"/load/{stop.id}/evidence"

    def test_a_documented_stop_is_not_nudged(self, client, db):
        """The whole point of a budget is that we only interrupt for something. A stop
        whose recoverable evidence is complete must produce silence."""
        account, headers = _driver(client, db)
        _awake(db, account)
        fac = _armed_facility(db, account)
        stop = self._armed_stop(db, account, fac)
        assert m5.irrecoverable_gaps(db, stop) != []  # nothing captured yet

        documents.store_document(
            db, account.id, documents.DocType.bol, b"scan", filename="bol.jpg",
            subject_kind="stop", subject_ref=stop.id,
        )
        for phase in (m5.CapturePhase.pickup, m5.CapturePhase.delivery):
            capture = m5.start_condition_capture(db, stop, account.id, phase)
            m5.add_condition_photo(db, capture, "trailer_corner", content_hash="h" * 64)

        assert m5.irrecoverable_gaps(db, stop) == []

        client.post("/location/ping", json={"lat": DALLAS[0], "lon": DALLAS[1]}, headers=headers)
        client.post("/location/ping", json={"lat": FAR[0], "lon": FAR[1]}, headers=headers)

        assert (
            db.scalar(
                select(notify.Notification).where(
                    notify.Notification.category == notify.PROTECTION_GAP_CLASS
                )
            )
            is None
        )

    def test_on_time_proof_is_not_treated_as_irrecoverable(self, client, db):
        """F5 files on-time proof from the arrival record at `/arrive`, so driving away
        changes nothing about it. Warning about it here would be the nag §13.1 exists
        to prevent."""
        account, headers = _driver(client, db)
        fac = _armed_facility(db, account)
        stop = self._armed_stop(db, account, fac)

        assert "on_time_proof" in m5.protection_summary(db, stop)["missing"]
        assert "on_time_proof" not in m5.irrecoverable_gaps(db, stop)

    def test_the_deadline_survives_a_spent_budget(self, client, db):
        """The carve-out itself. A driver who already had their two ordinary nudges
        today must still be told that evidence just became uncapturable."""
        account, headers = _driver(client, db)
        _awake(db, account)
        fac = _armed_facility(db, account)
        self._armed_stop(db, account, fac)
        gateway = notify.RecordingNotificationGateway()
        now = NOON
        for i in range(notify.MAX_UNPROMPTED_P1_PER_DAY):
            notify.dispatch(
                db, account.id, notify.NotificationTier.P1, "free_time",
                f"ordinary {i}", "body", "/load", gateway, now=now,
            )
        assert notify.p1_budget_used(db, account.id, now) >= notify.MAX_UNPROMPTED_P1_PER_DAY

        client.post("/location/ping", json={"lat": DALLAS[0], "lon": DALLAS[1]}, headers=headers)
        client.post("/location/ping", json={"lat": FAR[0], "lon": FAR[1]}, headers=headers)

        gap = db.scalar(
            select(notify.Notification).where(
                notify.Notification.category == notify.PROTECTION_GAP_CLASS
            )
        )
        assert gap.status == notify.NotificationStatus.sent

    def test_the_deadline_does_not_spend_the_ordinary_budget(self, db):
        """Both halves of 'exempt'. A class that skipped the check but still consumed a
        slot would take one of the driver's two ordinary nudges to pay for itself."""
        account = identity.register_account(db, "budget@example.com", "pw-123456")
        gateway = notify.RecordingNotificationGateway()
        now = NOON

        notify.dispatch(
            db, account.id, notify.NotificationTier.P1, notify.PROTECTION_GAP_CLASS,
            "Missing: BOL", "body", "/load/x/evidence", gateway, now=now,
        )

        assert notify.p1_budget_used(db, account.id, now) == 0

    def test_quiet_hours_still_apply(self, db):
        """Exempt from the BUDGET is not exempt from the driver's sleep (§13.3)."""
        account = identity.register_account(db, "quiet@example.com", "pw-123456")
        gateway = notify.RecordingNotificationGateway()
        night = NOON.replace(hour=23)  # inside the default 22:00-06:00 window

        out = notify.dispatch(
            db, account.id, notify.NotificationTier.P1, notify.PROTECTION_GAP_CLASS,
            "Missing: BOL", "body", "/load/x/evidence", gateway, now=night,
        )

        assert out.status == notify.NotificationStatus.suppressed
        assert out.suppress_reason == notify.SuppressReason.quiet_hours

    def test_at_most_one_a_day(self, db):
        """Capped at one: a driver bouncing in and out of a geofence on a bad GPS day
        must not be told four times."""
        account = identity.register_account(db, "capped@example.com", "pw-123456")
        gateway = notify.RecordingNotificationGateway()
        now = NOON

        first = notify.dispatch(
            db, account.id, notify.NotificationTier.P1, notify.PROTECTION_GAP_CLASS,
            "Missing: BOL", "body", "/load/x/evidence", gateway, now=now,
        )
        second = notify.dispatch(
            db, account.id, notify.NotificationTier.P1, notify.PROTECTION_GAP_CLASS,
            "Missing: BOL", "body", "/load/x/evidence", gateway, now=now,
        )

        assert first.status == notify.NotificationStatus.sent
        assert second.status == notify.NotificationStatus.suppressed
        assert second.suppress_reason == notify.SuppressReason.budget

    def test_leaving_a_facility_that_is_not_the_stop_says_nothing(self, client, db):
        """An EXIT from a truck stop the driver happened to be armed at is not a
        delivery, and M5 has nothing to say about it."""
        account, headers = _driver(client, db)
        _awake(db, account)
        elsewhere = facility.create_facility(
            db, facility.FacilityType.truck_stop, "Not The Dock", *DALLAS
        )
        location.arm_geofence(db, account.id, elsewhere.id)

        client.post("/location/ping", json={"lat": DALLAS[0], "lon": DALLAS[1]}, headers=headers)
        client.post("/location/ping", json={"lat": FAR[0], "lon": FAR[1]}, headers=headers)

        assert (
            db.scalar(
                select(notify.Notification).where(
                    notify.Notification.category == notify.PROTECTION_GAP_CLASS
                )
            )
            is None
        )


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


class TestGeocode:
    """F2 grew a geocoder because a parsed address had nowhere to go (§23 entry 67).

    The transport is monkeypatched at the module seam — the same one F9 uses — so this
    never reaches the network. A geocoder test that calls Mapbox is a test that fails
    on a train.
    """

    def test_an_address_becomes_coordinates_with_the_geocoder_s_own_wording(
        self, client, db, monkeypatch
    ):
        from app.foundation.f02_facility.domain import geocode as geo

        monkeypatch.setattr(geo.get_settings(), "mapbox_token", "pk.test", raising=False)
        monkeypatch.setattr(
            geo,
            "_mapbox_forward",
            lambda q, token, limit: {
                "features": [
                    {
                        "properties": {
                            "full_address": "8450 Lakeside Ave, Columbus, OH 43228",
                            "coordinates": {"latitude": 39.9612, "longitude": -83.0907},
                        }
                    }
                ]
            },
        )
        _account, headers = _driver(client, db, "geo@example.com")

        resp = client.post(
            "/location/geocode",
            json={"address": "8450 Lakeside Ave, Columbus OH"},
            headers=headers,
        )

        assert resp.status_code == 200
        place = resp.json()["places"][0]
        assert place["lat"] == 39.9612
        assert place["lon"] == -83.0907
        # the geocoder's wording, not the driver's — so the screen can show what it
        # matched instead of asserting the driver's typing was understood (§11.7)
        assert place["label"] == "8450 Lakeside Ave, Columbus, OH 43228"

    def test_an_address_it_cannot_place_is_a_fact_not_an_error(self, client, db, monkeypatch):
        from app.foundation.f02_facility.domain import geocode as geo

        monkeypatch.setattr(geo.get_settings(), "mapbox_token", "pk.test", raising=False)
        monkeypatch.setattr(geo, "_mapbox_forward", lambda q, token, limit: {"features": []})
        _account, headers = _driver(client, db, "geo-none@example.com")

        resp = client.post("/location/geocode", json={"address": "nowhere at all"}, headers=headers)

        assert resp.status_code == 200
        assert resp.json()["places"] == []

    def test_a_dead_geocoder_never_costs_the_driver_their_rate_con(
        self, client, db, monkeypatch
    ):
        from app.foundation.f02_facility.domain import geocode as geo

        def boom(*_a, **_k):
            raise RuntimeError("mapbox is down")

        monkeypatch.setattr(geo.get_settings(), "mapbox_token", "pk.test", raising=False)
        monkeypatch.setattr(geo, "_mapbox_forward", boom)
        _account, headers = _driver(client, db, "geo-dead@example.com")

        resp = client.post("/location/geocode", json={"address": "anywhere"}, headers=headers)

        assert resp.status_code == 200
        assert resp.json()["places"] == []

    def test_no_token_means_we_cannot_place_addresses_rather_than_guessing(
        self, client, db, monkeypatch
    ):
        """Dev and CI run without a token. Returning nothing is honest; the coordinate
        this whole entry exists to stop was a fabricated one."""
        from app.foundation.f02_facility.domain import geocode as geo

        monkeypatch.setattr(geo.get_settings(), "mapbox_token", "", raising=False)
        called = []
        monkeypatch.setattr(geo, "_mapbox_forward", lambda *a, **k: called.append(1) or {})
        _account, headers = _driver(client, db, "geo-notoken@example.com")

        resp = client.post("/location/geocode", json={"address": "somewhere"}, headers=headers)

        assert resp.json()["places"] == []
        assert called == []  # and it never called out at all

    def test_geocode_requires_a_session(self, client):
        assert client.post("/location/geocode", json={"address": "x"}).status_code in (401, 403)
