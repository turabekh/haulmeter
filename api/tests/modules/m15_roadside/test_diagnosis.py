"""AI-CONTEXT: bands and quality law Q-8 — the provisional label (M15-FR4).

The assertion this file exists for is `test_a_band_cannot_be_obtained_without_its_
provisional_state`. Q-8 says every band renders "provisional" until rolling human
agreement clears the gate, and a law like that survives only if it is impossible to
bypass rather than merely documented. `band_for` returns a verdict carrying both, so a
caller cannot render a bare colour by accident — and the label key for a provisional band
is a DIFFERENT key, not the plain one with a suffix a surface might forget to add.

The second-most important is `test_the_gate_does_not_open_on_a_lucky_handful`. A gate on
the agreement rate alone opens the first time three reviews happen to agree, at which
point every band silently drops the word "provisional" — the failure looks like success.
"""

import uuid

from app.foundation.f01_identity import public as identity
from app.modules.m15_roadside.domain import diagnosis
from app.modules.m15_roadside.domain import models as m
from app.modules.m15_roadside.domain.diagnosis import Band

PERFECT = {
    "comprehension": 100,
    "answer_completeness": 100,
    "task_completion": 100,
    "intelligibility": 100,
}
POOR = {
    "comprehension": 0,
    "answer_completeness": 0,
    "task_completion": 0,
    "intelligibility": 20,
}
MIDDLING = {
    "comprehension": 100,
    "answer_completeness": 50,
    "task_completion": 0,
    "intelligibility": 100,
}


def _session_with_turn(db):
    scenario = m.ScenarioVersion(version=1, difficulty=m.Difficulty.clear, allowed_intents=[])
    db.add(scenario)
    db.flush()
    account = identity.register_account(
        db, f"diag-{uuid.uuid4().hex[:8]}@example.com", "pw-123456"
    )
    session = m.Session(
        account_id=account.id, scenario_version_id=scenario.id, mode=m.SessionMode.check
    )
    db.add(session)
    db.flush()
    turn = m.Turn(session_id=session.id, seq=1, speaker=m.Speaker.driver, transcript="x")
    db.add(turn)
    db.flush()
    return turn


def _reviews(db, *, count, agreeing):
    """`agreeing` of `count` reviews agree — created through the real recorder."""
    for i in range(count):
        turn = _session_with_turn(db)
        human = "green" if i < agreeing else "red"
        diagnosis.record_review(
            db, turn_id=turn.id, ai_band="green", human_band=human, reviewer="calibrator"
        )
    db.flush()


# --- bands --------------------------------------------------------------------------


def test_the_three_bands_are_the_ones_e3_names(db):
    assert [b.value for b in Band] == ["green", "yellow", "red"]


def test_scores_map_to_bands_at_the_configured_thresholds(db):
    assert diagnosis.band_for(db, [PERFECT]).band is Band.green
    assert diagnosis.band_for(db, [MIDDLING]).band is Band.yellow
    assert diagnosis.band_for(db, [POOR]).band is Band.red


def test_unscored_turns_are_excluded_rather_than_counted_as_zero(db):
    """Q-2 reaching the band.

    A session where the recogniser failed three times must not band lower than one where
    it did not — the driver said the same things. Counting an unheard turn as zero would
    let ASR quality decide what a driver is told about their English.
    """
    with_gaps = diagnosis.band_for(db, [PERFECT, {}, {}, {}])
    without = diagnosis.band_for(db, [PERFECT])
    assert with_gaps.score == without.score
    assert with_gaps.band is without.band


# --- Q-8 -----------------------------------------------------------------------------


def test_a_band_cannot_be_obtained_without_its_provisional_state(db):
    """The law is structural: there is no API that returns a bare Band."""
    verdict = diagnosis.band_for(db, [PERFECT])
    assert isinstance(verdict, diagnosis.BandVerdict)
    assert verdict.provisional is True
    assert not isinstance(verdict, Band)


def test_an_uncalibrated_band_renders_a_different_key_not_a_suffix(db):
    """A surface cannot forget to append something it never receives."""
    verdict = diagnosis.band_for(db, [PERFECT])
    assert verdict.label_key == "roadside.band.green_provisional"


def test_nothing_reviewed_reads_as_unknown_not_as_zero_agreement(db):
    """A 0.0 would claim the scorer agrees with humans none of the time.

    That is a far worse statement than "no human has looked yet", and it is exactly the
    zero this project has a trap about.
    """
    size, pct = diagnosis.rolling_agreement(db)
    assert size == 0
    assert pct is None
    assert diagnosis.is_calibrated(db) is False


def test_the_gate_does_not_open_on_a_lucky_handful(db):
    """Three reviews that agree are 100% and prove nothing."""
    _reviews(db, count=3, agreeing=3)
    size, pct = diagnosis.rolling_agreement(db)
    assert (size, pct) == (3, 100.0)
    assert diagnosis.is_calibrated(db) is False, "a sample of 3 must not open the gate"
    assert diagnosis.band_for(db, [PERFECT]).provisional is True


def test_enough_agreement_over_enough_samples_drops_provisional(db):
    _reviews(db, count=40, agreeing=38)  # 95%
    size, pct = diagnosis.rolling_agreement(db)
    assert size == 40
    assert pct == 95.0
    assert diagnosis.is_calibrated(db) is True

    verdict = diagnosis.band_for(db, [PERFECT])
    assert verdict.provisional is False
    assert verdict.label_key == "roadside.band.green"


def test_a_large_sample_that_disagrees_keeps_the_label(db):
    """Volume alone is not calibration."""
    _reviews(db, count=40, agreeing=20)  # 50%
    assert diagnosis.is_calibrated(db) is False
    assert diagnosis.band_for(db, [PERFECT]).provisional is True


# --- the agreement metric cannot be told a story --------------------------------------


def test_agreement_is_derived_from_the_two_bands_not_supplied(db):
    """`record_review` computes `agree` itself.

    If a caller could pass it, the number that decides whether a driver's band still says
    "provisional" would be whatever the caller claimed.
    """
    turn = _session_with_turn(db)
    same = diagnosis.record_review(
        db, turn_id=turn.id, ai_band="yellow", human_band="yellow", reviewer="r"
    )
    assert same.agree is True

    other = _session_with_turn(db)
    differ = diagnosis.record_review(
        db, turn_id=other.id, ai_band="green", human_band="red", reviewer="r"
    )
    assert differ.agree is False
