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
  · **the second leg is real but SMALL, and the first figure for it was measured in the
    wrong place.** From a laptop in Tashkent, Azure took ~1.2s to say a line. From the
    box — us-central1, next door to Azure — it takes **0.25s** (median of 3, 0.22–0.60).
    `audio_fragment` caches by text, so a repeated line costs nothing at all; a novel one
    costs a quarter second. The frame split below is therefore worth ~0.25s on a miss and
    ~0 on a hit, **not the 1.2s the first version of this comment claimed**.
  · **so the turn is the MODEL, almost entirely.** Measured end to end on production,
    `ready` → officer text: **3.3s, 3.6s, 3.9s, 4.1s, 4.2s, 4.7s** (plus one 6.3s cold
    first call after a deploy). Subtract the 0.25s and what is left is the model. There is
    no request shape that fixes that — only a different model, which is an owner decision
    (entry 190) because the prompt's prohibitions are the review a human would otherwise
    have done and how well they hold is a property of the model.

**The split in `_officer_frame` is kept on correctness, not on the second it does not buy:**
a TTS failure used to take the whole turn down with it, and the closing frame used to take
the driver's verdict down with it. It also costs nothing when the cache hits.

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
OFFICER_MODE_DEFAULT = "llm"


def register_config(db: DbSession) -> None:
    """DECLARE the kill switch, so an operator can find it.

    AI-CONTEXT: `set_config` writes whether or not a key is declared, so the revert always
    worked mechanically — and it was still the wrong kind of broken. `declared_configs`
    walks `ConfigDeclaration`, which is what /admin lists, so an undeclared key is a knob
    that exists and cannot be found. Entry 189 promises an operator can stop unreviewed
    officer lines "in seconds without shipping anything"; that promise was only true for
    someone who already knew the key existed and had a database shell. Caught on the box
    by querying the registry rather than trusting the sentence.

    This is the same failure `register_module` already records for m11 — a prompt that was
    registered lazily and so was absent from /admin until an unrelated endpoint happened
    to be called. A knob nobody can find is not a control.
    """
    from app.foundation.f13_flags import public as flags

    flags.register_config(
        db,
        OFFICER_MODE_KEY,
        OFFICER_MODE_DEFAULT,
        description=(
            "Roadside officer: 'llm' improvises each line (unreviewed text, Q-6 amended "
            "by entry 189); 'scripted' reverts to reviewed content only. The kill switch."
        ),
    )


def officer_mode(db: DbSession) -> str:
    """`llm` or `scripted`. A config key so a bad line can be stopped in seconds.

    AI-CONTEXT: this is the guardrail that makes an unreviewed officer survivable. Q-6 was
    amended for the live simulation, not repealed — and the compensating control for
    "content reaches a driver without review" is an operator who can revert to reviewed
    content without waiting for a build.
    """
    from app.foundation.f13_flags import public as flags

    return str(flags.get_config(db, OFFICER_MODE_KEY, OFFICER_MODE_DEFAULT))
