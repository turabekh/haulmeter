"""AI-CONTEXT: can a DRIVER reach the lot-status prompt? Three times, the answer was no.

This file exists because the same defect has now appeared three times in one feature,
each time behind a green suite:

1. §23 entry 112 — the trigger hung off `DWELL_TICK`, which only fires for ARMED
   facilities, and nothing arms a truck stop. Thirteen tests passed; every one of them
   called `prompt_for_lot_status` directly.
2. §23 entry 113 — the tray answer had no token, because the only caller of the
   IndexedDB mirror was a test-only helper. Nine test files exercised it; production
   never did.
3. This one — `dispatch` gates on `is_opted_in` before any tier logic,
   `lot_status_prompt` is `opt_in_default=False`, and **no endpoint, script or screen
   could set that preference.** `set_class_opt_in` had exactly one caller in the tree:
   the vendor-alerts route, hardcoded to `VENDOR_ALERT`. So every dispatch suppressed
   `not_opted_in`, for every driver, always — and the feature's own tests opted in by
   calling the service function.

So the assertions here go through ROUTES, never through `app.foundation`/`app.modules`
service calls. That is the whole point: a suite that reaches past the API answers "do
these rules work" and can never answer "can anyone get here".

Two things ARE scaffolding, and they are marked as such below: the facility has to
exist, and fifteen minutes have to have passed. Neither is the thing under test.
"""

import uuid
from datetime import UTC, datetime, timedelta
from datetime import time as dt_time

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f08_notifications import public as notify
from app.main import app

LOT = (41.8781, -87.6298)
PROMPT_CLASS = "lot_status_prompt"


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _driver(client, db, email="reach@example.com"):
    reg = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    assert reg.status_code in (200, 201), reg.text
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    account = db.get(identity.Account, uuid.UUID(reg.json()["account_id"]))
    return account, headers


def _awake(db, account):
    """SCAFFOLDING. §13.3's default quiet hours are 22:00-06:00 and this test has no
    control over what time it runs — the lesson from the m13 flake in HANDOFF-091 and
    from the two EXIT tests that failed at 02:03 UTC. An empty window can contain no
    hour, because `in_quiet_hours` compares `start <= local < end`."""
    prefs = notify.get_or_create_prefs(db, account.id)
    prefs.quiet_start = dt_time(3, 0)
    prefs.quiet_end = dt_time(3, 0)
    db.flush()


def _lot(db, name="Reachable Truck Stop"):
    """SCAFFOLDING. There is no driver-facing route that creates a facility, and there
    should not be."""
    return facility.create_facility(db, facility.FacilityType.truck_stop, name, *LOT)


def _parked_for_twenty_minutes(db, account):
    """SCAFFOLDING for TIME, not for the trigger.

    `POST /location/ping` stamps its own `datetime.now(UTC)` — server time is
    authoritative (PRD §7.3) — so a test cannot make fifteen minutes pass through the
    route. The trail is seeded relative to real now, and the ping that MATTERS is still
    posted over HTTP below.
    """
    now = datetime.now(UTC)
    location.evaluate_ping(db, account.id, *LOT, occurred_at=now - timedelta(minutes=20))
    location.evaluate_ping(db, account.id, *LOT, occurred_at=now - timedelta(minutes=10))
    db.flush()


def _inbox(client, headers, class_key=PROMPT_CLASS):
    rows = client.get("/notifications", headers=headers).json()["notifications"]
    return [n for n in rows if n["category"] == class_key]


# --- the test this file exists for -------------------------------------------------


def test_a_driver_can_turn_the_prompt_on_and_then_be_asked(client, db):
    """RED before the opt-in endpoint existed, and the only test in the tree that could
    have caught the third occurrence.

    Every step a driver could actually perform is an HTTP call: register, opt in, ping.
    """
    account, headers = _driver(client, db)
    _awake(db, account)
    lot = _lot(db)

    opt_in = client.put(
        f"/notifications/classes/{PROMPT_CLASS}/opt-in",
        json={"opted_in": True},
        headers=headers,
    )
    assert opt_in.status_code == 200, "a driver has no way to turn this class on"
    assert opt_in.json()["opted_in"] is True

    _parked_for_twenty_minutes(db, account)
    ping = client.post("/location/ping", json={"lat": LOT[0], "lon": LOT[1]}, headers=headers)
    assert ping.status_code == 201

    asked = _inbox(client, headers)
    assert len(asked) == 1, "the driver opted in, parked, and was never asked"
    assert asked[0]["status"] == "sent"
    assert asked[0]["suppressed_reason"] is None
    assert asked[0]["deep_link"] == f"/facility/{lot.id}"


def test_without_opting_in_the_driver_is_not_asked(client, db):
    """The other half of the same fact, and the state every driver was stuck in: the
    class is off until they say otherwise, and silence is never consent (E-D1)."""
    account, headers = _driver(client, db)
    _awake(db, account)
    _lot(db)
    _parked_for_twenty_minutes(db, account)

    client.post("/location/ping", json={"lat": LOT[0], "lon": LOT[1]}, headers=headers)

    held = _inbox(client, headers)
    assert len(held) == 1
    assert held[0]["status"] == "suppressed"
    assert held[0]["suppressed_reason"] == "not_opted_in"


def test_turning_it_back_off_stops_the_asking(client, db):
    """§21.8: off is exactly as easy as on. A one-way switch is a trap."""
    account, headers = _driver(client, db)
    _awake(db, account)
    _lot(db)
    client.put(
        f"/notifications/classes/{PROMPT_CLASS}/opt-in",
        json={"opted_in": True},
        headers=headers,
    )
    off = client.put(
        f"/notifications/classes/{PROMPT_CLASS}/opt-in",
        json={"opted_in": False},
        headers=headers,
    )
    assert off.json()["opted_in"] is False

    _parked_for_twenty_minutes(db, account)
    client.post("/location/ping", json={"lat": LOT[0], "lon": LOT[1]}, headers=headers)

    assert _inbox(client, headers)[0]["suppressed_reason"] == "not_opted_in"


# --- the class list, which is what lets a screen render the switch in the right state


def test_the_class_list_reports_what_the_driver_has_chosen(client, db):
    account, headers = _driver(client, db)
    _awake(db, account)

    before = client.get("/notifications/classes", headers=headers)
    assert before.status_code == 200
    prompt = next(c for c in before.json()["classes"] if c["key"] == PROMPT_CLASS)
    # no row yet: the default IS the answer, not a missing one
    assert prompt["opted_in"] is False
    assert prompt["opt_in_default"] is False
    assert prompt["max_per_day"] == 1

    client.put(
        f"/notifications/classes/{PROMPT_CLASS}/opt-in",
        json={"opted_in": True},
        headers=headers,
    )

    after = client.get("/notifications/classes", headers=headers).json()["classes"]
    assert next(c for c in after if c["key"] == PROMPT_CLASS)["opted_in"] is True


def test_a_class_that_does_not_exist_is_not_found(client, db):
    """The registry is code-defined (§23 E-D1), so an unknown key is a client bug and
    must not create a preference row that governs nothing."""
    _account, headers = _driver(client, db)

    resp = client.put(
        "/notifications/classes/lot_status_promt/opt-in",  # typo on purpose
        json={"opted_in": True},
        headers=headers,
    )

    assert resp.status_code == 404


def test_the_class_routes_need_a_session(client, db):
    assert client.get("/notifications/classes").status_code in (401, 403)
    assert client.put(
        f"/notifications/classes/{PROMPT_CLASS}/opt-in", json={"opted_in": True}
    ).status_code in (401, 403)
