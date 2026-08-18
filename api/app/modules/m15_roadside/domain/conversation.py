"""AI-CONTEXT: the officer improvises (M15-FR2/FR3, owner amendment entry 189).

**WHY THIS EXISTS.** Three passes of polish on the scripted-tree design — rephrasing,
repair branches, acknowledgements, a stop that opens and closes, the driver's own words
echoed back — and the owner still said "no actual conversation". They were right, and the
diagnosis was not the polish: a fixed list of intents asked in order is a form no matter
how well it is dressed. E3 specified scripted trees; the owner amended it.

**WHAT IS AND IS NOT DELEGATED TO THE MODEL.** The model chooses WHAT IS SAID. It does not
choose what anything is worth. It returns the line plus the intent that line is asking
about, and the driver's answer is still validated against that intent's expected slots from
the scenario's hidden state, then scored by `score_turn` with the deterministic rules and
the separate rubric. Same separation `rubric_f9` states for the same reason: a model that
returned a score would BE the scoring policy, and a version change would silently alter
what a driver is told about their English.

**THE KILL SWITCH IS A CONFIG KEY, NOT A DEPLOY.** `m15.officer_mode` flips between `llm`
and `scripted` through F13. This is unreviewed text reaching drivers by an explicit
amendment, and the thing that makes that survivable is being able to stop it in seconds
without shipping anything. A deploy-gated revert would mean the first bad line stays up for
as long as a build takes.

**LATENCY IS WORSE AND THAT IS THE TRADE.** E3 budgets ≤1.3s p75 on cached audio; a model
call plus synthesis is roughly 1.5–3s. The owner accepted it after hearing the alternative.
Runtime audio is cached by TEXT (`audio.fragment_audio`), so the officer's common lines
converge toward free as the same sentences recur.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.foundation.f09_ai_gateway import public as ai

from .models import Intent, ScenarioVersion, Session, Turn
from .officer_prompt import PROMPT_KEY

MODULE = "m15"

# how much of the stop the officer is reminded of. A real officer remembers the whole
# conversation; a prompt that carries all of it grows without bound and costs per token, so
# this is the working memory of a short stop rather than a transcript archive.
HISTORY_TURNS = 12


class OfficerUnavailable(RuntimeError):
    """The model could not produce a line. The caller falls back to the scripted loop."""


@dataclass
class ImprovisedTurn:
    line: str
    intent_key: str
    done: bool


def conversational_officer(db: DbSession, session: Session) -> ImprovisedTurn:
    """The officer's next line, chosen by the model from where the conversation actually is.

    AI-CONTEXT: raises rather than inventing when the model is unreachable, over budget or
    unparseable — and the caller falls back to the SCRIPTED loop rather than to silence.
    A driver mid-stop gets a slightly stiffer officer instead of a dead screen, which is
    the honest degradation: the scripted path is fully reviewed content and always works.
    """
    scenario = db.get(ScenarioVersion, session.scenario_version_id)
    turns = list(
        db.scalars(
            select(Turn).where(Turn.session_id == session.id).order_by(Turn.seq.desc()).limit(
                HISTORY_TURNS
            )
        )
    )[::-1]

    asked = {t.intent_id for t in turns if t.speaker.value == "officer" and t.intent_id}
    remaining = []
    for key in scenario.allowed_intents or []:
        intent = db.scalar(select(Intent).where(Intent.key == key))
        if intent is not None and intent.id not in asked:
            remaining.append(key)

    history = "\n".join(
        f"{'OFFICER' if t.speaker.value == 'officer' else 'DRIVER'}: {t.transcript or ''}"
        for t in turns
    )
    last_answer = next(
        (t.transcript or "" for t in reversed(turns) if t.speaker.value == "driver"), ""
    )

    try:
        raw = ai.complete(
            db,
            ai.resolve_provider(),
            MODULE,
            PROMPT_KEY,
            {
                "hidden_state": json.dumps(scenario.hidden_state or {}),
                "remaining_intents": ", ".join(remaining),
                "history": history or "(the stop has just begun)",
                "last_answer": last_answer or "(nothing yet)",
            },
        )
    except Exception as exc:  # provider outage, budget, timeout
        raise OfficerUnavailable(str(exc)) from exc

    payload = _parse(raw)
    line = (payload.get("line") or "").strip()
    if not line:
        raise OfficerUnavailable("the model returned no line")

    return ImprovisedTurn(
        line=line,
        intent_key=(payload.get("intent_key") or "").strip(),
        done=bool(payload.get("done")),
    )


def _parse(raw: str) -> dict:
    """AI-CONTEXT: fenced JSON survives, because models emit it and a stop should not end
    over a code fence. Anything else raises rather than being guessed at."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        payload = json.loads(text.strip())
    except (ValueError, IndexError) as exc:
        raise OfficerUnavailable("unparseable officer turn") from exc
    if not isinstance(payload, dict):
        raise OfficerUnavailable("officer turn was not an object")
    return payload


OFFICER_MODE_KEY = "m15.officer_mode"


def officer_mode(db: DbSession) -> str:
    """`llm` or `scripted`. A config key so a bad line can be stopped in seconds.

    AI-CONTEXT: this is the guardrail that makes an unreviewed officer survivable. Q-6 was
    amended for the live simulation, not repealed — and the compensating control for
    "content reaches a driver without review" is an operator who can revert to reviewed
    content without waiting for a build.
    """
    from app.foundation.f13_flags import public as flags

    return str(flags.get_config(db, OFFICER_MODE_KEY, "llm"))
