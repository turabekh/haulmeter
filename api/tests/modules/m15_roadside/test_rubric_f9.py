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


# --- what the model is actually TOLD about the question ------------------------------
#
# AI-CONTEXT: two fields the prompt template asks for and the call site never supplied.
# Found 2026-08-18 while authoring 49 intents (entry 208), when the probe scored "I do not
# understand" as a perfect answer to "Wait here while I run these."
#
# `PROMPT_TEMPLATE` renders "The intent behind it: {canonical_meaning}" and
# "Required pieces of information: {required_slots}". The call site passed the snake_case
# INTENT KEY for the first and a hardcoded EMPTY STRING for the second — so the model was
# told the intent behind the question was `wait_instruction`, and was asked which required
# pieces of information were present without being told what any of them were.
#
# `Intent.canonical_meaning` is authored on every intent, reviewed by a human under Q-6,
# and reached nothing. It is the same defect as every row in HANDOFF-138 §2: written,
# wired to nothing, believed. These tests were watched failing before the fix.


class _Recorder:
    """A stand-in provider that keeps the rendered prompt."""

    def __init__(self):
        self.rendered = None

    def __call__(self, *, template: str, values: dict) -> str:
        self.rendered = template.format(**values)
        return (
            '{"intent_matched": true, "slots_filled": [], '
            '"slots_missing": [], "intelligible": true}'
        )


def test_the_rubric_is_told_the_intents_MEANING_not_its_key(monkeypatch):
    from app.modules.m15_roadside.domain import prompts, rubric_f9

    captured = {}

    def fake_complete(db, provider, module, key, values, account_id=None):
        captured.update(values)
        return (
            '{"intent_matched": true, "slots_filled": [], '
            '"slots_missing": [], "intelligible": true}'
        )

    monkeypatch.setattr(rubric_f9.ai, "complete", fake_complete)
    monkeypatch.setattr(rubric_f9.ai, "resolve_provider", lambda: "fake")

    rubric_f9.F9Rubric(db=None).judge(
        officer_line="Wait here while I run these.",
        transcript="I do not understand",
        intent_key="wait_instruction",
        canonical_meaning="the driver acknowledges an instruction to wait",
        required_slots={"acknowledgement": "required"},
    )

    assert captured["canonical_meaning"] == "the driver acknowledges an instruction to wait"
    assert captured["canonical_meaning"] != "wait_instruction"
    # the template renders this field; an empty string asks the model which of nothing
    assert captured["required_slots"].strip() != ""
    assert "acknowledgement" in captured["required_slots"]
    # and the rendered prompt must actually carry them
    assert "{" not in prompts.PROMPT_TEMPLATE.format(**captured)


def test_a_meaningless_key_still_works_when_no_meaning_is_supplied(monkeypatch):
    """Callers that have no Intent row must degrade to the old behaviour, not crash."""
    from app.modules.m15_roadside.domain import rubric_f9

    captured = {}

    def fake_complete(db, provider, module, key, values, account_id=None):
        captured.update(values)
        return (
            '{"intent_matched": true, "slots_filled": [], '
            '"slots_missing": [], "intelligible": true}'
        )

    monkeypatch.setattr(rubric_f9.ai, "complete", fake_complete)
    monkeypatch.setattr(rubric_f9.ai, "resolve_provider", lambda: "fake")

    rubric_f9.F9Rubric(db=None).judge(
        officer_line="Where are you headed?", transcript="Chicago", intent_key="destination"
    )

    assert captured["canonical_meaning"] == "destination"
    assert captured["required_slots"] == "none"
