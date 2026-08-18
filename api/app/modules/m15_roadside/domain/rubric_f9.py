"""AI-CONTEXT: the F9-backed semantic rubric (M15-FR2 "hybrid scoring", M15-FR4).

This is the ONLY place a model is consulted about a driver's answer, and it is deliberately
small. `scoring.py` holds the policy — which dimensions exist, what a tag is worth, what
Q-1 forbids — and this file holds one question: *what happened in that turn?*

WHY THE SEAM RETURNS A VERDICT AND NOT A SCORE, restated here because this is the file
where it would be tempting to shortcut. If the model returned a number, the model would BE
the scoring policy, and a provider or version change would silently alter what a driver is
told about their English. It reports observations; `score_turn` decides their worth.

FAILURE IS A REVIEW, NOT A GUESS. When F9 is unreachable, over budget, or returns
something unparseable, this does NOT fall back to a lenient or a harsh verdict — both are
opinions about a driver invented by an outage. It raises, and the caller marks the turn
`REVIEW_NEEDED`, which is the same honest state Q-2 uses for audio nobody could hear.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.foundation.f09_ai_gateway import public as ai

from .prompts import PROMPT_KEY
from .scoring import RubricVerdict

MODULE = "m15"


class RubricUnavailable(RuntimeError):
    """The rubric could not judge this turn. The turn becomes REVIEW_NEEDED, not a fail."""


class F9Rubric:
    """Judges a turn through the registered classify prompt.

    AI-CONTEXT: the prompt is resolved from the REGISTRY per call (inside `ai.complete`)
    rather than captured at construction, so a version bump takes effect without a restart
    — and so the version actually used is the one an operator can see in `/admin`, rather
    than whichever was active when the process booted.
    """

    def __init__(self, db: Session, *, account_id=None) -> None:
        self._db = db
        self._account_id = account_id

    def judge(
        self,
        *,
        officer_line: str,
        transcript: str,
        intent_key: str,
        canonical_meaning: str = "",
        required_slots: dict | None = None,
    ) -> RubricVerdict:
        """AI-CONTEXT: TWO FIELDS THE TEMPLATE ASKS FOR THAT THIS NEVER SUPPLIED.

        `PROMPT_TEMPLATE` renders "The intent behind it: {canonical_meaning}" and
        "Required pieces of information: {required_slots}". This passed the snake_case
        INTENT KEY for the first and a hardcoded `""` for the second — so the model was
        told the intent behind "Wait here while I run these." was `wait_instruction`, and
        was asked which required pieces of information appeared without being told what
        any of them were. `Intent.canonical_meaning` is authored on every intent and
        reviewed by a human under Q-6, and reached nothing.

        Found by a probe scoring "I do not understand" as a perfect answer, not by a test
        (entry 208). The fallbacks keep callers with no `Intent` row working: the key is a
        poor meaning but it is what the model used to get, and "none" is at least true.
        """
        try:
            raw = ai.complete(
                self._db,
                ai.resolve_provider(),
                MODULE,
                PROMPT_KEY,
                {
                    "officer_line": officer_line,
                    "canonical_meaning": canonical_meaning or intent_key,
                    "required_slots": ", ".join(required_slots or {}) or "none",
                    "transcript": transcript,
                },
                account_id=self._account_id,
            )
        except ai.BudgetExceeded as exc:
            # AI-CONTEXT: an exhausted budget must not silently become a verdict. A driver
            # scored by a fallback because the month's AI spend ran out has been told
            # something about themselves by an accounting limit.
            raise RubricUnavailable(f"m15 AI budget exhausted: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise RubricUnavailable(f"rubric call failed: {exc}") from exc

        return parse_verdict(raw)


def parse_verdict(raw: str) -> RubricVerdict:
    """Read the model's JSON. Anything unreadable is a REVIEW, never a default verdict."""
    text = (raw or "").strip()
    # models fence JSON often enough that stripping it is cheaper than fighting it
    if "{" not in text or "}" not in text:
        raise RubricUnavailable(f"rubric returned no readable JSON: {raw!r}")
    try:
        payload = json.loads(text[text.find("{") : text.rfind("}") + 1])
    except (ValueError, TypeError) as exc:
        raise RubricUnavailable(f"rubric returned no readable JSON: {raw!r}") from exc

    if not isinstance(payload, dict) or "intent_matched" not in payload:
        raise RubricUnavailable(f"rubric verdict has no intent_matched: {payload!r}")

    return RubricVerdict(
        intent_matched=bool(payload.get("intent_matched")),
        # AI-CONTEXT: `intelligible` DEFAULTS TRUE when the model omits it, and that
        # direction is deliberate. The alternative default marks a driver unintelligible
        # because a field was missing from a JSON blob, which is a judgement about a person
        # made by a parsing accident. Genuine unintelligibility has its own signal — the
        # ASR confidence floor, which is measured rather than opined.
        intelligible=bool(payload.get("intelligible", True)),
        asked_for_repeat=bool(payload.get("asked_for_repeat", False)),
        unknown_terms=[str(t) for t in payload.get("unknown_terms", []) or []],
    )
