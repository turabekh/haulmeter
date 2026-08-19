"""AI-CONTEXT: the food half was switched off and the app kept offering it.

The owner reported it from the screen: "still like food notifications are there which we
removed before". `m13_vendor` has been FALSE in production since HANDOFF-114 — food goes
by FLAG rather than by deletion (v2.0 §4) — and two things had never been told:
`/auth/me`, which carries every other capability condition the driver app reads, and the
opt-in route itself, which recorded a subscription to a module that is not running.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f13_flags import public as flags
from app.main import app
from app.modules.m13_vendor import public as m13


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client, db):
    reg = client.post("/auth/register", json={"email": "more@example.com", "password": "pw-123456"})
    account = db.get(identity.Account, uuid.UUID(reg.json()["account_id"]))
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    return {"Authorization": f"Bearer {reg.json()['token']}"}


def test_me_says_food_is_off_so_the_screen_can_stop_advertising_it(client, db):
    m13.register_module(db)
    # flags default OFF (PRD §6); registering is enough to make the off-state real
    headers = _auth(client, db)

    body = client.get("/auth/me", headers=headers).json()

    assert body["food_enabled"] is False


def test_me_says_food_is_on_when_it_actually_is(client, db):
    m13.register_module(db)
    flags.enable(db, m13.FLAG_KEY)
    headers = _auth(client, db)

    assert client.get("/auth/me", headers=headers).json()["food_enabled"] is True


def test_the_food_opt_in_names_its_own_half(client, db):
    """A6's rule, and the case that is masked today because BOTH halves are off.

    `require_any_module` gates this router on "is ANY half live" — food OR service
    centres — because refusing it when `m13_vendor` is off "would take the repair shops
    with it". Its docstring is explicit that the gate "is never sufficient on its own,
    and every route behind it names its own half". The food-alerts opt-in never did.

    So with service centres ON and food OFF the router is alive and this route would
    have recorded a subscription to alerts that cannot arrive. That is the state A6
    exists to produce, which makes this the case worth asserting rather than the
    both-off one that merely 404s.
    """
    m13.register_module(db)
    flags.enable(db, m13.SERVICE_CENTER_FLAG_KEY)  # A6: repair shops live, food not

    headers = _auth(client, db)
    resp = client.put("/vendors/alerts/opt-in", json={"opted_in": True}, headers=headers)

    assert resp.status_code == 404, "food is off; this must not record an opt-in"


def test_the_opt_in_still_works_when_food_is_running(client, db):
    m13.register_module(db)
    flags.enable(db, m13.FLAG_KEY)
    headers = _auth(client, db)

    resp = client.put("/vendors/alerts/opt-in", json={"opted_in": True}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["opted_in"] is True
