"""AI-CONTEXT: silencing the lot-status prompt at one lot (§23 entry 114).

§13.1 gives an opt-in class a per-subject mute and F8 has had `mute_subject` since the
vendor class shipped — with no surface for this class, so the only control a driver had
was the whole class. That matters more than it sounds: the class switch sits on the same
notification permission that carries the detention P0, and the browser's permission
prompt is ONE-SHOT (§23 entry 111). A driver whose only escape from one annoying prompt
is a bigger switch is a driver we can lose the P0 to.

These drive ROUTES, for the reason `test_prompt_reachability_api.py` explains at length:
this feature has now had three separate defects where the rules were right and nothing
could reach them.
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

LOT = (39.7392, -104.9903)
PROMPT_CLASS = "lot_status_prompt"


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _opted_in_driver(client, db, email="muter@example.com"):
    reg = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    account = db.get(identity.Account, uuid.UUID(reg.json()["account_id"]))
    prefs = notify.get_or_create_prefs(db, account.id)
    prefs.quiet_start = dt_time(3, 0)  # an empty window contains no hour — see 091
    prefs.quiet_end = dt_time(3, 0)
    db.flush()
    client.put(
        f"/notifications/classes/{PROMPT_CLASS}/opt-in",
        json={"opted_in": True},
        headers=headers,
    )
    return account, headers


def _lot(db, name="Mile High Truck Stop", at=LOT):
    return facility.create_facility(db, facility.FacilityType.truck_stop, name, *at)


def _park(db, account, at=LOT):
    now = datetime.now(UTC)
    location.evaluate_ping(db, account.id, *at, occurred_at=now - timedelta(minutes=20))
    location.evaluate_ping(db, account.id, *at, occurred_at=now - timedelta(minutes=10))
    db.flush()


def _ping(client, headers, at=LOT):
    return client.post("/location/ping", json={"lat": at[0], "lon": at[1]}, headers=headers)


def _prompts(client, headers):
    rows = client.get("/notifications", headers=headers).json()["notifications"]
    return [n for n in rows if n["category"] == PROMPT_CLASS]


def test_a_muted_lot_stops_asking(client, db):
    account, headers = _opted_in_driver(client, db)
    lot = _lot(db)

    muted = client.post(f"/map/facility/{lot.id}/mute-prompts", headers=headers)
    assert muted.status_code == 200
    assert muted.json()["muted"] is True

    _park(db, account)
    _ping(client, headers)

    held = _prompts(client, headers)
    assert len(held) == 1
    assert held[0]["status"] == "suppressed"
    assert held[0]["suppressed_reason"] == "muted"


def test_muting_one_lot_leaves_every_other_lot_asking(client, db):
    """The whole point of a per-SUBJECT mute. If this failed, the control would be the
    class switch wearing a smaller label."""
    account, headers = _opted_in_driver(client, db)
    quiet = _lot(db, "Silenced Stop")
    elsewhere = (39.6000, -104.8000)
    other = _lot(db, "Somewhere Else", at=elsewhere)

    client.post(f"/map/facility/{quiet.id}/mute-prompts", headers=headers)

    _park(db, account, at=elsewhere)
    _ping(client, headers, at=elsewhere)

    asked = _prompts(client, headers)
    assert len(asked) == 1
    # AI-CONTEXT: the DECISION, over the wire. Delivery is the push_delivery sweep,
    # so the status a driver's inbox reports the instant a prompt is decided is `queued`.
    assert asked[0]["status"] == "queued"
    assert asked[0]["deep_link"] == f"/facility/{other.id}"


def test_unmuting_asks_again(client, db):
    """§21.8, and the reason `unmute_subject` had to be written: before it, the only way
    out of a mute was `follow_subject`, which also switched the whole class on."""
    account, headers = _opted_in_driver(client, db)
    lot = _lot(db)
    client.post(f"/map/facility/{lot.id}/mute-prompts", headers=headers)

    back = client.post(f"/map/facility/{lot.id}/unmute-prompts", headers=headers)
    assert back.status_code == 200
    assert back.json()["muted"] is False

    _park(db, account)
    _ping(client, headers)

    assert _prompts(client, headers)[0]["status"] == "queued"


def test_unmuting_does_not_switch_the_class_on(client, db):
    """A driver who un-silences one lot has not asked to be asked everywhere. The
    mirror of `unfollow_subject`'s rule, and the trap `follow_subject` sets."""
    reg = client.post(
        "/auth/register", json={"email": "optout@example.com", "password": "pw-123456"}
    )
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    account = db.get(identity.Account, uuid.UUID(reg.json()["account_id"]))
    lot = _lot(db)
    client.post(f"/map/facility/{lot.id}/mute-prompts", headers=headers)

    client.post(f"/map/facility/{lot.id}/unmute-prompts", headers=headers)

    assert notify.is_opted_in(db, account.id, PROMPT_CLASS) is False


def test_unmuting_a_lot_that_was_never_muted_is_not_an_error(client, db):
    """Asking for a state you are already in is not a failure — `/push/unsubscribe`
    settled this posture."""
    _account, headers = _opted_in_driver(client, db)
    lot = _lot(db)

    resp = client.post(f"/map/facility/{lot.id}/unmute-prompts", headers=headers)
    assert resp.status_code == 200


def test_the_pref_route_reports_the_state_a_screen_has_to_render(client, db):
    _account, headers = _opted_in_driver(client, db)
    lot = _lot(db)

    pref = f"/map/facility/{lot.id}/prompt-pref"
    assert client.get(pref, headers=headers).json()["muted"] is False
    client.post(f"/map/facility/{lot.id}/mute-prompts", headers=headers)
    assert client.get(pref, headers=headers).json()["muted"] is True


def test_a_mute_recorded_against_a_MERGED_id_still_silences_the_real_lot(client, db):
    """§23 entry 73's scoping mistake, refused in a new place.

    A merge does not delete the duplicate — deliberately, so an id a driver already
    holds keeps working — and the prompt's `subject_ref` is the CANONICAL facility. So a
    mute keyed on the id the driver happens to be holding would 200 and then do nothing,
    and they would be asked again the next night having told us not to.
    """
    account, headers = _opted_in_driver(client, db)
    canonical = _lot(db, "Flying J Travel Center")
    duplicate = _lot(db, "Flying J (dupe)", at=(LOT[0] + 0.0002, LOT[1]))
    facility.merge_facilities(db, canonical, duplicate)
    db.flush()

    muted = client.post(f"/map/facility/{duplicate.id}/mute-prompts", headers=headers)
    assert muted.json()["facility_id"] == str(canonical.id), "the merged id was not resolved"

    _park(db, account)
    _ping(client, headers)

    held = _prompts(client, headers)
    assert len(held) == 1
    assert held[0]["suppressed_reason"] == "muted"


def test_the_mute_routes_need_a_session(client, db):
    lot = _lot(db)
    assert client.post(f"/map/facility/{lot.id}/mute-prompts").status_code in (401, 403)
    assert client.get(f"/map/facility/{lot.id}/prompt-pref").status_code in (401, 403)
