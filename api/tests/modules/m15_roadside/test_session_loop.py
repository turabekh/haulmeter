"""AI-CONTEXT: the loop's three refusals and its branch selection (M15-FR2/FR3, Q-2/Q-4/Q-6).

Four laws meet in this file and each is written as the failure it prevents:

  Q-4  a session must refuse to start in motion AND hard-pause mid-session
  Q-2  a turn below the ASR floor is REVIEW_NEEDED, excluded from bands, never a failure
  Q-6  draft content has no path to a driver — and an empty released pool RAISES rather
       than quietly falling back, because a silent fallback is how draft would reach one
  M15-FR3  no consent, no mic — checked before anything else

`test_the_production_path_cannot_reach_draft_content` is the one that matters most. The
dev seam `allow_draft` exists so the engine can be exercised against DEV_SEED content, and
the whole safety of that arrangement is that nothing in the request path passes it. The
test asserts the default, which is the same structural technique Q-3 uses for org queries.
"""

import uuid

import pytest

from app.foundation.f01_identity import public as identity
from app.modules.m15_roadside.domain import models as m
from app.modules.m15_roadside.domain import session_loop as loop
from app.modules.m15_roadside.domain.scoring import DeterministicRubric
from app.modules.m15_roadside.domain.session_loop import DriverState

INTENTS = [
    ("destination", "the driver states where they are headed", {"destination": "Chicago"}),
    ("hos_hours_driven", "hours driven today", {"hours": "6"}),
]


def _scenario(db, *, keys=None):
    scenario = m.ScenarioVersion(
        version=1,
        difficulty=m.Difficulty.clear,
        allowed_intents=keys or [k for k, _, _ in INTENTS],
        status=m.ContentStatus.draft,
    )
    db.add(scenario)
    db.flush()
    return scenario


def _content(db, *, status=m.ContentStatus.draft):
    for key, meaning, slots in INTENTS:
        intent = m.Intent(
            key=key, domain="stop", canonical_meaning=meaning, required_slots=slots
        )
        db.add(intent)
        db.flush()
        db.add(
            m.PhraseVariant(
                intent_id=intent.id,
                text=f"officer line for {key}",
                difficulty=m.Difficulty.clear,
                status=status,
            )
        )
        db.add(
            m.PhraseVariant(
                intent_id=intent.id,
                text=f"holdout line for {key}",
                difficulty=m.Difficulty.clear,
                status=status,
                holdout=True,
            )
        )
    db.flush()


def _account(db):
    return identity.register_account(db, f"loop-{uuid.uuid4().hex[:8]}@example.com", "pw-123456")


def _open(db, scenario, **kw):
    kw.setdefault("consented", True)
    return loop.start_session(db, scenario=scenario, account_id=_account(db).id, **kw)


# --- consent (M15-FR3) ----------------------------------------------------------------


def test_no_consent_no_session(db):
    """Consent is checked FIRST — asking after recording has begun is not consent."""
    scenario = _scenario(db)
    with pytest.raises(loop.ConsentRequired):
        loop.start_session(db, scenario=scenario, account_id=_account(db).id, consented=False)


def test_consent_is_recorded_on_the_session(db):
    scenario = _scenario(db)
    session = _open(db, scenario)
    assert session.consent_at is not None


def test_consent_is_checked_before_motion(db):
    """Both are wrong; the driver should be told about consent, which they can act on."""
    scenario = _scenario(db)
    with pytest.raises(loop.ConsentRequired):
        loop.start_session(
            db,
            scenario=scenario,
            account_id=_account(db).id,
            consented=False,
            driver_state=DriverState.DRIVING,
        )


# --- Q-4: nothing interactive in motion -------------------------------------------------


def test_a_session_refuses_to_start_in_motion(db):
    scenario = _scenario(db)
    with pytest.raises(loop.RefusedInMotion):
        loop.start_session(
            db,
            scenario=scenario,
            account_id=_account(db).id,
            consented=True,
            driver_state=DriverState.DRIVING,
        )


def test_a_session_hard_pauses_mid_turn(db):
    """The state flips DURING a session — the case E3's validation names.

    Stricter than M11's defer-confirm: there is nothing to defer, because a simulation
    resumed later is a different simulation.
    """
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination"])
    session = _open(db, scenario)

    officer = loop.next_officer_turn(db, session, driver_state=DriverState.IDLE)
    assert officer is not None

    with pytest.raises(loop.RefusedInMotion):
        loop.record_driver_turn(
            db,
            session,
            officer=officer,
            transcript="Chicago",
            asr_confidence=0.9,
            rubric=DeterministicRubric(),
            driver_state=DriverState.DRIVING,
        )


def test_resting_and_on_site_are_not_refused(db):
    """Only DRIVING refuses — a parked driver at a dock is exactly the intended user."""
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination"])
    for state in (DriverState.IDLE, DriverState.ON_SITE, DriverState.RESTING):
        session = _open(db, scenario, driver_state=state)
        assert session.id is not None


# --- Q-6: draft content has no path to a driver ------------------------------------------


def test_the_production_path_cannot_reach_draft_content(db):
    """The assertion this file exists for.

    `allow_draft` defaults False and nothing in the request path passes it. With only
    draft content present, the loop RAISES — it does not quietly serve the draft, which is
    precisely how draft would reach a driver.
    """
    _content(db, status=m.ContentStatus.draft)
    scenario = _scenario(db, keys=["destination"])
    session = _open(db, scenario)

    with pytest.raises(loop.NoContentAvailable):
        loop.next_officer_turn(db, session)


def test_the_dev_seam_serves_draft_only_when_explicitly_asked(db):
    _content(db, status=m.ContentStatus.draft)
    scenario = _scenario(db, keys=["destination"])
    session = _open(db, scenario)

    officer = loop.next_officer_turn(db, session, allow_draft=True)
    assert officer is not None
    assert officer.intent_key == "destination"


def test_q5_holds_even_inside_the_dev_seam(db):
    """A holdout must not leak just because the dev path is open."""
    _content(db, status=m.ContentStatus.draft)
    scenario = _scenario(db, keys=["destination"])
    session = _open(db, scenario)

    seen = set()
    for _ in range(4):
        officer = loop.next_officer_turn(db, session, allow_draft=True)
        if officer is None:
            break
        seen.add(officer.text)
    assert not any("holdout" in t for t in seen)


# --- branch selection ---------------------------------------------------------------------


def test_the_scenario_drives_which_intents_are_asked_and_in_order(db):
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db)
    session = _open(db, scenario)

    first = loop.next_officer_turn(db, session)
    assert first.intent_key == "destination"
    loop.record_driver_turn(
        db,
        session,
        officer=first,
        transcript="Chicago",
        asr_confidence=0.9,
        rubric=DeterministicRubric(),
    )
    second = loop.next_officer_turn(db, session)
    assert second.intent_key == "hos_hours_driven"


def test_the_scenario_ends_when_every_intent_has_been_asked(db):
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db)
    session = _open(db, scenario)
    for _ in range(len(INTENTS)):
        assert loop.next_officer_turn(db, session) is not None
    assert loop.next_officer_turn(db, session) is None


# --- Q-2 at the loop ---------------------------------------------------------------------


def test_a_turn_below_the_floor_is_review_needed_and_scores_nothing(db):
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination"])
    session = _open(db, scenario)
    officer = loop.next_officer_turn(db, session)

    turn = loop.record_driver_turn(
        db,
        session,
        officer=officer,
        transcript="mmmf",
        asr_confidence=0.2,
        rubric=DeterministicRubric(),
    )
    assert turn.review_status is m.TurnReviewStatus.review_needed
    assert turn.scores == {}
    assert loop.review_needed_count(db, session) == 1


def test_unheard_turns_do_not_drag_the_band_down(db):
    """Q-2 reaching the band: the driver said the same things either way."""
    _content(db, status=m.ContentStatus.released)

    good = _scenario(db, keys=["destination"])
    s1 = _open(db, good)
    o1 = loop.next_officer_turn(db, s1)
    loop.record_driver_turn(
        db, s1, officer=o1, transcript="Chicago", asr_confidence=0.95,
        rubric=DeterministicRubric(),
    )
    band_clean = loop.complete_session(db, s1)

    noisy = _scenario(db, keys=["destination", "hos_hours_driven"])
    s2 = _open(db, noisy)
    o2 = loop.next_officer_turn(db, s2)
    loop.record_driver_turn(
        db, s2, officer=o2, transcript="Chicago", asr_confidence=0.95,
        rubric=DeterministicRubric(),
    )
    o3 = loop.next_officer_turn(db, s2)
    loop.record_driver_turn(
        db, s2, officer=o3, transcript="mmf", asr_confidence=0.1,
        rubric=DeterministicRubric(),
    )
    band_noisy = loop.complete_session(db, s2)

    assert band_noisy.score == band_clean.score
    assert band_noisy.band is band_clean.band


# --- completion ----------------------------------------------------------------------------


def test_completing_writes_the_band_and_keeps_provisional(db):
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination"])
    session = _open(db, scenario)
    officer = loop.next_officer_turn(db, session)
    loop.record_driver_turn(
        db, session, officer=officer, transcript="Chicago", asr_confidence=0.95,
        rubric=DeterministicRubric(),
    )

    verdict = loop.complete_session(db, session)
    assert session.completed_at is not None
    assert session.band == verdict.band.value
    assert session.provisional is True, "uncalibrated bands stay provisional (Q-8)"


# --- hidden state: the defect a real session found ---------------------------------------


def test_expected_slots_come_from_the_scenarios_facts_not_the_slot_names(db):
    """The bug a live probe found and no unit test could.

    `intent.required_slots` names WHICH facts a question needs; the scenario's
    `hidden_state` holds what they ARE. The first implementation used the former as the
    answer key, so a driver who said "six hours today" was checked against the literal
    string "required" and scored `answer_completeness: 0` — told they answered
    incompletely when they had answered perfectly.

    Every earlier test passed because each supplied its own expected slots directly. This
    one goes through `next_officer_turn`, which is where the resolution actually happens.
    """
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination"])
    scenario.hidden_state = {"destination": "Chicago"}
    db.flush()
    session = _open(db, scenario)

    officer = loop.next_officer_turn(db, session)
    turn = loop.record_driver_turn(
        db, session, officer=officer, transcript="I am going to Chicago",
        asr_confidence=0.95, rubric=DeterministicRubric(),
    )

    assert turn.expected_slots == {"destination": "Chicago"}
    assert turn.observed_slots == {"destination": "Chicago"}
    assert turn.scores["answer_completeness"] == 100, (
        "a driver who named the destination must not be scored incomplete"
    )
    assert turn.scores["task_completion"] == 100


def test_a_slot_the_scenario_has_no_fact_for_is_dropped_not_left_unanswerable(db):
    """A question we cannot mark cannot be failed."""
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination"])
    scenario.hidden_state = {}  # no facts at all
    db.flush()
    session = _open(db, scenario)

    officer = loop.next_officer_turn(db, session)
    turn = loop.record_driver_turn(
        db, session, officer=officer, transcript="I am going to Chicago",
        asr_confidence=0.95, rubric=DeterministicRubric(),
    )
    assert turn.expected_slots == {}
    assert turn.scores["answer_completeness"] == 100


# --- the officer asks again (M15-FR2/FR3) ---------------------------------------------


def _driver_turn(db, session, officer, *, tags, transcript="..."):
    """A driver turn with chosen tags — the scorer's own output is exercised elsewhere;
    what these tests are about is what the LOOP does with it."""
    from app.modules.m15_roadside.domain.models import Speaker

    intent = db.query(m.Intent).filter(m.Intent.key == officer.intent_key).first()
    turn = m.Turn(
        session_id=session.id,
        seq=officer.seq + 1,
        speaker=Speaker.driver,
        intent_id=intent.id,
        transcript=transcript,
        failure_tags=list(tags),
    )
    db.add(turn)
    db.flush()
    return turn


def test_asking_the_officer_to_repeat_gets_the_question_again(db):
    """THE ONE THIS EXISTS FOR.

    The scorer already recognises "sorry, could you say that again?" and tags it
    REPETITION_REQUIRED — diagnostic, never a failure. The loop then asked something else
    entirely, which taught a driver that asking for a repeat makes things worse.
    """
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination", "hos_hours_driven"])
    session = _open(db, scenario)

    first = loop.next_officer_turn(db, session)
    _driver_turn(db, session, first, tags=["REPETITION_REQUIRED"])
    second = loop.next_officer_turn(db, session)

    assert second.intent_key == first.intent_key, "the officer moved on instead of repeating"


def test_a_repeat_rephrases_rather_than_echoing(db):
    """Hearing the identical sentence twice teaches nothing about understanding it, and
    the second phrasing is often the one that lands.

    Needs TWO teachable phrasings — `_content` seeds one plus a holdout, and a holdout can
    never be spoken (Q-5). With a single-phrasing pool the loop correctly falls back to
    saying it again, which is the behaviour asserted one test down.
    """
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination"])
    intent = db.query(m.Intent).filter(m.Intent.key == "destination").first()
    db.add(
        m.PhraseVariant(
            intent_id=intent.id,
            text="a second way of asking where you are headed",
            difficulty=m.Difficulty.clear,
            status=m.ContentStatus.released,
            version=2,
        )
    )
    db.flush()
    session = _open(db, scenario)

    first = loop.next_officer_turn(db, session)
    _driver_turn(db, session, first, tags=["UNINTELLIGIBLE"])
    second = loop.next_officer_turn(db, session)

    assert second.intent_key == first.intent_key
    assert second.text != first.text, "the officer said the same words again"


def test_a_repeat_says_it_again_when_there_is_no_other_phrasing(db):
    """The fallback. An intent with one released line must still be repeatable — refusing
    to repeat because the pool is thin would drop the driver's request on the floor."""
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination"])
    session = _open(db, scenario)

    first = loop.next_officer_turn(db, session)
    _driver_turn(db, session, first, tags=["REPETITION_REQUIRED"])
    second = loop.next_officer_turn(db, session)

    assert second.intent_key == first.intent_key
    assert second.text == first.text


def test_silence_also_gets_the_question_again(db):
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination", "hos_hours_driven"])
    session = _open(db, scenario)

    first = loop.next_officer_turn(db, session)
    _driver_turn(db, session, first, tags=["NO_RESPONSE"], transcript="")

    assert loop.next_officer_turn(db, session).intent_key == first.intent_key


def test_a_wrong_answer_does_NOT_get_the_question_again(db):
    """An officer who re-asks until you get it right is running a quiz. E3's taxonomy
    carries 'misunderstood' as a FINDING, not as something to drill on the spot."""
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination", "hos_hours_driven"])
    session = _open(db, scenario)

    first = loop.next_officer_turn(db, session)
    _driver_turn(db, session, first, tags=["INTENT_MISUNDERSTOOD"])

    assert loop.next_officer_turn(db, session).intent_key != first.intent_key


def test_the_officer_moves_on_after_one_repeat(db):
    """A dead microphone must not trap a driver in a loop forever — and a real officer
    at a real window moves on too."""
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination", "hos_hours_driven"])
    session = _open(db, scenario)

    first = loop.next_officer_turn(db, session)
    _driver_turn(db, session, first, tags=["NO_RESPONSE"])
    second = loop.next_officer_turn(db, session)
    assert second.intent_key == first.intent_key

    _driver_turn(db, session, second, tags=["NO_RESPONSE"])
    third = loop.next_officer_turn(db, session)
    assert third.intent_key != first.intent_key, "the officer asked a third time"


def test_a_good_answer_moves_the_conversation_on(db):
    """The control. Without it every assertion above would also pass on a loop that
    repeats the first question forever."""
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination", "hos_hours_driven"])
    session = _open(db, scenario)

    first = loop.next_officer_turn(db, session)
    _driver_turn(db, session, first, tags=[])

    assert loop.next_officer_turn(db, session).intent_key != first.intent_key


# --- the repair branch (M15-FR2) --------------------------------------------------------


def _repair(db, intent_key, text="I'm asking how long you've been driving today."):
    intent = db.query(m.Intent).filter(m.Intent.key == intent_key).first()
    line = m.RepairLine(intent_id=intent.id, text=text, status=m.ContentStatus.released)
    db.add(line)
    db.flush()
    return line


def test_answering_the_wrong_question_gets_a_clarification(db):
    """FR2's repair branch, and its validation says "at least one reached and recovered
    from". The loop used to shrug at a misunderstanding and ask something else — which no
    officer does. Entry 184 was right that a wrong answer must not get the same question
    REPEATED, and wrong that it should get nothing.
    """
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination", "hos_hours_driven"])
    session = _open(db, scenario)
    repair = _repair(db, "destination", "I'm asking where you're going.")

    first = loop.next_officer_turn(db, session)
    _driver_turn(db, session, first, tags=["INTENT_MISUNDERSTOOD"])
    second = loop.next_officer_turn(db, session)

    assert second.text == repair.text
    assert second.intent_key == first.intent_key


def test_the_officer_clarifies_once_and_then_moves_on(db):
    """A second clarification of the same question is the quiz entry 184 warned about."""
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination", "hos_hours_driven"])
    session = _open(db, scenario)
    _repair(db, "destination", "I'm asking where you're going.")

    first = loop.next_officer_turn(db, session)
    _driver_turn(db, session, first, tags=["INTENT_MISUNDERSTOOD"])
    second = loop.next_officer_turn(db, session)
    _driver_turn(db, session, second, tags=["INTENT_MISUNDERSTOOD"])
    third = loop.next_officer_turn(db, session)

    assert third.intent_key != first.intent_key


def test_an_unreleased_repair_is_never_spoken(db):
    """Q-6 reaches the repair branch like everything else a driver hears."""
    _content(db, status=m.ContentStatus.released)
    scenario = _scenario(db, keys=["destination", "hos_hours_driven"])
    session = _open(db, scenario)
    intent = db.query(m.Intent).filter(m.Intent.key == "destination").first()
    db.add(m.RepairLine(
        intent_id=intent.id, text="a drafted clarification", status=m.ContentStatus.draft
    ))
    db.flush()

    first = loop.next_officer_turn(db, session)
    _driver_turn(db, session, first, tags=["INTENT_MISUNDERSTOOD"])
    second = loop.next_officer_turn(db, session)

    assert second.text != "a drafted clarification"
    assert second.intent_key != first.intent_key, "no repair released, so the stop moves on"


def test_a_stop_has_an_opening_and_a_closing(db):
    """It used to begin mid-interrogation and end by running out of questions."""
    db.add_all([
        m.OfficerAck(text="Afternoon.", kind="opening", status=m.ContentStatus.released),
        m.OfficerAck(text="You're good to go.", kind="closing", status=m.ContentStatus.released),
        m.OfficerAck(text="Okay.", kind="ack", status=m.ContentStatus.released),
    ])
    db.flush()

    assert loop.pick_line(db, "opening").text == "Afternoon."
    assert loop.pick_line(db, "closing").text == "You're good to go."
    # an ack must never be drawn from the opening pool, or a stop starts with "Okay."
    assert loop.pick_acknowledgement(db).text == "Okay."
