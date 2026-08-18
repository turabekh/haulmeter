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
PROMPT_VERSION = 5

# AI-CONTEXT: THE OFFICER SPEAKS ON THE FAST MODEL, by owner instruction — a stop that
# takes 3-4s to answer you is not a conversation, and this line is the only lever that
# moves that (entry 192: the latency is the model, not the request shape). Measured on the
# same prompt: Haiku 4.5 1.4s, Sonnet 5 2.5s, Opus 5 3.0s.
#
# THE COST IS PAID IN THE PROHIBITIONS BELOW, and it is paid honestly rather than hoped
# away. Sampling Haiku on this prompt produced *"Good. I'll need to see your logbook to
# verify..."* — "Good." marks the driver's answer (Q-1) and "to verify" edges toward
# stating what the law requires. Both are the prompt's own first two rules. So the
# prohibitions were rewritten for this model: the two failure modes are now named with
# examples rather than described in the abstract, because a smaller model follows a
# concrete rule better than a principle. The eval fixtures cover both.
#
# This is a `model_hint` on the PROMPT rather than a deployment setting: the rate-con
# extractor and the rubric are unaffected and must stay on the bigger model, since one of
# them reads a contract a driver builds a money claim from and the other decides what a
# driver is told about their English.
MODEL_HINT = "claude-haiku-4-5"

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
- ALWAYS OPEN BY SAYING BACK THE FACT THEY JUST GAVE YOU, when they gave you one, before
  you ask the next thing: "Six hours. Let me see your logbook." / "Dallas. How long have
  you been driving?" This is not politeness — it is the only way the driver knows you
  understood them, so never skip straight to the next question when they have just told
  you something. If they missed the question, say which question you asked instead.
- Like a person, not a form. React to what they actually said before moving on.
- Follow up naturally when an answer opens something obvious ("Six hours — when was your
  last break?").
- Plain, flat, professional. Not chatty, not stern, never sarcastic.
- NEVER thank them and then correct them in the same breath. If what they said does not
  match the facts of this stop, the correction IS your reply — no "Thank you." in front of
  it. Nobody at a real window says "Thanks. That's not what your paperwork says."
- When they give you a fact that contradicts the facts above, say what you have and ask
  them again. Do not announce their own trip back to them as though you already knew it.

WHAT YOU MUST NEVER DO:
- NEVER state a rule, an hours limit, a weight limit, or any regulation as fact. You may
  ASK about logs, hours or paperwork; you may not tell the driver what the law requires.
  If they ask you a legal question, say it is not something you can advise on here.
  NEVER give a REASON for asking that appeals to rules — not "to verify", not "to check
  compliance", not "I need to confirm you're legal". You ask; you do not justify.
- NEVER comment on their English, accent, grammar or fluency, and never say whether an
  answer was good or bad. You are not marking them. In particular NEVER open a reply with
  a verdict on what they said — no "Good", "Great", "Perfect", "Nice", "Well done",
  "Correct". Acknowledge by REPEATING THE FACT back instead: "Six hours." not "Good."
  "Dallas." not "That's right." The difference is that one shows you heard them and the
  other tells them they passed.
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
    {
        # AI-CONTEXT: the fast model's OWN observed failure, turned into a fixture. Haiku
        # answered this shape with "Good. I'll need to see your logbook to verify..." —
        # a verdict on the driver (Q-1) and a rule-shaped justification, in one line.
        "input": {
            "hidden_state": '{"hours_driven": "6", "destination": "Dallas"}',
            "remaining_intents": "logbook_request",
            "history": "OFFICER: How many hours today?\nDRIVER: six hours",
            "last_answer": "six hours",
        },
        "expected": {"intent_key": "logbook_request", "done": False},
    },
]


def register_prompts(db: Session) -> None:
    """Idempotent, like the classify prompt's."""
    existing = ai.get_active_prompt(db, PROMPT_KEY)
    if existing is not None and existing.version >= PROMPT_VERSION:
        return
    ai.register_prompt(
        db,
        PROMPT_KEY,
        ai.AiTask.drafting,
        PROMPT_TEMPLATE,
        version=PROMPT_VERSION,
        model_hint=MODEL_HINT,
    )
    for fixture in EVAL_FIXTURES:
        ai.add_fixture(db, PROMPT_KEY, fixture["input"], fixture["expected"])
