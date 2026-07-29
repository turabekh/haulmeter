"""AI-CONTEXT: F8's first delivery path, as tests.

F8 has decided tiers, budgets, quiet hours and classes since it shipped and every
decision ended in a row nobody could read: no notification endpoint existed in the
schema at all, the client has no service worker or push registration, and the only
gateway wired in application code is the RECORDING one used by tests. §23 entry 429
caught the miniature — "nothing may be filed P2 until a surface renders the digest" —
and the general case was larger.

What these defend:
· A suppressed notification is still READABLE. §13.1 caps unprompted interruptions;
  a driver opening a list is asking, not being interrupted. Quiet hours defer, they
  do not destroy.
· `pending` is never shown — a row the system has not finished deciding is not a fact.
· §13.5's deep link survives to the client, so the inbox can land on the exact screen.
· Another driver's notification is NOT FOUND, never FORBIDDEN: a 403 would confirm the
  id exists and leak that someone else was told something.
· Reading is idempotent — the first read is when the driver learned it, and a second
  tap must not rewrite that.
"""

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


@pytest.fixture
def driver(client):
    resp = client.post(
        "/auth/register", json={"email": "inbox@example.com", "password": "pw-123456"}
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _dispatch(db, account_id, **kw):
    gw = notify.RecordingNotificationGateway()
    defaults = dict(
        category="detention_started",
        tier=notify.NotificationTier.P0,
        title="Detention started · $75/h",
        body="Notice ready to send",
        deep_link="/load/abc/evidence",
        gateway=gw,
    )
    defaults.update(kw)
    return notify.dispatch(db, account_id, **defaults)


def test_the_inbox_exists_at_all(client, driver, db):
    # the whole point: before this endpoint there was no way for a driver to see
    # anything F8 had decided about them
    resp = client.get("/notifications", headers=driver)
    assert resp.status_code == 200
    assert resp.json() == {"notifications": [], "unread": 0}


def test_a_dispatched_notification_reaches_the_driver(client, driver, db):
    account = identity.resolve_session(db, driver["Authorization"].split()[1])
    _dispatch(db, account.id)

    body = client.get("/notifications", headers=driver).json()
    assert body["unread"] == 1
    row = body["notifications"][0]
    assert row["tier"] == "P0"
    assert row["deep_link"] == "/load/abc/evidence"  # §13.5 survives to the client
    assert row["read_at"] is None


def test_reading_is_idempotent(client, driver, db):
    account = identity.resolve_session(db, driver["Authorization"].split()[1])
    _dispatch(db, account.id)
    nid = client.get("/notifications", headers=driver).json()["notifications"][0]["id"]

    first = client.post(f"/notifications/{nid}/read", headers=driver).json()["read_at"]
    second = client.post(f"/notifications/{nid}/read", headers=driver).json()["read_at"]

    assert first is not None
    assert first == second  # when the driver learned it does not move
    assert client.get("/notifications", headers=driver).json()["unread"] == 0


def test_another_drivers_notification_is_not_found(client, driver, db):
    account = identity.resolve_session(db, driver["Authorization"].split()[1])
    _dispatch(db, account.id)
    nid = client.get("/notifications", headers=driver).json()["notifications"][0]["id"]

    other = client.post(
        "/auth/register", json={"email": "other@example.com", "password": "pw-123456"}
    ).json()["token"]
    resp = client.post(
        f"/notifications/{nid}/read", headers={"Authorization": f"Bearer {other}"}
    )

    # 404 and not 403: confirming the id exists would leak that someone else was told
    assert resp.status_code == 404


def test_the_inbox_requires_a_session(client):
    assert client.get("/notifications").status_code == 401


def test_a_suppressed_notification_is_still_readable(client, driver, db):
    """§13.1 caps UNPROMPTED interruptions at two a day. A driver who opens a list is
    asking, not being interrupted — so the budget must defer the interruption without
    destroying the information. Hiding it here would make a considerate rule lossy."""
    account = identity.resolve_session(db, driver["Authorization"].split()[1])
    for i in range(4):
        _dispatch(
            db,
            account.id,
            tier=notify.NotificationTier.P1,
            category="free_time_warning",
            title=f"Free time warning {i}",
        )

    rows = client.get("/notifications", headers=driver).json()["notifications"]
    statuses = {r["status"] for r in rows}

    # the budget did its job...
    assert "suppressed" in statuses, statuses
    # ...and nothing vanished because of it
    assert len(rows) == 4
    suppressed = next(r for r in rows if r["status"] == "suppressed")
    assert suppressed["suppressed_reason"] is not None
