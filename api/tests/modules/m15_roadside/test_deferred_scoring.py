"""AI-CONTEXT: the rubric runs after the conversation, and a band is never partial.

Measured on the production box: the rubric was 3.41s of a ~5.5s exchange — the largest
single cost in a spoken conversation, spent computing what a driver reads on the RESULT
screen. Moving it off the path is the latency fix; the tests here are about the two ways
that could go wrong rather than about the seconds.

  1. A band computed while some turns are still queued would be derived from "whichever
     ones happened to have finished" — a wrong number wearing a right one's clothes.
  2. A pending turn and a Q-2 exclusion both carry `scores == {}`, and confusing them is
     how (1) would happen silently.
"""

from app.modules.m15_roadside.domain import deferred_scoring
from app.modules.m15_roadside.domain import models as m
from app.modules.m15_roadside.domain import session_loop as loop
from app.modules.m15_roadside.domain.scoring import RubricVerdict


class _Rubric:
    """A rubric that answers, and counts how often the conversation asked it to."""

    def __init__(self):
        self.calls = 0

    def judge(self, *, officer_line, transcript, intent_key,
              canonical_meaning="", required_slots=None):
        # the meaning and the slots are what the model is judged against (entry 208)
        self.last_meaning = canonical_meaning
        self.calls += 1
        return RubricVerdict(
            intent_matched=True, intelligible=True, unknown_terms=[], asked_for_repeat=False
        )


class _Broken:
    def judge(self, **kw):
        from app.modules.m15_roadside.domain.rubric_f9 import RubricUnavailable

        raise RubricUnavailable("the provider is down")


def _setup(db):
    import uuid

    from app.foundation.f01_identity import public as identity

    intent = m.Intent(
        key="destination", domain="stop", canonical_meaning="where they are headed",
        required_slots={"destination": "Dallas"},
    )
    db.add(intent)
    scenario = m.ScenarioVersion(
        version=1, difficulty=m.Difficulty.clear, allowed_intents=["destination"],
        status=m.ContentStatus.released, hidden_state={"destination": "Dallas"},
    )
    db.add(scenario)
    db.flush()
    account = identity.register_account(db, f"def-{uuid.uuid4().hex[:8]}@example.com", "pw-123456")
    session = loop.start_session(db, scenario=scenario, account_id=account.id, consented=True)
    officer = loop.OfficerTurn(
        intent_key="destination", variant_id=None, text="Where are you headed?",
        audio_ref=None, seq=1,
    )
    return session, officer


def test_the_conversation_does_not_ask_the_rubric_anything(db):
    """THE LATENCY FIX ITSELF: the hot path makes no model call at all."""
    session, officer = _setup(db)
    rubric = _Rubric()

    turn = loop.record_driver_turn(
        db, session, officer=officer, transcript="i am headed to dallas",
        asr_confidence=0.95, rubric=None,
    )

    assert rubric.calls == 0
    assert turn.scoring_state == "pending"
    # ...and yet the officer can still say the fact back, because slots are deterministic
    assert turn.observed_slots == {"destination": "Dallas"}


def test_a_turn_q2_already_excluded_is_finished_not_queued(db):
    """A turn nobody could hear is not waiting for an opinion.

    AI-CONTEXT: the distinction migration 0091 exists for. Both this turn and a pending one
    carry `scores == {}`; only `scoring_state` says which is which, and getting it wrong
    would either re-judge an unhearable turn or leave it queued forever.
    """
    session, officer = _setup(db)

    silent = loop.record_driver_turn(
        db, session, officer=officer, transcript="", asr_confidence=0.9, rubric=None,
    )
    assert silent.scores == {}
    assert silent.scoring_state == "done"
    assert "NO_RESPONSE" in silent.failure_tags

    later = loop.OfficerTurn(
        intent_key="destination", variant_id=None, text="Where are you headed?",
        audio_ref=None, seq=3,
    )
    unheard = loop.record_driver_turn(
        db, session, officer=later, transcript="mmf", asr_confidence=0.01, rubric=None,
    )
    assert unheard.scores == {}
    assert unheard.scoring_state == "done"
    assert unheard.review_status is m.TurnReviewStatus.review_needed


def test_settling_fills_in_the_scores_the_conversation_skipped(db):
    session, officer = _setup(db)
    turn = loop.record_driver_turn(
        db, session, officer=officer, transcript="i am headed to dallas",
        asr_confidence=0.95, rubric=None,
    )
    assert turn.scores == {}

    settled = deferred_scoring.settle_session_scores(db, session, rubric=_Rubric())

    assert settled == 1
    assert turn.scoring_state == "done"
    assert turn.scores["comprehension"] == 100
    assert turn.scores["task_completion"] == 100


def test_a_band_is_never_computed_over_a_partial_set(db):
    """THE ONE THIS FILE EXISTS FOR.

    `complete_session` settles before it derives anything. Without that, a session whose
    turns were still queued would be banded on whatever had happened to finish — and the
    driver would be told something about their English that was measured on a subset they
    never chose.
    """
    session, officer = _setup(db)
    loop.record_driver_turn(
        db, session, officer=officer, transcript="i am headed to dallas",
        asr_confidence=0.95, rubric=None,
    )
    assert deferred_scoring.pending_turns(db, session.id)

    loop.complete_session(db, session)

    assert deferred_scoring.pending_turns(db, session.id) == []


def test_a_rubric_outage_becomes_review_needed_and_never_stays_queued(db):
    """Q-2 at the deferred edge, plus the queue-drain rule.

    An outage must not become a verdict about a driver's English; and a turn that cannot be
    settled must not stay pending, because a queue that never drains is a result screen
    that never loads.
    """
    session, officer = _setup(db)
    turn = loop.record_driver_turn(
        db, session, officer=officer, transcript="i am headed to dallas",
        asr_confidence=0.95, rubric=None,
    )

    deferred_scoring.settle_session_scores(db, session, rubric=_Broken())

    assert turn.scoring_state == "done"
    assert turn.review_status is m.TurnReviewStatus.review_needed
    assert turn.scores == {}


def test_settling_twice_changes_nothing(db):
    """The worker and the result path both settle; they must not fight."""
    session, officer = _setup(db)
    loop.record_driver_turn(
        db, session, officer=officer, transcript="i am headed to dallas",
        asr_confidence=0.95, rubric=None,
    )
    rubric = _Rubric()

    assert deferred_scoring.settle_session_scores(db, session, rubric=rubric) == 1
    assert deferred_scoring.settle_session_scores(db, session, rubric=rubric) == 0
    assert rubric.calls == 1
