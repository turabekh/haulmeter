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


def test_the_improvised_line_arrives_before_the_voice_does(client, db, monkeypatch):
    """AI-CONTEXT: THE LATENCY FIX, ASSERTED AT THE SOCKET — which is the only level that
    can see it. Measured on the live APIs: ~3.0s for the model to choose the line, ~1.2s
    for Azure to say it. Serialized behind a single frame that was 4.2s of a screen where
    nobody had spoken. An improvised line is novel every time, so the TTS leg is always a
    cache MISS — it is paid on every turn and cannot be cached away.

    So the text ships the moment it exists and the voice follows on its own frame. The
    `audio_pending` flag is load-bearing rather than cosmetic: without it the surface
    reads a null `audio_url` as "he has finished speaking" and opens the mic over the top
    of him, recording a driver answering a question they have not heard.
    """
    from app.modules.m15_roadside.domain import conversation

    _module_on(db)
    intent = _draft_content(db)
    db.add(
        m.PhraseVariant(
            intent_id=intent.id,
            text="RELEASED LINE",
            difficulty=m.Difficulty.clear,
            status=m.ContentStatus.released,
            version=2,
        )
    )
    db.flush()
    session = _session(db)

    monkeypatch.setattr(
        m15_api.conversation,
        "conversational_officer",
        lambda db_, s: conversation.ImprovisedTurn(
            line="Let me see your logbook.", intent_key="destination", done=False
        ),
    )
    monkeypatch.setattr(m15_api.conversation, "officer_mode", lambda db_: "llm")
    synthesized = []

    def _synth(db_, text):
        synthesized.append(text)
        return uuid.uuid4()

    monkeypatch.setattr(m15_api.m15_audio, "fragment_audio", _synth)

    with client.websocket_connect(f"/roadside/session/{session.id}/stream") as ws:
        ws.send_json({"type": "ready", "driver_state": "IDLE"})
        first = ws.receive_json()
        second = ws.receive_json()
        ws.send_json({"type": "bye"})

    # the words, with nothing to wait for except a promise that the voice is coming
    assert first["type"] == "officer"
    assert first["text"] == "Let me see your logbook."
    assert first["audio_url"] is None
    assert first["audio_pending"] is True

    # then the voice, on its own frame, tied to the same turn
    assert second["type"] == "officer_audio"
    assert second["seq"] == first["seq"]
    assert second["audio_url"] is not None
    assert synthesized == ["Let me see your logbook."]


def test_a_voice_that_fails_to_synthesize_still_releases_the_driver(client, db, monkeypatch):
    """The frame goes out with a null url rather than not going out at all. A driver whose
    officer lost his voice can still read the question and answer it; one waiting on a
    frame that never arrives has a hung screen and a mic that never opens."""
    from app.modules.m15_roadside.domain import conversation

    _module_on(db)
    intent = _draft_content(db)
    db.add(
        m.PhraseVariant(
            intent_id=intent.id,
            text="RELEASED LINE",
            difficulty=m.Difficulty.clear,
            status=m.ContentStatus.released,
            version=2,
        )
    )
    db.flush()
    session = _session(db)

    monkeypatch.setattr(
        m15_api.conversation,
        "conversational_officer",
        lambda db_, s: conversation.ImprovisedTurn(
            line="Let me see your logbook.", intent_key="destination", done=False
        ),
    )
    monkeypatch.setattr(m15_api.conversation, "officer_mode", lambda db_: "llm")

    def _boom(db_, text):
        raise RuntimeError("azure is down")

    monkeypatch.setattr(m15_api.m15_audio, "fragment_audio", _boom)

    with client.websocket_connect(f"/roadside/session/{session.id}/stream") as ws:
        ws.send_json({"type": "ready", "driver_state": "IDLE"})
        first = ws.receive_json()
        second = ws.receive_json()
        ws.send_json({"type": "bye"})

    assert first["text"] == "Let me see your logbook."
    assert second["type"] == "officer_audio"
    assert second["audio_url"] is None


def test_a_lost_voice_on_the_closing_line_does_not_eat_the_verdict(client, db, monkeypatch):
    """RED-FIRST: this failed before the guard existed, and it failed by CRASHING.

    AI-CONTEXT: the closing frame is the only thing that sends a driver to their result
    screen, and it was built with an unguarded `fragment_audio` call inline in the dict.
    Azure failing on the last line of a stop raised out of `_officer_frame`, so the frame
    never went and the socket closed — and the surface reads an unexpected close as
    FAILED. The verdict was already committed one line above. A finished stop, a saved
    score, and a failure screen. A missing voice may cost the closing words; it may never
    cost the result.
    """
    from app.modules.m15_roadside.domain import conversation

    _module_on(db)
    intent = _draft_content(db)
    db.add(
        m.PhraseVariant(
            intent_id=intent.id,
            text="RELEASED LINE",
            difficulty=m.Difficulty.clear,
            status=m.ContentStatus.released,
            version=2,
        )
    )
    db.flush()
    session = _session(db)

    monkeypatch.setattr(
        m15_api.conversation,
        "conversational_officer",
        lambda db_, s: conversation.ImprovisedTurn(
            line="Alright, you're good to go.", intent_key="", done=True
        ),
    )
    monkeypatch.setattr(m15_api.conversation, "officer_mode", lambda db_: "llm")

    def _boom(db_, text):
        raise RuntimeError("azure is down")

    monkeypatch.setattr(m15_api.m15_audio, "fragment_audio", _boom)

    with client.websocket_connect(f"/roadside/session/{session.id}/stream") as ws:
        ws.send_json({"type": "ready", "driver_state": "IDLE"})
        frame = ws.receive_json()
        ws.send_json({"type": "bye"})

    # the stop ENDS, with words and a band, and only the voice is missing
    assert frame["type"] == "complete"
    assert frame["closing"] == "Alright, you're good to go."
    assert frame["closing_audio_url"] is None
    assert frame["band"]


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


# --- the teaching loop over HTTP (M15-FR5) ---------------------------------------------


def _coachable_session(db):
    """A session with one missed intent, and two released phrasings so a retest exists."""
    intent = m.Intent(
        key="hos", domain="paperwork", canonical_meaning="hours driven", required_slots={}
    )
    db.add(intent)
    db.flush()
    asked = m.PhraseVariant(
        intent_id=intent.id, text="How many hours have you been driving today?",
        difficulty=m.Difficulty.clear, status=m.ContentStatus.released,
    )
    other = m.PhraseVariant(
        intent_id=intent.id, text="How long you been behind the wheel?",
        difficulty=m.Difficulty.clear, status=m.ContentStatus.released, version=2,
    )
    scenario = m.ScenarioVersion(
        version=1, difficulty=m.Difficulty.clear,
        allowed_intents=["hos"], status=m.ContentStatus.released,
    )
    db.add_all([asked, other, scenario])
    db.flush()
    session = loop.start_session(
        db, scenario=scenario, account_id=_account(db).id, consented=True
    )
    db.add_all([
        m.Turn(session_id=session.id, seq=1, speaker=m.Speaker.officer,
               intent_id=intent.id, transcript=asked.text),
        m.Turn(session_id=session.id, seq=2, speaker=m.Speaker.driver,
               intent_id=intent.id, transcript="uh, furniture",
               failure_tags=["INTENT_MISUNDERSTOOD"]),
    ])
    db.flush()
    return session, intent, other


def test_the_coaching_route_returns_the_loop_for_each_miss(client, db):
    _module_on(db)
    session, _intent, other = _coachable_session(db)

    body = client.get(f"/roadside/session/{session.id}/coaching?locale=uz").json()

    assert len(body["coaching"]) == 1
    plan = body["coaching"][0]
    assert plan["missed_question"] == "How many hours have you been driving today?"
    assert [p["text"] for p in plan["phrase_family"]] == ["How long you been behind the wheel?"]
    assert plan["retest_variant_id"] == str(other.id)


def test_the_route_carries_Q9_rather_than_falling_back_to_english(client, db):
    """`explanation: null` is the honest state, and the surface renders it as "not yet in
    your language". A route that substituted the English row would defeat Q-9 in a place
    no domain test would see."""
    _module_on(db)
    session, intent, _other = _coachable_session(db)
    db.add(m.CoachingContent(
        intent_id=intent.id, locale="en", explanation="AN ENGLISH EXPLANATION",
        review_status=m.ContentStatus.released,
    ))
    db.flush()

    plan = client.get(f"/roadside/session/{session.id}/coaching?locale=uz").json()["coaching"][0]

    assert plan["explanation"] is None


def test_an_audio_url_is_signed_when_a_line_has_a_voice(client, db):
    """The officer-audio URL bug (entry 183) again, one layer over: a hand-built path here
    would 422 in the player exactly as it did in the socket."""
    _module_on(db)
    session, intent, other = _coachable_session(db)
    from app.foundation.f06_documents import public as documents

    doc = documents.store_document(
        db, _account(db).id, documents.DocType.other, b"ID3x",
        filename="x.mp3", content_type="audio/mpeg",
    )
    other.audio_ref = doc.id
    db.flush()

    plan = client.get(f"/roadside/session/{session.id}/coaching?locale=uz").json()["coaching"][0]
    url = plan["phrase_family"][0]["audio_url"]

    assert "sig=" in url and "exp=" in url, "an unsigned media URL is a 422 in the player"


def _rubric_saying(intent_matched: bool):
    class _Stub:
        def __init__(self, *a, **kw):
            pass

        def judge(self, *, officer_line, transcript, intent_key):
            from app.modules.m15_roadside.domain.scoring import RubricVerdict

            return RubricVerdict(intent_matched=intent_matched, intelligible=True)

    return _Stub


def _answering_session(db):
    """A released question, an open session, and one officer turn already asked."""
    _module_on(db)
    intent = _draft_content(db)
    db.add(m.PhraseVariant(
        intent_id=intent.id, text="Where are you headed?",
        difficulty=m.Difficulty.clear, status=m.ContentStatus.released, version=2,
    ))
    db.add(m.OfficerAck(text="Okay.", kind="ack", status=m.ContentStatus.released))
    db.flush()
    session = _session(db)
    db.add(m.Turn(
        session_id=session.id, seq=1, speaker=m.Speaker.officer,
        intent_id=intent.id, transcript="Where are you headed?",
    ))
    db.flush()
    return session


def _scored_frame(client, session, transcript):
    with client.websocket_connect(f"/roadside/session/{session.id}/stream") as ws:
        ws.send_json({"type": "answer", "transcript": transcript, "driver_state": "IDLE"})
        frame = ws.receive_json()
        ws.send_json({"type": "bye"})
    return frame


def test_no_acknowledgement_when_a_clarification_is_coming(client, db, monkeypatch):
    """AI-CONTEXT: measured on a live session, not reasoned about. The officer said
    "Thank you." and then "I'm asking how long you've been driving today, not where you're
    headed." Nobody thanks you and then corrects you in the same breath — when the answer
    missed the question, the repair IS the response and an ack in front of it is a machine
    being polite on a schedule.
    """
    monkeypatch.setattr(m15_api, "F9Rubric", _rubric_saying(False))
    session = _answering_session(db)

    frame = _scored_frame(client, session, "I am hauling furniture")

    assert "INTENT_MISUNDERSTOOD" in frame["tags"]
    assert frame["ack"] is None


def test_an_answer_that_landed_still_gets_acknowledged(client, db, monkeypatch):
    """The control. Without it the assertion above would also pass on a socket that had
    quietly stopped acknowledging anything at all."""
    monkeypatch.setattr(m15_api, "F9Rubric", _rubric_saying(True))
    session = _answering_session(db)

    frame = _scored_frame(client, session, "I am headed to Chicago")

    assert "INTENT_MISUNDERSTOOD" not in frame["tags"]
    assert frame["ack"] == "Okay."


def test_the_first_officer_frame_carries_the_greeting(client, db, monkeypatch):
    """A stop OPENS. This lived on `POST /session` — answered by the CONSENT screen, which
    meant a driver would have heard "Afternoon" while still deciding whether to agree to be
    recorded, and the session surface never received it at all."""
    _module_on(db)
    intent = _draft_content(db)
    db.add(m.PhraseVariant(
        intent_id=intent.id, text="Where are you headed?",
        difficulty=m.Difficulty.clear, status=m.ContentStatus.released, version=2,
    ))
    db.add(m.OfficerAck(
        text="Afternoon. Just a routine check.", kind="opening", status=m.ContentStatus.released
    ))
    db.flush()
    session = _session(db)

    with client.websocket_connect(f"/roadside/session/{session.id}/stream") as ws:
        ws.send_json({"type": "ready", "driver_state": "IDLE"})
        first = ws.receive_json()
        ws.send_json({"type": "ready", "driver_state": "IDLE"})
        second = ws.receive_json()
        ws.send_json({"type": "bye"})

    assert first["opening"] == "Afternoon. Just a routine check."
    # and only once — an officer who greets you before every question is a machine
    assert second.get("opening") is None


def test_the_scored_frame_carries_the_echo_and_the_ack(client, db, monkeypatch):
    """The fields the surface plays back. A frame that stopped carrying them would leave
    the officer silent between questions and nothing would fail — which is exactly what
    happened when a UI edit silently no-opped."""
    monkeypatch.setattr(m15_api, "F9Rubric", _rubric_saying(True))
    session = _answering_session(db)

    frame = _scored_frame(client, session, "I am headed to Chicago")

    assert "echo" in frame and "echo_audio_url" in frame
    assert "ack" in frame and "ack_audio_url" in frame
