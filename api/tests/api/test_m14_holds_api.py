"""AI-CONTEXT: the approvals queue over HTTP (M14 slice 1, PRD Extension E2, D8).

Two things these hold that the domain tests cannot: that the routes are gated the way
fleet money is gated, and that **no credential is ever in a response**. The second is not
paranoia — the connector table holds a working key to somebody else's telematics, and a
route that leaked `key_last4`, let alone the ciphertext, would put it in a browser's
history and every proxy log between here and the operator.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f13_flags import public as flags
from app.main import app
from app.modules.m14_recovery import public as m14
from app.modules.m14_recovery.domain import crypto


@pytest.fixture(autouse=True)
def _connector_key(monkeypatch):
    monkeypatch.setenv(crypto.SECRET_ENV, "c2VjcmV0LWtleS0zMi1ieXRlcy1sb25nLWVub3VnaCE=")


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    # the routes are gated on the module flag, and slice 1's flag declares nothing —
    # so every test here must switch it on deliberately, which is the posture wanted
    m14.register_module(db)
    for name in m14.GATES:
        flags.satisfy_gate(db, flags.get_gate(db, m14.FLAG_KEY, name), note="test")
    flags.enable(db, m14.FLAG_KEY)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client, email="owner@example.com"):
    resp = client.post("/auth/register", json={"email": email, "password": "pw-123456"})
    assert resp.status_code == 201
    return resp.json()["account_id"], {"Authorization": f"Bearer {resp.json()['token']}"}


def _fleet(client, headers):
    created = client.post("/fleet", json={"name": "Acme Fleet"}, headers=headers)
    assert created.status_code == 201
    return created.json()["fleet_id"]


def test_the_queue_requires_a_session(client):
    assert client.get(f"/fleet/{uuid.uuid4()}/holds").status_code == 401


def test_the_queue_is_fleet_management_only(client, db):
    """Approving invoices in the CARRIER's name (D13), so it is management action — the
    same owner/dispatcher rule M12's report and claims desk already enforce."""
    _, owner = _auth(client, "owner@example.com")
    fleet_id = _fleet(client, owner)

    _, stranger = _auth(client, "stranger@example.com")
    assert client.get(f"/fleet/{fleet_id}/holds", headers=stranger).status_code == 403


def test_an_empty_queue_still_states_whether_it_could_send(client, db):
    """`can_send` travels WITH the list rather than being discovered on failure: a claim
    that cannot leave the box must say so BEFORE an admin approves, not explain
    afterwards why nothing happened."""
    _, owner = _auth(client)
    fleet_id = _fleet(client, owner)

    body = client.get(f"/fleet/{fleet_id}/holds", headers=owner).json()
    assert body["holds"] == []
    assert body["can_send"] is True  # both gates satisfied by the fixture
    assert body["send_blocked_by"] is None


def test_the_queue_reports_the_blocker_when_counsel_has_not_signed(client, db):
    # the state a real operator is in today: D13 open, so approving records a decision
    # and sends nothing
    flags.unsatisfy_gate(
        db, flags.get_gate(db, m14.FLAG_KEY, "carrier_invoicing_counsel"), note="test"
    )
    _, owner = _auth(client)
    fleet_id = _fleet(client, owner)

    body = client.get(f"/fleet/{fleet_id}/holds", headers=owner).json()
    assert body["can_send"] is False
    assert body["send_blocked_by"] == "carrier_invoicing_counsel"


def test_no_route_here_returns_any_part_of_a_credential(client, db):
    """The connector row holds a working key to somebody else's telematics. Nothing in
    this module's HTTP surface may return it — not the ciphertext, not `key_last4`."""
    _, owner = _auth(client)
    fleet_id = _fleet(client, owner)
    m14.connect_fleet(db, uuid.UUID(fleet_id), "mot_live_supersecret", m14.Provider.motive)
    db.flush()

    raw = client.get(f"/fleet/{fleet_id}/holds", headers=owner).text
    assert "supersecret" not in raw
    assert "key_ciphertext" not in raw
    assert "key_last4" not in raw
    assert "cret" not in raw  # the last four of the pasted key


def test_deciding_a_hold_that_does_not_exist_is_a_404(client, db):
    _, owner = _auth(client)
    fleet_id = _fleet(client, owner)
    resp = client.post(f"/fleet/{fleet_id}/holds/{uuid.uuid4()}/approve", headers=owner)
    assert resp.status_code == 404


def test_a_hold_belonging_to_another_fleet_is_not_reachable(client, db):
    """The id is a UUID, not a secret. Scoping by fleet is what stops one carrier
    approving another carrier's claim."""
    _, owner = _auth(client, "owner@example.com")
    mine = _fleet(client, owner)

    other_account, other = _auth(client, "other@example.com")
    theirs = _fleet(client, other)
    held = m14.HeldClaim(
        fleet_id=uuid.UUID(theirs),
        claim_ref=uuid.uuid4(),
        stop_ref=uuid.uuid4(),
        account_id=uuid.UUID(other_account),
    )
    db.add(held)
    db.flush()

    resp = client.post(f"/fleet/{mine}/holds/{held.id}/approve", headers=owner)
    assert resp.status_code == 404
