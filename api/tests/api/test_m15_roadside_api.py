"""AI-CONTEXT: Q-6 AT THE ENTRY POINT — the assertion `test_session_loop.py` believed it
was making and could not.

That file's docstring says the safety of the `allow_draft` dev seam is that "nothing in
the request path passes it", and its test proves the DOMAIN DEFAULT: call
`next_officer_turn` without the argument and an all-draft pool raises. Both halves are
true and neither is the claim. The claim is about the request path, and the request path
is this file's subject — a domain default cannot testify about what an HTTP layer chooses
to pass.

It was passing it. `_officer_frame` read `allow_draft` straight off the client's own
WebSocket frame, so any browser could ask for unreleased content and be served it. Q-6 is
"content ships reviewed or not at all" and the reason it exists is that F9 drafts the text
— an ungoverned client flag turned a review pipeline into a suggestion.

These tests are at the SOCKET, not the domain, because that is where the defect lived and
the level a domain test cannot reach.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import m15_roadside as m15_api
from app.api.deps import get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f13_flags import public as flags
from app.main import app
from app.modules.m15_roadside import public as m15
from app.modules.m15_roadside.domain import models as m
from app.modules.m15_roadside.domain import session_loop as loop


@pytest.fixture
def client(db, monkeypatch):
    """A client whose socket talks to the TEST database.

    AI-CONTEXT: the socket deliberately does NOT use `Depends(get_db)` — it opens a
    session per turn so a talking driver cannot pin a pooled connection for minutes
    (the `events.py` outage). That is correct, and it means overriding `get_db` is not
    enough: `SessionLocal` is module-global and bound to the app engine, so an
    un-patched socket test would read and WRITE THE DEV DATABASE while reporting on the
    test one. `close()` is neutered because the handler closes per turn and the fixture
    owns this session's lifetime.
    """

    def override_get_db():
        yield db

    class _NonClosing:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def close(self):
            pass

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(m15_api, "SessionLocal", lambda: _NonClosing(db))
    yield TestClient(app)
    app.dependency_overrides.clear()


def _module_on(db):
    """The operator's decision, made explicitly — registration never writes it."""
    m15.register_module(db)
    flag = db.get(flags.FeatureFlag, m15.FLAG_KEY)
    flag.enabled = True
    db.flush()


def _draft_content(db):
    intent = m.Intent(
        key="destination",
        domain="stop",
        canonical_meaning="the driver states where they are headed",
        required_slots={"destination": "Chicago"},
    )
    db.add(intent)
    db.flush()
    db.add(
        m.PhraseVariant(
            intent_id=intent.id,
            text="DRAFT LINE — where are you headed?",
            difficulty=m.Difficulty.clear,
            status=m.ContentStatus.draft,
        )
    )
    db.flush()
    return intent


def _account(db):
    return identity.register_account(db, f"m15-api-{uuid.uuid4().hex[:8]}@example.com", "pw-123456")


def _session(db):
    scenario = m.ScenarioVersion(
        version=1,
        difficulty=m.Difficulty.clear,
        allowed_intents=["destination"],
        status=m.ContentStatus.draft,
    )
    db.add(scenario)
    db.flush()
    return loop.start_session(
        db, scenario=scenario, account_id=_account(db).id, consented=True
    )


def test_the_catalogue_is_empty_rather_than_absent_when_nothing_is_reviewed(client, db):
    """200 with an empty list, not a 404.

    Today this IS the state of the module: nothing has been through review. The surface
    renders its empty state from this, and a 404 would say "no such feature" about a
    feature that exists and is waiting on a human.
    """
    _module_on(db)
    _draft_content(db)

    resp = client.get("/roadside/scenarios")

    assert resp.status_code == 200
    assert resp.json() == {"scenarios": []}


def test_the_catalogue_never_names_a_scenario_the_driver_could_not_run(client, db):
    """The endpoint is a thin read over `startable_scenarios` — this asserts the wiring,
    not the policy, which is held in the domain tests where the laws live."""
    _module_on(db)
    intent = _draft_content(db)
    db.add(
        m.PhraseVariant(
            intent_id=intent.id,
            text="RELEASED LINE — where are you headed?",
            difficulty=m.Difficulty.clear,
            status=m.ContentStatus.released,
            version=2,
        )
    )
    scenario = m.ScenarioVersion(
        version=1,
        difficulty=m.Difficulty.clear,
        allowed_intents=["destination"],
        status=m.ContentStatus.released,
    )
    db.add(scenario)
    db.flush()

    body = client.get("/roadside/scenarios").json()

    assert [s["id"] for s in body["scenarios"]] == [str(scenario.id)]
    assert body["scenarios"][0]["intents"] == ["destination"]
    # the version is HIDDEN STATE — a driver never sees it and never picks it
    assert "version" not in body["scenarios"][0]


def test_the_catalogue_is_gated_with_the_module(client, db):
    """A disabled module is NOT THERE (404, entry 105) — including its catalogue."""
    m15.register_module(db)
    flag = db.get(flags.FeatureFlag, m15.FLAG_KEY)
    flag.enabled = False
    db.flush()

    assert client.get("/roadside/scenarios").status_code == 404


def test_a_client_asking_for_draft_content_is_refused(client, db):
    """THE ONE THIS FILE EXISTS FOR.

    A client sets `allow_draft` itself and asks. The only acceptable answer is the same
    one an empty released pool gets: refuse. Serving the draft here would mean F9's
    unreviewed words reaching a driver on the client's say-so.
    """
    _module_on(db)
    _draft_content(db)
    session = _session(db)

    with client.websocket_connect(f"/roadside/session/{session.id}/stream") as ws:
        ws.send_json({"type": "ready", "driver_state": "IDLE", "allow_draft": True})
        with pytest.raises(WebSocketDisconnect) as caught:
            ws.receive_json()

    assert caught.value.code == m15_api.CLOSE_NO_CONTENT


def test_the_ordinary_ready_frame_is_refused_too(client, db):
    """The control. If this ever passes while the one above fails, the refusal came from
    somewhere other than the released-pool check and neither test means what it says."""
    _module_on(db)
    _draft_content(db)
    session = _session(db)

    with client.websocket_connect(f"/roadside/session/{session.id}/stream") as ws:
        ws.send_json({"type": "ready", "driver_state": "IDLE"})
        with pytest.raises(WebSocketDisconnect) as caught:
            ws.receive_json()

    assert caught.value.code == m15_api.CLOSE_NO_CONTENT


def test_released_content_is_served(client, db):
    """The other side of the law: review is a path, not a wall. Without this the two
    refusals above would also pass on a socket that could serve nothing at all."""
    _module_on(db)
    intent = _draft_content(db)
    db.add(
        m.PhraseVariant(
            intent_id=intent.id,
            text="RELEASED LINE — where are you headed?",
            difficulty=m.Difficulty.clear,
            status=m.ContentStatus.released,
            version=2,
        )
    )
    db.flush()
    session = _session(db)

    with client.websocket_connect(f"/roadside/session/{session.id}/stream") as ws:
        ws.send_json({"type": "ready", "driver_state": "IDLE"})
        frame = ws.receive_json()
        ws.send_json({"type": "bye"})

    assert frame["type"] == "officer"
    assert frame["text"] == "RELEASED LINE — where are you headed?"


# --- the client's own condition for showing the entry ---------------------------------


def test_me_says_whether_roadside_is_on(client, db):
    """AI-CONTEXT: the More row hangs off this. A driver app cannot read F13, so the one
    place it can learn a capability exists is `/me` — the same route and the same reason
    as `verification_enabled`.

    Asserted in BOTH directions, because a payload key that is always False looks
    identical to a working gate right up until someone switches the module on.
    """
    _register = client.post(
        "/auth/register",
        json={"email": f"m15-me-{uuid.uuid4().hex[:8]}@example.com", "password": "pw-123456"},
    )
    headers = {"Authorization": f"Bearer {_register.json()['token']}"}

    m15.register_module(db)
    flag = db.get(flags.FeatureFlag, m15.FLAG_KEY)
    db.flush()
    assert client.get("/auth/me", headers=headers).json()["roadside_enabled"] is False

    flag.enabled = True
    db.flush()
    assert client.get("/auth/me", headers=headers).json()["roadside_enabled"] is True
