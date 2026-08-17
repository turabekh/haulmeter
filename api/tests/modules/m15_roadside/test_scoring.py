"""AI-CONTEXT: quality law Q-1 and the hybrid scorer (M15-FR4).

Q-1 IS THE POINT OF THIS FILE: *accent is never a feature, a score, or a tag.* The two
tests that carry it are `test_broken_english_that_carries_the_meaning_beats_fluent_evasion`
— E3's own example, "I go Chicago" against "Yes." on a destination question — and
`test_the_vocabulary_itself_contains_no_accent_dimension`, which reads the enums rather
than trusting a docstring, so that adding a `HEAVY_ACCENT` tag turns this red.

Provenance stated honestly rather than flattered: the scorer was written first and these
tests second, then each law was sabotaged and the tests watched to fail. That is E3's build
note ("sabotage each and watch it go red before trusting green") and not a strict red-first
ordering.
"""

from app.modules.m15_roadside.domain import scoring
from app.modules.m15_roadside.domain.scoring import (
    DeterministicRubric,
    Dimension,
    FailureTag,
    score_turn,
    validate_slots,
)

DESTINATION = "Where are you headed?"


def _score(transcript, *, expected=None, confidence=0.95, rubric=None, **kw):
    return score_turn(
        officer_line=kw.pop("officer_line", DESTINATION),
        transcript=transcript,
        intent_key=kw.pop("intent_key", "destination"),
        expected_slots=expected if expected is not None else {"destination": "Chicago"},
        asr_confidence=confidence,
        rubric=rubric or DeterministicRubric(),
        **kw,
    )


# --- Q-1 ------------------------------------------------------------------------------


def test_broken_english_that_carries_the_meaning_beats_fluent_evasion():
    """E3's own example, and the single most important assertion in the module.

    "I go Chicago" is ungrammatical and complete. "Yes." is well-formed and answers
    nothing. If the second ever outscores the first, the scorer is rewarding fluency —
    which is scoring accent under a different name.
    """
    broken = _score("I go Chicago")
    fluent_but_empty = _score("Yes.", rubric=DeterministicRubric(intent_matched=False))

    assert broken.scores[Dimension.answer_completeness.value] == 100
    assert broken.scores[Dimension.task_completion.value] == 100
    assert broken.failure_tags == []

    assert fluent_but_empty.scores[Dimension.answer_completeness.value] == 0
    assert FailureTag.INTENT_MISUNDERSTOOD.value in fluent_but_empty.failure_tags

    for dimension in Dimension:
        assert (
            broken.scores[dimension.value] >= fluent_but_empty.scores[dimension.value]
        ), f"{dimension.value}: broken-but-meaningful must never score below fluent-but-empty"


def test_the_vocabulary_itself_contains_no_accent_dimension():
    """Read the enums, not the docstring. Adding `HEAVY_ACCENT` turns this red."""
    assert scoring.scoring_tags_are_accent_free() is True
    words = [t.value.lower() for t in FailureTag] + [d.value.lower() for d in Dimension]
    for banned in ("accent", "native", "fluen", "pronunc", "grammar"):
        assert not any(banned in w for w in words)


def test_intelligibility_is_audibility_not_nativeness():
    """The dimension that could go wrong, pinned.

    Heavily accented but audible speech that answers the question scores full
    intelligibility. The only thing that lowers it is a person being unable to make the
    words out.
    """
    accented = _score("Ah, I am go to Chicago, yes, Chicago")
    assert accented.scores[Dimension.intelligibility.value] == 100
    assert FailureTag.UNINTELLIGIBLE.value not in accented.failure_tags


# --- deterministic slot validation ----------------------------------------------------


def test_a_fact_is_matched_without_consulting_a_model():
    result = validate_slots({"destination": "Chicago"}, "yeah heading up to chicago tonight")
    assert result.filled == {"destination": "Chicago"}
    assert result.missing == []


def test_number_words_and_digits_are_the_same_answer():
    """"six hours" and "6 hours" are the same claim.

    A validator that only understands digits marks the first wrong — which is scoring the
    recogniser's output format, one step away from scoring the speaker.
    """
    assert validate_slots({"hours": "6"}, "six hours today").filled == {"hours": "6"}
    assert validate_slots({"hours": "6"}, "6 hours today").filled == {"hours": "6"}


def test_a_wrong_number_is_a_different_failure_from_no_number():
    """The driver needs a different lesson for each, so the tags differ."""
    wrong = validate_slots({"hours": "6"}, "about nine hours")
    assert wrong.wrong == {"hours": "6"}
    assert wrong.missing == []

    silent = validate_slots({"hours": "6"}, "since this morning")
    assert silent.missing == ["hours"]
    assert silent.wrong == {}


def test_diacritics_do_not_decide_whether_a_fact_matched():
    """A transcript's accents come from the recogniser, not from the driver."""
    assert validate_slots({"city": "Bogota"}, "we go to Bogotá").filled


def test_a_partially_answered_multi_part_question_is_tagged():
    partial = _score("Chicago", expected={"destination": "Chicago", "cargo": "furniture"})
    assert FailureTag.MULTI_PART_PARTIAL.value in partial.failure_tags
    assert partial.scores[Dimension.answer_completeness.value] == 50


def test_a_wrong_fact_is_tagged_as_such():
    wrong = _score(
        "I have been driving nine hours",
        expected={"hours": "6"},
        intent_key="hos_hours_driven",
    )
    assert FailureTag.SLOT_WRONG_FACT.value in wrong.failure_tags


# --- Q-2, at the scorer ----------------------------------------------------------------


def test_below_floor_confidence_scores_nothing_at_all():
    """Q-2: an unclear recording is not a failed answer.

    The turn is REVIEW_NEEDED and carries NO scores, so it cannot pull a band down. A
    driver whose accent defeated the recogniser has not failed anything, and scoring it
    low is precisely how a scoring control starts scoring accent without anyone deciding to.
    """
    unclear = _score("mumble", confidence=0.2)
    assert unclear.review_needed is True
    assert unclear.scores == {}
    assert FailureTag.UNINTELLIGIBLE.value in unclear.failure_tags


def test_the_floor_is_a_floor_not_a_penalty():
    clear = _score("I go Chicago", confidence=scoring.ASR_CONFIDENCE_FLOOR + 0.01)
    assert clear.review_needed is False
    assert clear.scores[Dimension.task_completion.value] == 100


def test_silence_is_its_own_tag_and_scores_nothing():
    for empty in (None, "", "   "):
        silent = _score(empty)
        assert silent.failure_tags == [FailureTag.NO_RESPONSE.value]
        assert silent.scores == {}


# --- diagnostics vs failures ------------------------------------------------------------


def test_asking_an_officer_to_repeat_is_a_diagnostic_not_a_failure():
    """Penalising it would teach a driver to guess rather than ask, at a roadside stop."""
    repeated = _score(
        "Sorry, could you say that again? Chicago.",
        rubric=DeterministicRubric(asked_for_repeat=True),
    )
    assert FailureTag.REPETITION_REQUIRED.value in repeated.failure_tags
    assert FailureTag.REPETITION_REQUIRED in scoring.DIAGNOSTIC_ONLY
    assert repeated.scores[Dimension.task_completion.value] == 100


def test_unknown_terminology_is_tagged_with_the_term():
    """FR5 teaches vocabulary before testing it, which needs to know WHICH word."""
    unknown = _score("I go Chicago", rubric=DeterministicRubric(unknown_terms=["tandem"]))
    assert any(
        t.startswith("TERMINOLOGY_UNKNOWN(") and "tandem" in t for t in unknown.failure_tags
    )


def test_a_fluent_answer_to_the_wrong_question_is_both_misunderstood_and_irrelevant():
    """The driver needs to know it was well said AND beside the point."""
    off = _score(
        "I am hauling furniture to a warehouse", rubric=DeterministicRubric(intent_matched=False)
    )
    assert FailureTag.INTENT_MISUNDERSTOOD.value in off.failure_tags
    assert FailureTag.IRRELEVANT.value in off.failure_tags


# --- sign turns --------------------------------------------------------------------------


def test_a_missed_sign_is_tagged_distinctly_from_a_dynamic_one():
    static = _score(
        "no idea",
        expected={"meaning": "weigh station ahead"},
        rubric=DeterministicRubric(intent_matched=False),
        is_sign_turn=True,
    )
    dynamic = _score(
        "no idea",
        expected={"meaning": "left lane closed"},
        rubric=DeterministicRubric(intent_matched=False),
        is_sign_turn=True,
        is_dynamic_sign=True,
    )

    assert FailureTag.SIGN_INCORRECT.value in static.failure_tags
    assert FailureTag.DYNAMIC_SIGN_INCORRECT.value in dynamic.failure_tags
    assert FailureTag.SIGN_INCORRECT.value not in dynamic.failure_tags


# --- the rubric seam ----------------------------------------------------------------------


def test_the_rubric_returns_a_verdict_not_a_score():
    """The seam's shape is the guard.

    A rubric that returned a number would BE the scoring policy, and a model version
    change would silently alter what a driver is told about themselves. It reports what
    happened; this module decides what that is worth.
    """
    verdict = DeterministicRubric().judge(
        officer_line=DESTINATION, transcript="I go Chicago", intent_key="destination"
    )
    assert hasattr(verdict, "intent_matched")
    assert not hasattr(verdict, "score")
    assert not hasattr(verdict, "band")


def test_a_repeat_request_INSTEAD_of_an_answer_carries_no_scores():
    """AI-CONTEXT: the half `DIAGNOSTIC_ONLY` claimed and nothing implemented.

    That frozenset named REPETITION_REQUIRED as "never a failure" and was read by no code
    at all. A driver who said "sorry?" and nothing else scored comprehension 0 and picked
    up INTENT_MISUNDERSTOOD and IRRELEVANT — by definition, since they had not matched the
    intent. So the product punished the exact behaviour a careful driver shows at a real
    window, while a comment said it did not.

    No scores at all, in the shape NO_RESPONSE and the ASR floor already use: excluded
    from the band rather than dragging it down.
    """
    asked = _score("Sorry, could you say that again?", rubric=DeterministicRubric(
        asked_for_repeat=True, intent_matched=False
    ))
    assert asked.scores == {}
    assert asked.failure_tags == [FailureTag.REPETITION_REQUIRED.value]
    assert FailureTag.INTENT_MISUNDERSTOOD.value not in asked.failure_tags
    assert FailureTag.IRRELEVANT.value not in asked.failure_tags


def test_the_prompt_asks_for_every_field_the_rubric_parses():
    """The defect that made all of this dead code, as a test.

    `rubric_f9` reads `asked_for_repeat` out of the model's JSON. The prompt never asked
    for it, so no model ever produced it, so it was always False, so REPETITION_REQUIRED
    could not fire in production — and the officer never repeated himself. A parsed field
    that the prompt does not request is a feature that cannot happen.
    """
    from app.modules.m15_roadside.domain import prompts

    for field in ("intent_matched", "slots_filled", "slots_missing", "intelligible",
                  "asked_for_repeat"):
        assert f'"{field}"' in prompts.PROMPT_TEMPLATE, (
            f"{field} is parsed from the model's reply but the prompt never asks for it"
        )
