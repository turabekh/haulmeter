"""AI-CONTEXT: the improvising officer (entry 189) — and what he is still not allowed to do.

Q-6 was amended for the LIVE SIMULATION, not repealed. The compensating controls are the
prompt's prohibitions, a config kill switch, and the scoring separation — and the last of
those is the one code can hold, so it is what these tests are mostly about.

The model chooses WHAT IS SAID. It does not choose what anything is WORTH: the driver's
answer is still validated against the intent's expected slots from the scenario's hidden
state and scored by `score_turn`. A model that could set a score would BE the scoring
policy, and a version change would silently alter what a driver is told about their English.
"""

import pytest

from app.modules.m15_roadside.domain import conversation
from app.modules.m15_roadside.domain import models as m
from app.modules.m15_roadside.domain import session_loop as loop


def _scenario(db, keys, hidden=None):
    scenario = m.ScenarioVersion(
        version=1,
        difficulty=m.Difficulty.clear,
        allowed_intents=list(keys),
        status=m.ContentStatus.released,
        hidden_state=hidden or {"destination": "Chicago", "hours": "6"},
    )
    db.add(scenario)
    db.flush()
    return scenario


def _intent(db, key):
    intent = m.Intent(
        key=key, domain="stop", canonical_meaning=key, required_slots={"destination": "Chicago"}
    )
    db.add(intent)
    db.flush()
    return intent


def _session(db, scenario):
    import uuid

    from app.foundation.f01_identity import public as identity

    account = identity.register_account(db, f"conv-{uuid.uuid4().hex[:8]}@example.com", "pw-123456")
    return loop.start_session(db, scenario=scenario, account_id=account.id, consented=True)


def test_the_model_picks_the_line_and_the_module_keeps_the_facts(db, monkeypatch):
    """THE SEPARATION THIS FILE EXISTS FOR. The officer improvises the question; the
    expected answer still comes from the scenario's hidden state, so scoring is checked
    against the facts of this stop rather than the model's opinion of them."""
    intent = _intent(db, "destination")
    scenario = _scenario(db, ["destination"])
    session = _session(db, scenario)

    turn = loop.record_improvised_officer_turn(
        db,
        session,
        conversation.ImprovisedTurn(line="So where's this load going?", intent_key="destination"
                                    , done=False),
    )

    assert turn.transcript == "So where's this load going?"
    assert turn.intent_id == intent.id
    # the FACT, from the scenario — not anything the model said
    assert turn.expected_slots == {"destination": "Chicago"}


def test_an_intent_the_model_invented_is_stored_as_nothing(db):
    """A turn with no intent scores nothing, which is right for a line that could not be
    tied to a topic. Inventing one would attach a driver's answer to a question nobody
    asked."""
    scenario = _scenario(db, ["destination"])
    _intent(db, "destination")
    session = _session(db, scenario)

    turn = loop.record_improvised_officer_turn(
        db, session, conversation.ImprovisedTurn(line="Nice truck.", intent_key="vibes", done=False)
    )

    assert turn.intent_id is None
    assert turn.expected_slots == {}


def test_a_reply_the_gateway_rejects_raises_rather_than_inventing(db, monkeypatch):
    """The caller falls back to the SCRIPTED loop — reviewed content that always works —
    rather than to silence or to a guessed line."""
    scenario = _scenario(db, ["destination"])
    _intent(db, "destination")
    session = _session(db, scenario)

    def _boom(*a, **kw):
        raise conversation.ai.StructuredOutputError("missing required keys: ['line']")

    monkeypatch.setattr(conversation.ai, "parse_structured", _boom)
    monkeypatch.setattr(conversation.ai, "resolve_provider", lambda: object())

    with pytest.raises(conversation.OfficerUnavailable):
        conversation.conversational_officer(db, session)


def test_an_empty_line_is_a_failure_not_a_silent_officer(db, monkeypatch):
    """A schema guarantees the KEY is there; it cannot guarantee the key says anything.
    An officer who says "" would be a turn where the screen waits and nobody speaks."""
    scenario = _scenario(db, ["destination"])
    _intent(db, "destination")
    session = _session(db, scenario)
    monkeypatch.setattr(
        conversation.ai,
        "parse_structured",
        lambda *a, **kw: {"line": "  ", "intent_key": "destination", "done": False},
    )
    monkeypatch.setattr(conversation.ai, "resolve_provider", lambda: object())

    with pytest.raises(conversation.OfficerUnavailable):
        conversation.conversational_officer(db, session)


def test_the_turn_is_asked_for_under_a_schema(db, monkeypatch):
    """The reply is a GUARANTEED object rather than a fenced-JSON hunt.

    AI-CONTEXT: this is a robustness test, not a latency one — worth saying because the
    schema was added while chasing latency and turned out not to be where the seconds
    were (module docstring has the measurements). What it does buy is that a stray code
    fence can no longer end a driver's turn mid-stop, which used to be a real failure the
    old `_parse` existed to paper over.
    """
    scenario = _scenario(db, ["destination"])
    _intent(db, "destination")
    session = _session(db, scenario)
    seen = {}

    def _record(db_, provider, module, prompt_key, context, **kw):
        seen.update(kw, module=module, prompt_key=prompt_key)
        return {"line": "Where to?", "intent_key": "destination", "done": False}

    monkeypatch.setattr(conversation.ai, "parse_structured", _record)
    monkeypatch.setattr(conversation.ai, "resolve_provider", lambda: object())

    assert conversation.conversational_officer(db, session).line == "Where to?"
    assert seen["schema"] == conversation.OFFICER_SCHEMA
    assert seen["schema"]["required"] == ["line", "intent_key", "done"]
    assert seen["required_keys"] == ["line", "intent_key", "done"]


def test_the_schema_and_effort_reach_the_wire_not_just_the_call_site(monkeypatch):
    """What the gateway actually PUTS IN THE REQUEST BODY.

    AI-CONTEXT: asserted on the body rather than by reading `parse_structured`'s source,
    because a test that greps its own codebase passes on text that no longer reaches
    anyone — TRAPS 79, which cost this module a release. So this builds the real request
    and reads `output_config` out of the JSON that would have gone to Anthropic.
    """
    import httpx

    from app.foundation.f09_ai_gateway.domain import provider as prov

    sent = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "content": [{"type": "text", "text": '{"line": "Where to?"}'}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }

    def _post(url, headers=None, json=None, timeout=None):
        sent.update(json)
        return _Resp()

    monkeypatch.setattr(httpx, "post", _post)

    provider = prov.AnthropicModelProvider("k", "claude-opus-5")
    provider.parse_structured("say something", {"json_schema": conversation.OFFICER_SCHEMA})

    assert sent["output_config"]["effort"] == "low"
    assert sent["output_config"]["format"]["schema"] == conversation.OFFICER_SCHEMA

    # and the schema-less path is untouched: `complete` still carries no effort, so this
    # is a change to ONE caller rather than a quiet re-tuning of every module's AI calls
    sent.clear()
    provider.complete("say something", {})
    assert "output_config" not in sent


def test_the_kill_switch_is_a_config_key(db):
    """AI-CONTEXT: the control that makes an unreviewed officer survivable. Q-6 was amended
    for the live simulation, and the compensating control is an operator who can revert to
    reviewed content in seconds rather than waiting for a build."""
    from app.foundation.f13_flags import public as flags

    assert conversation.officer_mode(db) == "llm"
    flags.set_config(db, conversation.OFFICER_MODE_KEY, "scripted")
    db.flush()
    assert conversation.officer_mode(db) == "scripted"


def test_the_prompt_forbids_the_two_things_that_would_hurt_a_driver(db):
    """The prompt IS the review a human would otherwise have done, so the prohibitions are
    asserted rather than trusted: an officer who states the law has told a driver something
    they will act on, and one who marks their English has both scored them and scored the
    wrong thing (Q-1)."""
    from app.modules.m15_roadside.domain import officer_prompt

    text = officer_prompt.PROMPT_TEMPLATE
    assert "NEVER state a rule" in text
    assert "regulation as fact" in text
    assert "NEVER comment on their English" in text
    assert "accent" in text
