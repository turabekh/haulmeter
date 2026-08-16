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
