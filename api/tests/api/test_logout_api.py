"""F1-2 — signing out is a server fact now, not only a localStorage one.

There was no logout route at all: the only revocation anywhere in the product was the
impersonation path. Clearing the client left the bearer valid for the rest of its 30-day
TTL, so a driver handing a phone to a mechanic had not signed out of anything a server
would notice.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _register(client, email="out@example.com"):
    body = client.post(
        "/auth/register", json={"email": email, "password": "pw-123456"}
    ).json()
    return body["token"], {"Authorization": f"Bearer {body['token']}"}


def test_the_token_is_dead_on_the_server_afterwards(client, db):
    token, headers = _register(client)
    assert client.get("/auth/me", headers=headers).status_code == 200

    assert client.post("/auth/logout", headers=headers).status_code == 204

    assert client.get("/auth/me", headers=headers).status_code == 401


def test_it_ends_only_this_session(client, db):
    """"Sign out everywhere" is a different act; `revoke_sessions` makes it trivial later."""
    _, first = _register(client)
    second_body = client.post(
        "/auth/login", json={"email": "out@example.com", "password": "pw-123456"}
    ).json()
    second = {"Authorization": f"Bearer {second_body['token']}"}

    client.post("/auth/logout", headers=first)

    assert client.get("/auth/me", headers=first).status_code == 401
    assert client.get("/auth/me", headers=second).status_code == 200


def test_it_needs_a_session_to_end(client, db):
    assert client.post("/auth/logout").status_code == 401
    assert (
        client.post("/auth/logout", headers={"Authorization": "Bearer nonsense"}).status_code
        == 401
    )


def test_logging_out_twice_is_not_an_error_the_second_time_it_is_a_401(client, db):
    """The token is gone, so the second call cannot authenticate — which is correct."""
    _, headers = _register(client)
    client.post("/auth/logout", headers=headers)

    assert client.post("/auth/logout", headers=headers).status_code == 401
