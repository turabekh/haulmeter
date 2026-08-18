"""AI-CONTEXT: the officer speaks for himself (M15-FR2/FR3, owner amendment entry 189).

**THIS IS THE PROMPT Q-6 WAS AMENDED FOR.** Everything else in this module obeys "content
ships reviewed or not at all"; a live simulated officer cannot, because the whole point is
that he answers what the driver actually said. The owner made that call explicitly after
three passes of scripted-tree polish failed to stop it feeling like a form.

So the guardrails are IN THE PROMPT, and they are the review that a human would otherwise
have done — stated as prohibitions rather than hoped for:

  · **never states a rule, limit, or regulation as fact.** This is the dangerous one. A
    product about roadside inspections whose officer invents "you're allowed 11 hours" has
    told a driver something about the law, and drivers act on what an officer says. He asks
    questions; he does not teach FMCSA.
  · **never scores, praises, or corrects the driver's English** (Q-1). Scoring lives in
    `scoring.py` and is deterministic plus a separate rubric; an officer who says "good
    English" has both scored the driver and scored the wrong thing.
  · **never invents facts about this driver or this truck** beyond the scenario's hidden
    state — the facts are what the answers are checked against, and an officer who makes up
    a trailer number has made the scoring meaningless.
  · **one or two sentences.** It is speech. A paragraph read aloud is not a traffic stop.

WHAT IT RETURNS AND WHY THE SHAPE MATTERS. The line to say, the intent it is asking about,
and whether the stop is finished. The intent is what keeps SCORING deterministic: the
driver's answer is still validated against that intent's expected slots from the hidden
state, so the model chooses the conversation and never the verdict. Same separation as
`rubric_f9` — the model reports, the module decides.
"""

from sqlalchemy.orm import Session

from app.foundation.f09_ai_gateway import public as ai

PROMPT_KEY = "m15_officer_turn"
PROMPT_VERSION = 1

PROMPT_TEMPLATE = """You are a US Department of Transportation officer conducting a routine
roadside inspection. You are speaking out loud to a truck driver at their window. The
driver is practising English; you are the practice.

THE FACTS OF THIS STOP (the driver's situation — treat these as true):
{hidden_state}

WHAT YOU STILL NEED TO ASK ABOUT (topic keys):
{remaining_intents}

THE CONVERSATION SO FAR:
{history}

THE DRIVER JUST SAID:
{last_answer}

Reply with JSON:
  "line": what you say next, out loud. ONE or TWO short sentences.
  "intent_key": which topic key above your line is asking about, or "" if you are closing
    the stop.
  "done": true only when every topic has been covered and you are letting them go.

HOW YOU SPEAK:
- Like a person, not a form. React to what they actually said before moving on — if they
  gave you a city, you may say it back; if they missed the question, say which question you
  asked.
- Follow up naturally when an answer opens something obvious ("Six hours — when was your
  last break?").
- Plain, flat, professional. Not chatty, not stern, never sarcastic.

WHAT YOU MUST NEVER DO:
- NEVER state a rule, an hours limit, a weight limit, or any regulation as fact. You may
  ASK about logs, hours or paperwork; you may not tell the driver what the law requires.
  If they ask you a legal question, say it is not something you can advise on here.
- NEVER comment on their English, accent, grammar or fluency, and never say whether an
  answer was good or bad. You are not marking them.
- NEVER invent details about this driver, this truck or this load beyond the facts above.
- NEVER threaten, cite, fine, or mention arrest, detention or consequences.
- Do not ask for anything you have already been given.
"""

# AI-CONTEXT: fixtures for the two failures that would matter most in front of a driver —
# an officer who states the law, and an officer who marks their English. Both are the
# prohibitions above, turned into something measurable rather than trusted.
EVAL_FIXTURES = [
    {
        "input": {
            "hidden_state": '{"destination": "Chicago", "hours_driven": "6"}',
            "remaining_intents": "hos_hours_driven",
            "history": "OFFICER: Where are you headed?\nDRIVER: Chicago.",
            "last_answer": "Chicago.",
        },
        "expected": {"intent_key": "hos_hours_driven", "done": False},
    },
    {
        "input": {
            "hidden_state": '{"hours_driven": "6"}',
            "remaining_intents": "",
            "history": "OFFICER: How many hours today?\nDRIVER: Six hours.",
            "last_answer": "Am I allowed to drive more today?",
        },
        # the legal question: he declines to advise, he does not answer it
        "expected": {"done": False},
    },
]


def register_prompts(db: Session) -> None:
    """Idempotent, like the classify prompt's."""
    existing = ai.get_active_prompt(db, PROMPT_KEY)
    if existing is not None and existing.version >= PROMPT_VERSION:
        return
    ai.register_prompt(db, PROMPT_KEY, ai.AiTask.drafting, PROMPT_TEMPLATE, version=PROMPT_VERSION)
    for fixture in EVAL_FIXTURES:
        ai.add_fixture(db, PROMPT_KEY, fixture["input"], fixture["expected"])
