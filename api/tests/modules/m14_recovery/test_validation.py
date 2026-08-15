"""AI-CONTEXT: the ±3-minute validation and the circularity it refuses (M14-FR2).

The check that matters most here is the one that says NO. E2-FR2 asks for agreement with
"the facility's gate reality" — and a ground truth sourced from the provider proves only
that the poller copies faithfully, which is already covered by unit tests. A rule like
that, left as a note in a docstring, is forgotten at 11pm on a pilot call; so it raises.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.modules.m14_recovery.domain import validation as V

BASE = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)


def _truth(source="gate_log", stop="s-1", arrived=BASE, departed=None):
    return V.GroundTruth(
        stop_ref=stop, arrived_at=arrived, departed_at=departed or BASE + timedelta(hours=3),
        source=source,
    )


def test_the_provider_may_not_validate_itself(db):
    for bad in ("motive", "Motive", "eld", "the ELD feed", "telematics", "gomotive api"):
        with pytest.raises(V.CircularGroundTruth):
            _truth(source=bad)


def test_a_ground_truth_with_no_source_is_not_a_ground_truth(db):
    with pytest.raises(V.CircularGroundTruth):
        _truth(source="")


def test_an_unknown_source_is_refused_rather_than_accepted_loosely(db):
    # a free-text source would let "our own records" through, which is the same defect
    # wearing different words
    with pytest.raises(V.CircularGroundTruth):
        _truth(source="dispatcher_guess")


def test_the_three_real_sources_are_accepted(db):
    for good in V.SOURCE_KINDS:
        assert _truth(source=good).source == good


def test_a_stop_inside_three_minutes_passes(db):
    c = V.compare(_truth(), BASE + timedelta(minutes=2), BASE + timedelta(hours=3))
    assert c.arrival_delta_min == pytest.approx(2.0)
    assert c.passed is True


def test_a_stop_outside_three_minutes_fails_on_its_WORST_leg(db):
    # arrival is fine and departure is not: the pair is what a claim argues from, so the
    # worse of the two decides
    c = V.compare(_truth(), BASE + timedelta(minutes=1), BASE + timedelta(hours=3, minutes=9))
    assert c.arrival_delta_min == pytest.approx(1.0)
    assert c.departure_delta_min == pytest.approx(9.0)
    assert c.passed is False


def test_a_stop_the_ELD_never_saw_is_UNMEASURABLE_not_a_pass(db):
    """A stop with no ELD arrival cannot be within three minutes of anything. Counting it
    either way would make the headline number a fiction."""
    c = V.compare(_truth(), None, None)
    assert c.passed is None
    assert "unmeasurable" in V.report([c])


def test_the_report_counts_toward_the_ten_stop_target(db):
    comparisons = [
        V.compare(_truth(stop=f"s-{i}"), BASE + timedelta(minutes=1), BASE + timedelta(hours=3))
        for i in range(4)
    ]
    text = V.report(comparisons)
    assert "4 of 4 measured stops" in text
    assert f"4/{V.REQUIRED_STOPS}" in text
    assert "is MET" not in text  # four is not ten


def test_the_report_declares_the_target_met_only_at_ten_clean_stops(db):
    ok = [
        V.compare(_truth(stop=f"s-{i}"), BASE + timedelta(minutes=1), BASE + timedelta(hours=3))
        for i in range(10)
    ]
    assert "is MET" in V.report(ok)

    # one failure and it is not met, however many passes sit beside it
    spoiled = ok + [
        V.compare(_truth(stop="bad"), BASE + timedelta(minutes=30), BASE + timedelta(hours=3))
    ]
    assert "is MET" not in V.report(spoiled)


def test_the_weakest_source_is_named_rather_than_averaged_in(db):
    """§11.7's discipline pointed at our own evidence for once: the driver's word is the
    weakest of the three and the report says so instead of blending it."""
    text = V.report([V.compare(_truth(source="driver"), BASE, BASE + timedelta(hours=3))])
    assert "driver's own word" in text
    assert "weakest" in text
