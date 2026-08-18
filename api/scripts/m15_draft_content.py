"""AI-CONTEXT: draft the English content FR5's loop needs, for a human to review.

WHY THIS IS A SCRIPT AND NOT A SEED. `seed_demo` is dev-only and plants demo facilities;
this content belongs on production, where the driver is. It writes `draft` rows and
nothing else — Q-6 means a human reviews and releases them in `/admin/roadside`, and
until that happens not one line here can reach a driver.

WHAT IT DRAFTS AND WHY EACH IS NEEDED:

  · **more phrasings per intent.** FR5 asks a driver to "hear 3–6 equivalents"; the pool
    stood at two released phrasings per intent, so the phrase family was one line long.
    A family of one teaches nothing about the shape of a question.
  · **a model answer per intent.** FR5's shadowing step — "hear a clear model answer,
    repeat it" — had nowhere to draw from at all.

IT IS IDEMPOTENT ON TEXT. The job runs again after content is released; re-inserting the
same sentence as a fresh draft would give a reviewer the same line to approve forever.

NOT DRAFTED HERE: the native-language explanations. Drafting Uzbek nobody has reviewed is
cheap and worthless — Q-9 already specifies what a driver sees while that content does not
exist, and an unreviewed draft in the table would be a thing waiting to be released by
mistake.
"""

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.m15_roadside.domain.enums import ContentStatus, Difficulty
from app.modules.m15_roadside.domain.models import (
    Intent,
    ModelAnswer,
    OfficerAck,
    PhraseVariant,
    RepairLine,
)
from db_registry import import_all_models

# officer phrasings, in the register an officer actually uses at a window — including the
# clipped, ungrammatical ones ("Where you delivering to?"), because those are the hardest
# to follow and are exactly what a driver needs to have heard before.
PHRASINGS = {
    "destination": [
        "Where are you going with this load?",
        "What's your final stop?",
        "Where you delivering to?",
        "Where's this load headed?",
    ],
    "hos_hours_driven": [
        "How much drive time do you have today?",
        "How many hours are on your clock today?",
        "How many hours since you started?",
        "What have you got for hours today?",
    ],
    "logbook_request": [
        "Let me see your log for today.",
        "I need to see your ELD.",
        "Pull up your logs for me.",
        "Show me your record of duty status.",
    ],
}

# what a competent answer sounds like. Short, complete, and ordinary — a model answer that
# sounds like a textbook teaches a driver to sound like a textbook at a truck window.
MODEL_ANSWERS = {
    "destination": "I'm headed to Chicago, Illinois.",
    "hos_hours_driven": "I've been driving six hours today.",
    "logbook_request": "Yes sir, here is my logbook.",
}


# AI-CONTEXT: what an officer says BETWEEN questions. Short, flat, and unremarkable on
# purpose — an officer at a window is processing you, not encouraging you, and an
# acknowledgement that sounds pleased ("Great!") teaches a driver to expect warmth that a
# real stop will not supply. Neutral is the accurate register and also the kind one: it
# does not tell a nervous driver they did well when they did not.
# AI-CONTEXT: FR2's repair branches — what the officer says when you answered a DIFFERENT
# question. E3's own example is the register: "I'm asking where you picked UP this load."
# Each one NAMES the confusion rather than restating the question louder, because the
# driver did understand English well enough to answer something — they answered the wrong
# thing, and telling them which thing is the help.
REPAIRS = {
    "destination": [
        "I'm asking where you're going, not what you're carrying.",
        "Where are you delivering this load to?",
    ],
    "hos_hours_driven": [
        "I'm asking how long you've been driving today, not where you're headed.",
        "Hours. How many hours behind the wheel today?",
    ],
    "logbook_request": [
        "I'm asking to see your logbook.",
        "Your logs — can you show me your logs?",
    ],
}

# how a stop starts and how it ends. Without these the simulation began mid-interrogation
# and finished by running out of questions, which is how a form ends and not how a person
# lets you go.
OPENINGS = [
    "Afternoon. I'll need to ask you a few questions.",
    "Good afternoon. Just a routine check today.",
]
CLOSINGS = [
    "Alright, you're good to go. Drive safe.",
    "That's everything. Thanks for your time.",
]

# AI-CONTEXT: THE SOUND A PERSON MAKES WHILE THEY ARE STILL LISTENING — played the moment
# the driver stops speaking, over the ~1.5s the machine needs to transcribe and think.
#
# DELIBERATELY NON-COMMITTAL, and this is the whole design of the list. The owner suggested
# "mmm thanks" and "ok mmm I see"; both of those CLAIM SOMETHING — that the answer landed,
# that it was understood — and they are spoken before anything has been transcribed. When
# the next thing out of the officer's mouth is "Sorry, I didn't catch that", an "I see" in
# front of it is the machine having pretended. These claim nothing at all, which is exactly
# why people use them: a real officer fills the same gap the same way while still deciding.
#
# They are also never EVALUATIVE (Q-1). "Good." and "Got it." are absent on purpose.
THINKING = [
    "Mm-hm.",
    "Mm.",
    "Uh-huh.",
    "Right.",
]

ACKS = [
    "Okay.",
    "Alright.",
    "Thank you.",
    "Got it.",
    "Mm-hm.",
    "Okay, thank you.",
]


def main() -> None:
    # AI-CONTEXT: the WHOLE registry, not just m15's models — `model_answer.audio_ref` is
    # a foreign key to `f06.document`, and SQLAlchemy cannot resolve the mapper if only
    # this module's models were imported. Same shape as trap 4: a partial import fails
    # somewhere that looks unrelated to the omission.
    import_all_models()
    db = SessionLocal()
    added_variants = added_answers = 0

    for key, texts in PHRASINGS.items():
        intent = db.scalar(select(Intent).where(Intent.key == key))
        if intent is None:
            print(f"  skip {key}: no such intent on this box")
            continue
        rows = list(
            db.scalars(select(PhraseVariant).where(PhraseVariant.intent_id == intent.id))
        )
        existing = {v.text for v in rows}
        # version numbers continue the intent's own sequence so a reviewer sees an ordered
        # list rather than four rows all claiming to be version 1
        top = max([v.version for v in rows] or [0])
        for text in texts:
            if text in existing:
                continue
            top += 1
            db.add(PhraseVariant(
                intent_id=intent.id,
                text=text,
                difficulty=Difficulty.clear,
                status=ContentStatus.draft,
                version=top,
            ))
            added_variants += 1

    for key, text in MODEL_ANSWERS.items():
        intent = db.scalar(select(Intent).where(Intent.key == key))
        if intent is None:
            continue
        already = db.scalar(
            select(ModelAnswer).where(
                ModelAnswer.intent_id == intent.id, ModelAnswer.text == text
            )
        )
        if already is not None:
            continue
        db.add(ModelAnswer(intent_id=intent.id, text=text, status=ContentStatus.draft))
        added_answers += 1

    added_acks = 0
    for kind, texts in (
        ("ack", ACKS),
        ("opening", OPENINGS),
        ("closing", CLOSINGS),
        ("thinking", THINKING),
    ):
        for text in texts:
            # AI-CONTEXT: (text, KIND), not text alone. The same words legitimately serve
            # two roles — "Mm-hm." is both an acknowledgement after an answer and a noise
            # made while still listening — and a text-only check silently dropped the
            # second one, so the thinking pool lost its most natural member without
            # anything reporting a skip.
            existing = db.scalar(
                select(OfficerAck).where(OfficerAck.text == text, OfficerAck.kind == kind)
            )
            if existing is not None:
                continue
            db.add(OfficerAck(text=text, kind=kind, status=ContentStatus.draft))
            added_acks += 1

    added_repairs = 0
    for key, texts in REPAIRS.items():
        intent = db.scalar(select(Intent).where(Intent.key == key))
        if intent is None:
            continue
        for text in texts:
            if db.scalar(select(RepairLine).where(RepairLine.text == text)) is not None:
                continue
            db.add(RepairLine(intent_id=intent.id, text=text, status=ContentStatus.draft))
            added_repairs += 1
    print(f"  + {added_repairs} repair lines")

    db.commit()
    print(f"  + {added_acks} officer acknowledgements")
    print(
        f"m15 content drafted: +{added_variants} phrasings, +{added_answers} model answers "
        f"— ALL `draft`. Review and release them in /admin/roadside (Q-6)."
    )


if __name__ == "__main__":
    main()
