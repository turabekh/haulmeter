"""AI-CONTEXT: the F9 rubric bridge fails as a REVIEW, never as a verdict (M15-FR4).

The assertions here are all about the failure direction. A rubric that returned "did not
understand" when F9 was unreachable would let an outage, a budget ceiling or a malformed
JSON blob become a statement about a driver's English — and it would look exactly like a
real result on the result screen. So every failure path raises, and the caller turns that
into REVIEW_NEEDED, which is the same honest state Q-2 uses for audio nobody could hear.
"""

import pytest

from app.modules.m15_roadside.domain.rubric_f9 import RubricUnavailable, parse_verdict


def test_a_well_formed_verdict_parses():
    v = parse_verdict('{"intent_matched": true, "slots_filled": ["destination"], '
                      '"intelligible": true}')
    assert v.intent_matched is True
    assert v.intelligible is True


def test_a_fenced_verdict_still_parses():
    """Models fence JSON often enough that fighting it costs more than stripping it."""
    v = parse_verdict('```json\n{"intent_matched": false, "intelligible": true}\n```')
    assert v.intent_matched is False


def test_unreadable_output_is_a_review_not_a_default_verdict():
    """The important direction: garbage must not become "did not understand"."""
    for junk in ("", "   ", "I think the driver did fine", "null", "[]"):
        with pytest.raises(RubricUnavailable):
            parse_verdict(junk)


def test_a_verdict_missing_intent_matched_is_refused():
    with pytest.raises(RubricUnavailable):
        parse_verdict('{"intelligible": true}')


def test_intelligible_defaults_TRUE_when_omitted():
    """A missing field must not mark a driver unintelligible.

    That would be a judgement about a person made by a parsing accident. Genuine
    unintelligibility has its own signal — the ASR confidence floor, which is measured.
    """
    v = parse_verdict('{"intent_matched": true}')
    assert v.intelligible is True


def test_unknown_terms_survive_as_strings():
    v = parse_verdict('{"intent_matched": true, "unknown_terms": ["tandem", "BOL"]}')
    assert v.unknown_terms == ["tandem", "BOL"]
