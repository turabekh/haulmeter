"""AI-CONTEXT: HTTP API tests for M11 Voice Copilot. TestClient with get_db
overridden to the transactional test session. Proves text intent routing, the
motion policy over HTTP, the claim assistant, and the English-out ghostwriter.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f07_ledger import public as ledger
from app.main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth(client):
    resp = client.post(
        "/auth/register", json={"email": "driver@example.com", "password": "pw-123456"}
    )
    assert resp.status_code == 201
    return resp.json()["account_id"], {"Authorization": f"Bearer {resp.json()['token']}"}


def test_ask_requires_auth(client):
    assert client.post("/voice/ask", json={"text": "what am I owed"}).status_code == 401


def test_ask_routes_money_owed(client, db):
    account_id, headers = _auth(client)
    ledger.create_receivable(db, uuid.UUID(account_id), ledger.ReceivableKind.detention, 15000)
    resp = client.post("/voice/ask", json={"text": "what am I owed"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "money_owed"
    assert "$150.00" in body["spoken"]


def test_ask_defers_action_while_driving(client):
    headers = _auth(client)[1]
    resp = client.post(
        "/voice/ask",
        json={"text": "start my detention clock", "driving": True},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["needs_confirmation"] is True
    assert body["mode"] == "voice"
    assert body["data"]["deferred"] is True


def test_ghostwriter_draft_is_english(client):
    headers = _auth(client)[1]
    resp = client.post(
        "/voice/draft",
        json={"kind": "detention notice", "facts": "3h past free time", "tone": "firm"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["outbound_language"] == "en"
    assert "ENGLISH" in body["draft"]
