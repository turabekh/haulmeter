"""AI-CONTEXT: M15's F9 prompt and its eval fixtures (E3.0 row 6, §E3.1.2 FR2).

WHAT THIS PROMPT DOES AND WHAT IT MUST NEVER DO. It classifies a driver's transcript
against the intent an officer asked for, and reports which required slots were filled. It
does **not** score English, and it does not see or receive anything about the driver.
Quality law Q-1 is the reason and it is absolute: *accent is never scored*. The rubric
below asks only whether the meaning arrived, which is why the fixtures deliberately
include broken-but-intelligible English marked as a PASS.

The fixtures are not decoration. E3 keeps a corpus discipline for exactly this: a rubric
nobody measured is a rubric that drifts, and the first thing it drifts toward is rewarding
fluency, because fluency is what a language model finds easy to like.

REGISTRATION IS PROVEN BY QUERYING THE REGISTRY, never by `register_prompt` returning. It
returns a row whether or not the version advanced, and a session that reads the return
value learns nothing about what is actually active — which is the same shape as reading a
migration's exit line.
"""

from sqlalchemy.orm import Session

from app.foundation.f09_ai_gateway import public as ai

PROMPT_KEY = "m15_intent_classify"
PROMPT_VERSION = 2

# AI-CONTEXT: Q-1 lives in the prompt text itself, not only in the tests. A rubric that
# says "score the response" invites a model to score the ENGLISH, because that is the
# salient thing about a driver speaking a second language. Naming the forbidden dimension
# is what keeps it out — the same reason §12.3's glossary law is stated to translators
# rather than assumed.
PROMPT_TEMPLATE = """You are checking whether a truck driver's answer carried the MEANING
a roadside officer asked for.

The officer asked: {officer_line}
The intent behind it: {canonical_meaning}
Required pieces of information: {required_slots}
The driver said: {transcript}

Report, as JSON:
  "intent_matched": true if the driver answered THIS question, false if they answered a
    different one or did not understand it.
  "slots_filled": the required pieces of information that are present in the answer.
  "slots_missing": those that are not.
  "intelligible": true if a person could understand what was meant.
  "asked_for_repeat": true if the driver did not answer but ASKED THE OFFICER TO REPEAT
    or rephrase — "sorry?", "say again", "could you repeat that", "I didn't catch that".

RULES YOU MUST FOLLOW:
- Judge MEANING ONLY. Never judge accent, grammar, fluency, vocabulary size, verb tense,
  article use, or how native the speaker sounds.
- "I go Chicago" answers a destination question completely. So does "Chicago". Both are
  intent_matched with the destination slot filled.
- A grammatically perfect answer to the WRONG question is intent_matched false.
- If you cannot tell what was said, set intelligible false. Do not guess, and do not
  penalise — an unclear recording is not a failed answer.
- ASKING THE OFFICER TO REPEAT IS NOT A WRONG ANSWER. It is what a careful driver does
  when they did not hear. Set asked_for_repeat true and intent_matched false; the two
  together mean "they did not answer, and here is why" rather than "they got it wrong".
"""

# AI-CONTEXT: the fixture that matters most is the first one, and it is E3's own example.
# "I go Chicago" must outscore "Yes." on a destination question — broken English that
# carries the meaning beats fluent English that does not. A rubric that gets this backwards
# is one that scores accent while claiming not to.
EVAL_FIXTURES = [
    # AI-CONTEXT: the repeat request, and it is here because the field existed for a
    # version without the prompt ever asking for it — `rubric_f9` parsed
    # `asked_for_repeat` out of a payload no model had been told to produce, so
    # REPETITION_REQUIRED could not fire in production and the officer never repeated
    # himself. Measured, not reasoned: a live session answered "Sorry, could you say that
    # again?" and was scored INTENT_MISUNDERSTOOD + IRRELEVANT.
    {
        "input": {
            "officer_line": "How many hours have you been driving today?",
            "canonical_meaning": "the driver states hours driven today",
            "required_slots": "hours",
            "transcript": "Sorry, could you say that again?",
        },
        "expected": {
            "intent_matched": False,
            "slots_filled": [],
            "slots_missing": ["hours"],
            "intelligible": True,
            "asked_for_repeat": True,
        },
    },
    {
        "input": {
            "officer_line": "Where are you headed?",
            "canonical_meaning": "the driver states their destination",
            "required_slots": "destination",
            "transcript": "I go Chicago",
        },
        "expected": {
            "intent_matched": True,
            "slots_filled": ["destination"],
            "slots_missing": [],
            "intelligible": True,
        },
    },
    {
        "input": {
            "officer_line": "Where are you headed?",
            "canonical_meaning": "the driver states their destination",
            "required_slots": "destination",
            "transcript": "Yes.",
        },
        "expected": {
            "intent_matched": False,
            "slots_filled": [],
            "slots_missing": ["destination"],
            "intelligible": True,
        },
    },
    {
        "input": {
            "officer_line": "How many hours have you been driving today?",
            "canonical_meaning": "the driver states hours driven today",
            "required_slots": "hours",
            "transcript": "Six hour, since morning",
        },
        "expected": {
            "intent_matched": True,
            "slots_filled": ["hours"],
            "slots_missing": [],
            "intelligible": True,
        },
    },
    {
        "input": {
            "officer_line": "How many hours have you been driving today?",
            "canonical_meaning": "the driver states hours driven today",
            "required_slots": "hours",
            "transcript": "I am delivering furniture to a warehouse.",
        },
        # fluent, well-formed, and an answer to a different question
        "expected": {
            "intent_matched": False,
            "slots_filled": [],
            "slots_missing": ["hours"],
            "intelligible": True,
        },
    },
    {
        "input": {
            "officer_line": "May I see your logbook?",
            "canonical_meaning": "the driver acknowledges and offers the logbook",
            "required_slots": "acknowledgement",
            "transcript": "[unintelligible]",
        },
        # Q-2's shape at the rubric level: unclear is not failed
        "expected": {
            "intent_matched": False,
            "slots_filled": [],
            "slots_missing": ["acknowledgement"],
            "intelligible": False,
        },
    },
]


def register_prompts(db: Session) -> None:
    """Register the classify prompt and its fixtures. Idempotent."""
    existing = ai.get_active_prompt(db, PROMPT_KEY)
    if existing is not None and existing.version >= PROMPT_VERSION:
        return
    ai.register_prompt(
        db,
        PROMPT_KEY,
        ai.AiTask.classify,
        PROMPT_TEMPLATE,
        version=PROMPT_VERSION,
    )
    for fixture in EVAL_FIXTURES:
        ai.add_fixture(db, PROMPT_KEY, fixture["input"], fixture["expected"])
