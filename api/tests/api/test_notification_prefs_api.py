"""AI-CONTEXT: the door §13.3 never had (§23 entry 115).

"Default 22:00-06:00 local (driver-adjustable)" — and neither half was reachable. The
zone defaulted to UTC and no route wrote it; the window had no route either. So quiet
hours landed on the wrong eight hours for every driver on a US-only platform.

Route-level, on purpose. Three defects in a row on the neighbouring feature (§23 entries
112, 113, 114) were all invisible because the tests entered where a driver cannot, so the
habit here is the front door: if no test reaches it over HTTP, nobody can.
"""

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify
from app.main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _driver(client, db, email="prefs@example.com"):
    reg = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    account = db.get(identity.Account, uuid.UUID(reg.json()["account_id"]))
    return account, headers


def test_a_new_driver_reads_the_shipped_default(client, db):
    """UTC is the value that was wrong for everyone. It is still the default — the fix is
    that the client now overwrites it on sign-in, not that the column changed."""
    _account, headers = _driver(client, db)

    prefs = client.get("/notifications/prefs", headers=headers).json()

    assert prefs == {"timezone": "UTC", "quiet_start": "22:00", "quiet_end": "06:00"}


def test_the_driver_can_set_their_zone_and_it_changes_who_gets_interrupted(client, db):
    """The whole point, asserted through the route: setting the zone moves the window
    onto the right eight hours."""
    account, headers = _driver(client, db)

    resp = client.put(
        "/notifications/prefs", json={"timezone": "America/Denver"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["timezone"] == "America/Denver"

    evening = datetime(2026, 7, 31, 19, 0, tzinfo=ZoneInfo("America/Denver")).astimezone(UTC)
    note = notify.dispatch(
        db,
        account.id,
        notify.NotificationTier.P1,
        "free_time_warning",
        "30 minutes of free time left",
        "Arrived 09:12",
        "/load",
        notify.RecordingNotificationGateway(),
        now=evening,
    )
    assert note.status == notify.NotificationStatus.queued


def test_the_driver_can_move_the_window(client, db):
    account, headers = _driver(client, db)

    resp = client.put(
        "/notifications/prefs",
        json={"quiet_start": "09:00", "quiet_end": "17:00"},
        headers=headers,
    )

    assert resp.json()["quiet_start"] == "09:00"
    assert resp.json()["quiet_end"] == "17:00"
    prefs = notify.get_or_create_prefs(db, account.id)
    assert prefs.quiet_start.strftime("%H:%M") == "09:00"


def test_sending_only_the_zone_leaves_the_window_alone(client, db):
    """The reason the PUT is partial. The client sends the detected zone on EVERY
    sign-in; a whole-object write would quietly undo a window the driver chose, and they
    would have no way to tell what had happened."""
    _account, headers = _driver(client, db)
    client.put(
        "/notifications/prefs",
        json={"quiet_start": "09:00", "quiet_end": "17:00"},
        headers=headers,
    )

    client.put("/notifications/prefs", json={"timezone": "America/Chicago"}, headers=headers)

    after = client.get("/notifications/prefs", headers=headers).json()
    assert after == {
        "timezone": "America/Chicago",
        "quiet_start": "09:00",
        "quiet_end": "17:00",
    }


def test_an_unknown_zone_is_refused_and_changes_nothing(client, db):
    _account, headers = _driver(client, db)

    resp = client.put(
        "/notifications/prefs", json={"timezone": "Mars/Olympus_Mons"}, headers=headers
    )

    assert resp.status_code == 422
    assert client.get("/notifications/prefs", headers=headers).json()["timezone"] == "UTC"


def test_a_malformed_time_is_refused(client, db):
    _account, headers = _driver(client, db)

    resp = client.put("/notifications/prefs", json={"quiet_start": "25:99"}, headers=headers)

    assert resp.status_code == 422


def test_the_prefs_routes_need_a_session(client, db):
    assert client.get("/notifications/prefs").status_code in (401, 403)
    assert client.put("/notifications/prefs", json={"timezone": "UTC"}).status_code in (401, 403)
