"""AI-CONTEXT: deterministic slot validation + the semantic rubric seam (M15-FR4).

QUALITY LAW Q-1 IS THE DESIGN OF THIS FILE, not a check bolted onto it. *Accent is never a
feature, a score, or a tag.* There is no dimension for fluency, no weight for nativeness,
no tag for "hard to understand because of an accent", and none may be added. The four
dimensions E3 names are all about whether the MEANING arrived:

    comprehension          — did they answer the question that was asked
    answer_completeness    — are the required facts present
    task_completion        — did the exchange reach its purpose
    intelligibility        — could a person make out what was said

The fourth is the one that could go wrong, so it is defined narrowly on purpose:
**intelligibility is about audibility, not about how native someone sounds.** A driver
whose grammar is broken and whose meaning is clear scores well; a clear recording of
perfect English answering the wrong question does not. Intelligibility is only ever
lowered by an ASR confidence floor or an explicit unintelligible verdict — never by the
rubric's opinion of the speaker.

WHY THE SPLIT IS HYBRID. Slot validation is DETERMINISTIC because a fact is a fact: a
driver who says Chicago said Chicago, and no model needs consulting to check it against
hidden state. Only the judgement calls — did they understand, was this a repair request —
go to the rubric seam. That boundary is what keeps a scoring control from drifting with a
model version, and it is why `score_turn` can produce a band with the rubric stubbed.
"""

from __future__ import annotations

import enum
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Protocol


class FailureTag(enum.Enum):
    """The ten tags E3 §E3.1.4 names. There is no eleventh about accent."""

    INTENT_MISUNDERSTOOD = "INTENT_MISUNDERSTOOD"
    SLOT_WRONG_FACT = "SLOT_WRONG_FACT"
    MULTI_PART_PARTIAL = "MULTI_PART_PARTIAL"
    REPETITION_REQUIRED = "REPETITION_REQUIRED"
    TERMINOLOGY_UNKNOWN = "TERMINOLOGY_UNKNOWN"
    SIGN_INCORRECT = "SIGN_INCORRECT"
    DYNAMIC_SIGN_INCORRECT = "DYNAMIC_SIGN_INCORRECT"
    UNINTELLIGIBLE = "UNINTELLIGIBLE"
    IRRELEVANT = "IRRELEVANT"
    NO_RESPONSE = "NO_RESPONSE"


class Dimension(enum.Enum):
    comprehension = "comprehension"
    answer_completeness = "answer_completeness"
    task_completion = "task_completion"
    intelligibility = "intelligibility"


# AI-CONTEXT: below this ASR confidence a turn is REVIEW_NEEDED and scores nothing (Q-2).
# It is a FLOOR, not a penalty: an unclear recording is not a failed answer, and the
# difference is the whole point — a driver whose accent defeated the recogniser has not
# failed anything, and treating the two the same is how a scoring control starts scoring
# accent without anyone deciding to.
ASR_CONFIDENCE_FLOOR = 0.55

# tags that are diagnostics rather than failures — logged, never scored (E3 §E3.1.4:
# "latency and repetition counts are logged diagnostics only")
DIAGNOSTIC_ONLY = frozenset({FailureTag.REPETITION_REQUIRED})


@dataclass
class SlotResult:
    filled: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    wrong: dict[str, str] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return not self.missing and not self.wrong


@dataclass
class RubricVerdict:
    """What the semantic half is allowed to say. Note what is absent."""

    intent_matched: bool
    intelligible: bool
    asked_for_repeat: bool = False
    unknown_terms: list[str] = field(default_factory=list)


class Rubric(Protocol):
    """The semantic seam. F9-backed in production, deterministic in tests.

    AI-CONTEXT: it returns a `RubricVerdict` and NOT a score. The rubric is asked what
    happened; this module decides what that is worth. Letting a model return a number
    directly is how a rubric quietly becomes the scoring policy, and then a model version
    changes what a driver is told about themselves.
    """

    def judge(self, *, officer_line: str, transcript: str, intent_key: str) -> RubricVerdict: ...


class DeterministicRubric:
    """A rubric with no model behind it, for tests and for the offline path.

    Deliberately dumb: it exists so `score_turn` can be exercised without F9, not to be
    good at judging.
    """

    def __init__(
        self,
        *,
        intent_matched: bool = True,
        intelligible: bool = True,
        asked_for_repeat: bool = False,
        unknown_terms: list[str] | None = None,
    ):
        self._verdict = RubricVerdict(
            intent_matched=intent_matched,
            intelligible=intelligible,
            asked_for_repeat=asked_for_repeat,
            unknown_terms=unknown_terms or [],
        )

    def judge(self, *, officer_line: str, transcript: str, intent_key: str) -> RubricVerdict:
        return self._verdict


# --- deterministic slot validation ---------------------------------------------------


def _normalize(text: str) -> str:
    """Casefold, strip accents and punctuation, collapse whitespace.

    AI-CONTEXT: stripping diacritics here is about MATCHING A FACT, not about judging the
    speaker — "Chicago" and "Chicágo" are the same city, and a transcript's diacritics
    depend on the recogniser rather than on the driver.
    """
    folded = unicodedata.normalize("NFKD", text).casefold()
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = re.sub(r"[^\w\s]", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19, "twenty": 20,
}


def _numbers_in(text: str) -> set[int]:
    """Digits and number-words alike.

    A driver answering "six hours" and one answering "6 hours" said the same thing, and a
    validator that only understands digits would mark the first wrong — which is scoring
    the recogniser's output format, one step away from scoring the speaker.
    """
    normalized = _normalize(text)
    found = {int(tok) for tok in re.findall(r"\b\d+\b", normalized)}
    for word, value in _NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", normalized):
            found.add(value)
    return found


def validate_slots(expected: dict[str, str], transcript: str) -> SlotResult:
    """Check the driver's words against the scenario's hidden state.

    Deterministic by design: a fact is a fact and no model is consulted. Numeric slots
    match on VALUE (digits or words); everything else matches on normalized substring.
    """
    result = SlotResult()
    if not expected:
        return result

    said_numbers = _numbers_in(transcript)
    normalized_transcript = _normalize(transcript)

    for slot, truth in expected.items():
        truth_str = str(truth)
        truth_numbers = _numbers_in(truth_str)
        if truth_numbers:
            if truth_numbers & said_numbers:
                result.filled[slot] = truth_str
            elif said_numbers:
                # they gave a number, and it was the wrong one — a different failure from
                # saying nothing, and the driver needs a different lesson for each
                result.wrong[slot] = truth_str
            else:
                result.missing.append(slot)
            continue

        if _normalize(truth_str) and _normalize(truth_str) in normalized_transcript:
            result.filled[slot] = truth_str
        else:
            result.missing.append(slot)
    return result


# --- scoring -------------------------------------------------------------------------


@dataclass
class TurnScore:
    scores: dict[str, int]
    failure_tags: list[str]
    review_needed: bool
    slots: SlotResult


def score_turn(
    *,
    officer_line: str,
    transcript: str | None,
    intent_key: str,
    expected_slots: dict[str, str],
    asr_confidence: float | None,
    rubric: Rubric,
    is_sign_turn: bool = False,
    is_dynamic_sign: bool = False,
) -> TurnScore:
    """Score one turn on the four dimensions and tag what went wrong.

    Order matters and is not arbitrary:
      1. NO RESPONSE  — nothing was said; nothing else can be judged.
      2. ASR FLOOR    — we could not hear it; Q-2 forbids scoring it either way.
      3. everything else.

    Steps 1 and 2 both return early WITHOUT a negative score, which is the Q-2 law: a turn
    we could not hear is excluded from bands, not marked wrong.
    """
    if transcript is None or not transcript.strip():
        return TurnScore(
            scores={},
            failure_tags=[FailureTag.NO_RESPONSE.value],
            review_needed=False,
            slots=SlotResult(missing=list(expected_slots)),
        )

    if asr_confidence is not None and asr_confidence < ASR_CONFIDENCE_FLOOR:
        # Q-2: REVIEW_NEEDED, excluded from bands, and NOT a negative tag. The turn is
        # tagged UNINTELLIGIBLE for the driver's own transcript-flag affordance, but it
        # carries no scores at all — so it cannot pull a band down.
        return TurnScore(
            scores={},
            failure_tags=[FailureTag.UNINTELLIGIBLE.value],
            review_needed=True,
            slots=SlotResult(missing=list(expected_slots)),
        )

    verdict = rubric.judge(
        officer_line=officer_line, transcript=transcript, intent_key=intent_key
    )
    slots = validate_slots(expected_slots, transcript)
    tags: list[str] = []

    comprehension = 100 if verdict.intent_matched else 0
    if not verdict.intent_matched:
        tags.append(FailureTag.INTENT_MISUNDERSTOOD.value)
        # a fluent answer to the wrong question is IRRELEVANT as well — the driver needs
        # to know it was well said and beside the point
        tags.append(FailureTag.IRRELEVANT.value)

    if expected_slots:
        filled = len(slots.filled)
        total = len(expected_slots)
        answer_completeness = int(100 * filled / total)
        if slots.wrong:
            tags.append(FailureTag.SLOT_WRONG_FACT.value)
        if slots.missing and filled:
            # they answered part of a multi-part question
            tags.append(FailureTag.MULTI_PART_PARTIAL.value)
    else:
        answer_completeness = 100 if verdict.intent_matched else 0

    if is_sign_turn:
        sign_ok = verdict.intent_matched and slots.complete
        if not sign_ok:
            tags.append(
                (
                    FailureTag.DYNAMIC_SIGN_INCORRECT
                    if is_dynamic_sign
                    else FailureTag.SIGN_INCORRECT
                ).value
            )

    if verdict.asked_for_repeat:
        # a DIAGNOSTIC, never a failure — asking an officer to repeat themselves is what a
        # careful driver does, and penalising it would teach the opposite
        tags.append(FailureTag.REPETITION_REQUIRED.value)

    for term in verdict.unknown_terms:
        tags.append(f"{FailureTag.TERMINOLOGY_UNKNOWN.value}({term})")

    task_completion = 100 if (verdict.intent_matched and slots.complete) else 0
    # AI-CONTEXT: intelligibility is AUDIBILITY. It is full marks for anything that got
    # past the ASR floor, and the only thing that lowers it is the rubric saying a person
    # could not make the words out. It is never lowered for how the speaker sounds.
    intelligibility = 100 if verdict.intelligible else 0
    if not verdict.intelligible and FailureTag.UNINTELLIGIBLE.value not in tags:
        tags.append(FailureTag.UNINTELLIGIBLE.value)

    return TurnScore(
        scores={
            Dimension.comprehension.value: comprehension,
            Dimension.answer_completeness.value: answer_completeness,
            Dimension.task_completion.value: task_completion,
            Dimension.intelligibility.value: intelligibility,
        },
        failure_tags=tags,
        review_needed=False,
        slots=slots,
    )


def scoring_tags_are_accent_free() -> bool:
    """Q-1, asserted from the vocabulary itself rather than from a promise in a docstring.

    Exposed as a function so a test can call it and so a future session adding a tag has
    to read why the list is closed. If someone adds `HEAVY_ACCENT`, this returns False and
    the Q-1 test goes red — which is the only enforcement a taxonomy can carry.
    """
    banned = ("accent", "native", "fluen", "pronunc", "grammar", "foreign", "broken")
    vocabulary = [t.value.lower() for t in FailureTag] + [d.value.lower() for d in Dimension]
    return not any(bad in word for word in vocabulary for bad in banned)
