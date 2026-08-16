"""AI-CONTEXT: the classify prompt, proven by QUERYING the registry (E3 §E3.8 build notes).

The trap this file is written against, in the kickoff's own words: *prove the version
advanced by querying the registry, not by the register call returning*. `register_prompt`
returns a row whether or not anything changed, so a check built on its return value learns
nothing about what is actually active — the same shape as reading a migration's exit line
and believing it.

The other half is quality law Q-1, and the fixtures carry it: "I go Chicago" must beat
"Yes." on a destination question. A rubric that gets that backwards is scoring accent
while claiming not to, and the fixture is what makes the claim checkable.
"""

from app.foundation.f09_ai_gateway import public as ai
from app.modules.m15_roadside.domain import prompts


def test_the_prompt_is_active_after_registration_queried_not_assumed(db):
    """Query `get_active_prompt`, never `register_prompt`'s return value."""
    prompts.register_prompts(db)

    active = ai.get_active_prompt(db, prompts.PROMPT_KEY)
    assert active is not None, "the registry must hold it, not the call that made it"
    assert active.version == prompts.PROMPT_VERSION
    assert active.task is ai.AiTask.classify


def test_registration_is_idempotent_and_does_not_pile_up_versions(db):
    prompts.register_prompts(db)
    prompts.register_prompts(db)
    prompts.register_prompts(db)

    active = ai.get_active_prompt(db, prompts.PROMPT_KEY)
    assert active.version == prompts.PROMPT_VERSION
    # and the fixtures did not triple either
    assert len(ai.list_fixtures(db, prompts.PROMPT_KEY)) == len(prompts.EVAL_FIXTURES)


def test_the_module_boot_path_registers_it(db):
    """It registers at BOOT, not lazily inside a request — asserted through register_all.

    A prompt registered on first use is absent from the registry until someone happens to
    call the right endpoint, which is m11's recorded defect.
    """
    from app import module_registry

    module_registry.register_all(db)
    assert ai.get_active_prompt(db, prompts.PROMPT_KEY) is not None


def test_the_eval_fixtures_land_in_the_registry(db):
    prompts.register_prompts(db)
    fixtures = ai.list_fixtures(db, prompts.PROMPT_KEY)
    assert len(fixtures) == len(prompts.EVAL_FIXTURES)


def test_the_fixtures_encode_Q1_broken_english_beats_fluent_evasion(db):
    """Q-1, as a property of the corpus rather than a promise in a docstring.

    E3 states it directly: "I go Chicago" must outscore "Yes." on a destination question.
    If a future edit ever inverted these two expectations, the rubric would be rewarding
    fluency — which is scoring accent under another name.
    """
    by_transcript = {f["input"]["transcript"]: f["expected"] for f in prompts.EVAL_FIXTURES}

    broken_but_meaningful = by_transcript["I go Chicago"]
    fluent_but_empty = by_transcript["Yes."]

    assert broken_but_meaningful["intent_matched"] is True
    assert broken_but_meaningful["slots_filled"] == ["destination"]
    assert fluent_but_empty["intent_matched"] is False
    assert fluent_but_empty["slots_filled"] == []


def test_a_fluent_answer_to_the_wrong_question_does_not_pass(db):
    """The mirror case: well-formed English, wrong question, no credit."""
    by_transcript = {f["input"]["transcript"]: f["expected"] for f in prompts.EVAL_FIXTURES}
    wrong_question = by_transcript["I am delivering furniture to a warehouse."]
    assert wrong_question["intent_matched"] is False


def test_unintelligible_is_not_scored_as_failure(db):
    """Q-2's shape at the rubric level: unclear is excluded, not marked wrong."""
    by_transcript = {f["input"]["transcript"]: f["expected"] for f in prompts.EVAL_FIXTURES}
    unclear = by_transcript["[unintelligible]"]
    assert unclear["intelligible"] is False


def test_the_prompt_text_forbids_the_dimensions_Q1_bans(db):
    """Q-1 has to be in the PROMPT, not only in the tests.

    A rubric that merely says "score the response" invites a model to score the English,
    because that is the salient thing about a second-language speaker. Naming the
    forbidden dimensions is what keeps them out.
    """
    text = prompts.PROMPT_TEMPLATE.lower()
    for banned in ("accent", "grammar", "fluency", "native"):
        assert banned in text, f"the prompt must explicitly forbid judging {banned}"
    assert "meaning only" in text
