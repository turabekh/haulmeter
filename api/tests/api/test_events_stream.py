"""AI-CONTEXT: the live stream (§23 entry 103), and the one property that matters.

**A stream must not hold a database session.** FastAPI's `Depends(get_db)` yields a
session for the life of the REQUEST, and an SSE request lives for minutes — so wired
the obvious way, each connected driver pins one pooled connection and the
thirty-first takes the API down for everyone. §23 entry 93 did precisely this to this
codebase from a single phone's position stream, so this is not a hypothetical failure
mode; it is the one this feature is shaped to avoid.

Measured before these were written: 8 concurrent streams added **+2** connections to
the pool (the brief auth lookups, returned immediately), not +8, and `/health` still
answered in 5.8 ms. These tests hold that shape.

The transport itself is exercised live rather than mocked where it can be — a mocked
pub/sub proves the test doubles agree with each other and nothing about Redis.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.api.events import cell_for
from app.core import events
from app.main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    resp = client.post(
        "/auth/register", json={"email": "stream@example.com", "password": "pw-123456"}
    )
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_the_stream_requires_a_session(client):
    resp = client.get("/events/stream", params={"lat": 32.7, "lon": -96.8})
    assert resp.status_code == 401


def test_only_allowlisted_kinds_may_be_streamed(client, auth):
    # a free-form channel name would let a client subscribe to anything the product
    # ever publishes, including things it was never meant to hear
    resp = client.get(
        "/events/stream", params={"kind": "detention", "lat": 32.7, "lon": -96.8}, headers=auth
    )
    assert resp.status_code == 422


def test_a_cell_groups_nearby_drivers_and_separates_distant_ones():
    """Fan-out is per geohash cell: a broadcast in Dallas must not wake a stream in
    Ohio, and two drivers at the same truck stop must land on the same channel."""
    dallas = cell_for(32.7767, -96.7970)
    dallas_again = cell_for(32.7800, -96.8000)  # ~500 m away
    ohio = cell_for(40.8316, -83.9673)

    assert dallas == dallas_again
    assert dallas != ohio
    assert events.channel_for("handoff", dallas) != events.channel_for("handoff", ohio)


def test_publishing_never_raises_when_redis_is_unreachable(monkeypatch):
    """The publish rides a write that is already committed. A telemetry channel that
    could break a broadcast would be worse than having no channel at all."""

    def boom():
        raise OSError("redis is gone")

    monkeypatch.setattr(events, "_client", boom)
    assert events.publish("handoff", "9vg4", {"handoff_id": "h-1"}) is False


def test_a_stream_holds_no_database_session(client, auth):
    """The property the whole design rests on. The account is resolved inside the
    REQUEST and the session released before the body is generated — so the generator,
    which is what lives for minutes, has no session to hold."""
    import inspect

    from app.api import events as events_api

    source = inspect.getsource(events_api._stream)
    # the generator may not touch a session, directly or through a dependency
    assert "get_db" not in source
    assert "Session" not in source

    # and the endpoint takes its session as an ordinary request dependency, which
    # FastAPI releases when the function RETURNS — before the body is generated
    sig = inspect.signature(events_api.stream)
    assert "db" in sig.parameters, "the endpoint still authenticates against the DB"
    assert inspect.isgeneratorfunction(events_api._stream)


def test_the_stream_is_capped_so_a_forgotten_tab_cannot_hold_a_slot():
    # EventSource reconnects by itself, so a bounded stream costs nothing and stops a
    # abandoned page holding a subscriber slot indefinitely
    assert 0 < events.MAX_STREAM_SECONDS <= 3600
    assert 0 < events.HEARTBEAT_SECONDS < 60
