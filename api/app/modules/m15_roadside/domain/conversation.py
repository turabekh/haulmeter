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

**LATENCY, AND WHERE IT ACTUALLY WENT.** E3 budgets ≤1.3s p75 on cached audio; a model
call plus synthesis cannot meet that, and the owner accepted the trade. What was not
acceptable was the first live measurement — 2.0–6.8s per turn, long enough that a driver
stops believing they are talking to anyone. The obvious diagnosis was wrong, and it is
written down here so nobody spends the afternoon on it again:

  · **it is NOT thinking depth.** Claude Opus 5 thinks by default at `high` effort, and a
    two-sentence in-character line is plainly not a reasoning task — so `effort=low` looked
    like free seconds. Measured against the live API, five calls each: no effort 2.91s
    median, `effort=low` 3.07s. Inside the noise. ~2.8–3.0s is simply this model's
    round-trip floor for this prompt, and no request-shaping recovers it.
  · **it IS the second leg.** Azure takes ~1.2s to say the line. `audio_fragment` caches
    by text, but an improvised line is usually novel — so where the scripted officer drew
    from a finite reviewed pool that converged toward free, this one mostly MISSES and
    pays the 1.2s again. ~3.0s + ~1.2s serialized behind one frame is the 4.2s that was
    observed. **The fix is in `_officer_frame`, not here**: the text ships the moment it
    exists and the voice follows on its own frame.

The schema below stays regardless, earned on robustness rather than speed: it makes the
reply an object instead of a fenced-JSON hunt, so a stray code fence can no longer end a
driver's turn. `parse_structured` sends `effort=low` with it, which is right for the task
and costs nothing — shallow thinking, not none. Disabling thinking on this model is
documented to emit tool calls as plain prose and leak `<thinking>` into the text, and this
text is read aloud to a driver.

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

# AI-CONTEXT: the shape of a spoken turn, as a GUARANTEE rather than a plea — the reply is
# the object, so no fence-hunting and no turn lost to a stray ```. It buys robustness, not
# speed; the latency note in the module docstring says where the seconds actually were.
# `line` is read aloud, so it is a sentence and never a field dump; `intent_key` is what
# keeps SCORING deterministic, and "" is a real value meaning the officer is closing
# rather than asking.
OFFICER_SCHEMA = {
    "type": "object",
    "properties": {
        "line": {
            "type": "string",
            "description": "What the officer says next, out loud. One or two short sentences.",
        },
        "intent_key": {
            "type": "string",
            "description": (
                "Which remaining topic key this line asks about, or \"\" when closing the stop."
            ),
        },
        "done": {
            "type": "boolean",
            "description": "True only when every topic is covered and the driver may go.",
        },
    },
    "required": ["line", "intent_key", "done"],
    "additionalProperties": False,
}


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
        payload = ai.parse_structured(
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
            required_keys=["line", "intent_key", "done"],
            schema=OFFICER_SCHEMA,
        )
    # provider outage, budget, timeout, or a reply that would not parse against the schema
    except Exception as exc:
        raise OfficerUnavailable(str(exc)) from exc

    line = (payload.get("line") or "").strip()
    if not line:
        raise OfficerUnavailable("the model returned no line")

    return ImprovisedTurn(
        line=line,
        intent_key=(payload.get("intent_key") or "").strip(),
        done=bool(payload.get("done")),
    )


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
