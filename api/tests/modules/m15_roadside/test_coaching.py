"""AI-CONTEXT: the teaching loop (M15-FR5), and the four things it must never do.

FR5's validation is the module's north star — *a driver who failed an intent at baseline
passes its holdout after completing the loop, observed in `skill_state`* — and until this
session `skill_state` had no writer, so the measurement could not be taken at all.

What these hold, in order of how badly each would fail a driver:

  Q-9  a locale with no released coaching shows NOTHING, never silent English
  Q-6  every piece of the loop is released content or it is absent
  Q-5  the retest never spends a holdout — those belong to FR7's reassessment
  Q-2  what could not be heard is not a language failure and is never coached
"""

from app.foundation.f01_identity import public as identity
from app.modules.m15_roadside.domain import coaching
from app.modules.m15_roadside.domain import models as m


def _intent(db, key="hos_hours_driven"):
    intent = m.Intent(key=key, domain="paperwork", canonical_meaning="hours driven")
    db.add(intent)
    db.flush()
    return intent


def _variant(db, intent, text, *, status=m.ContentStatus.released, holdout=False, version=1):
    variant = m.PhraseVariant(
        intent_id=intent.id, text=text, difficulty=m.Difficulty.clear,
        status=status, holdout=holdout, version=version,
    )
    db.add(variant)
    db.flush()
    return variant


def _session(db, account_id=None):
    """Through `start_session`, not by hand — the row carries NOT NULL columns (`mode`,
    `consent_at`) that only the real entry point fills, and a hand-built one asserts
    against a shape the product never produces."""
    from app.modules.m15_roadside.domain import session_loop as loop

    scenario = m.ScenarioVersion(
        version=1, difficulty=m.Difficulty.clear,
        allowed_intents=["hos_hours_driven"], status=m.ContentStatus.released,
    )
    db.add(scenario)
    db.flush()
    return loop.start_session(
        db, scenario=scenario, account_id=account_id or _account(db).id, consented=True
    )


def _recording(db):
    """A real document: `Turn.audio_ref` is a foreign key, so a bare uuid4 asserts against
    a row shape the database will not accept."""
    from app.modules.m15_roadside.domain import audio as m15_audio

    return m15_audio.store_driver_audio(db, b"officer-line-bytes")


def _exchange(db, session, intent, asked, *, tags, officer_audio=None):
    """An officer turn and the driver turn that answered it."""
    officer = m.Turn(
        session_id=session.id, seq=1, speaker=m.Speaker.officer,
        intent_id=intent.id, transcript=asked, audio_ref=officer_audio,
    )
    driver = m.Turn(
        session_id=session.id, seq=2, speaker=m.Speaker.driver,
        intent_id=intent.id, transcript="uh, furniture", failure_tags=list(tags),
    )
    db.add_all([officer, driver])
    db.flush()
    return driver


# --- what gets taught ------------------------------------------------------------------


def test_a_missed_intent_is_taught(db):
    intent = _intent(db)
    asked = _variant(db, intent, "How many hours have you been driving today?")
    _variant(db, intent, "How long you been behind the wheel?", version=2)
    session = _session(db)
    turn = _exchange(db, session, intent, asked.text, tags=["INTENT_MISUNDERSTOOD"])

    plan = coaching.coaching_for(db, turn=turn, locale="uz")

    assert plan is not None
    assert plan.missed_question == asked.text
    assert [v.text for v in plan.phrase_family] == ["How long you been behind the wheel?"]


def test_the_improvised_question_is_still_replayable(db):
    """FR5 step 1 is REPLAY THE MISSED QUESTION, and the improvising officer broke it.

    The replay used to be found by matching the officer's words against the released
    phrase variants — sound while every line the officer spoke came out of that table.
    Since entry 194 he composes his own, so the match never succeeds and the button
    silently stopped rendering: a driver reads the question they missed with no way to
    hear it again. The audio was never missing — it is on the officer's own turn, the
    exact recording the driver heard at the stop.
    """
    intent = _intent(db)
    _variant(db, intent, "How many hours have you been driving today?")
    session = _session(db)
    spoken = _recording(db)
    turn = _exchange(
        db, session, intent,
        "I understand the weather is nice. Now, how long have you been driving?",
        tags=["INTENT_MISUNDERSTOOD"], officer_audio=spoken,
    )

    plan = coaching.coaching_for(db, turn=turn, locale="uz")

    assert plan.missed_question_audio == spoken


def test_a_scripted_question_replays_its_own_recording(db):
    """The scripted officer speaks a released variant, and that variant's audio is what
    the driver heard. Reading it off the turn keeps working for him too."""
    intent = _intent(db)
    asked = _variant(db, intent, "How many hours have you been driving today?")
    spoken = _recording(db)
    turn = _exchange(
        db, _session(db), intent, asked.text,
        tags=["INTENT_MISUNDERSTOOD"], officer_audio=spoken,
    )

    plan = coaching.coaching_for(db, turn=turn, locale="uz")

    assert plan.missed_question_audio == spoken


def test_what_could_not_be_heard_is_never_coached(db):
    """Q-2. Teaching a driver because the recogniser struggled would tell them their
    English failed when the microphone did."""
    intent = _intent(db)
    asked = _variant(db, intent, "How many hours have you been driving today?")

    for tag in ("UNINTELLIGIBLE", "NO_RESPONSE"):
        # a session each: `turn.seq` is unique per session, and reusing one would fail on
        # the constraint rather than on the assertion
        turn = _exchange(db, _session(db), intent, asked.text, tags=[tag])
        assert coaching.coaching_for(db, turn=turn, locale="uz") is None


def test_asking_for_a_repeat_is_never_coached(db):
    """Entry 184: a repeat request is a diagnostic. Coaching it would teach a driver that
    asking for clarity is a language problem."""
    intent = _intent(db)
    asked = _variant(db, intent, "How many hours have you been driving today?")
    session = _session(db)
    turn = _exchange(db, session, intent, asked.text, tags=["REPETITION_REQUIRED"])

    assert coaching.coaching_for(db, turn=turn, locale="uz") is None


def test_a_good_answer_is_never_coached(db):
    intent = _intent(db)
    asked = _variant(db, intent, "How many hours have you been driving today?")
    session = _session(db)
    turn = _exchange(db, session, intent, asked.text, tags=[])

    assert coaching.coaching_for(db, turn=turn, locale="uz") is None


# --- Q-9: never silent English ----------------------------------------------------------


def test_a_locale_with_no_released_coaching_gets_NOTHING(db):
    """THE ONE Q-9 EXISTS FOR. An English explanation shown to an Uzbek speaker who was
    promised their own language is worse than an honest absence — it looks like the
    product tried."""
    intent = _intent(db)
    asked = _variant(db, intent, "How many hours have you been driving today?")
    db.add(m.CoachingContent(
        intent_id=intent.id, locale="en", explanation="AN ENGLISH EXPLANATION",
        review_status=m.ContentStatus.released,
    ))
    db.flush()
    session = _session(db)
    turn = _exchange(db, session, intent, asked.text, tags=["INTENT_MISUNDERSTOOD"])

    plan = coaching.coaching_for(db, turn=turn, locale="uz")

    assert plan.explanation is None, "English leaked into an Uzbek driver's coaching"


def test_draft_coaching_never_reaches_a_driver(db):
    """Q-6 inside the teaching loop — F9 may draft an explanation; a driver may not see it
    until a human has read it."""
    intent = _intent(db)
    asked = _variant(db, intent, "How many hours have you been driving today?")
    db.add(m.CoachingContent(
        intent_id=intent.id, locale="uz", explanation="a drafted explanation",
        review_status=m.ContentStatus.draft,
    ))
    db.flush()
    session = _session(db)
    turn = _exchange(db, session, intent, asked.text, tags=["INTENT_MISUNDERSTOOD"])

    assert coaching.coaching_for(db, turn=turn, locale="uz").explanation is None


def test_released_coaching_in_the_drivers_language_is_shown(db):
    """The other side — otherwise every assertion above passes on a loop that teaches
    nothing to anyone."""
    intent = _intent(db)
    asked = _variant(db, intent, "How many hours have you been driving today?")
    db.add(m.CoachingContent(
        intent_id=intent.id, locale="uz", explanation="'clock' — bu HOS vaqti",
        glosses={"clock": "qolgan haydash vaqti"}, review_status=m.ContentStatus.released,
    ))
    db.flush()
    session = _session(db)
    turn = _exchange(db, session, intent, asked.text, tags=["INTENT_MISUNDERSTOOD"])

    plan = coaching.coaching_for(db, turn=turn, locale="uz")

    assert plan.explanation == "'clock' — bu HOS vaqti"
    assert plan.glosses["clock"] == "qolgan haydash vaqti"


# --- Q-5 / Q-6 on the retest and the model answer ---------------------------------------


def test_the_retest_never_spends_a_holdout(db):
    """Q-5 and owner decision 185. Holdouts are FR7's, and a driver tested on the item
    they just drilled has been measured on memory."""
    intent = _intent(db)
    asked = _variant(db, intent, "How many hours have you been driving today?")
    holdout = _variant(
        db, intent, "What time did you start this morning?", holdout=True, version=2
    )
    _variant(db, intent, "How long you been behind the wheel?", version=3)
    session = _session(db)
    turn = _exchange(db, session, intent, asked.text, tags=["INTENT_MISUNDERSTOOD"])

    plan = coaching.coaching_for(db, turn=turn, locale="uz")

    assert plan.retest_variant_id != holdout.id
    assert holdout.id not in [v.id for v in plan.phrase_family]


def test_the_retest_is_a_different_phrasing_from_the_one_missed(db):
    intent = _intent(db)
    asked = _variant(db, intent, "How many hours have you been driving today?")
    other = _variant(db, intent, "How long you been behind the wheel?", version=2)
    session = _session(db)
    turn = _exchange(db, session, intent, asked.text, tags=["INTENT_MISUNDERSTOOD"])

    assert coaching.coaching_for(db, turn=turn, locale="uz").retest_variant_id == other.id


def test_a_draft_model_answer_is_never_shadowed(db):
    """Q-6 again: shadowing means the driver REPEATS it aloud. Unreviewed text is the last
    thing to put in a driver's mouth."""
    intent = _intent(db)
    asked = _variant(db, intent, "How many hours have you been driving today?")
    db.add(m.ModelAnswer(intent_id=intent.id, text="I have been driving six hours today.",
                         status=m.ContentStatus.draft))
    db.flush()
    session = _session(db)
    turn = _exchange(db, session, intent, asked.text, tags=["INTENT_MISUNDERSTOOD"])

    assert coaching.coaching_for(db, turn=turn, locale="uz").model_answer is None


def test_a_released_model_answer_is_offered(db):
    intent = _intent(db)
    asked = _variant(db, intent, "How many hours have you been driving today?")
    db.add(m.ModelAnswer(intent_id=intent.id, text="I have been driving six hours today.",
                         status=m.ContentStatus.released))
    db.flush()
    session = _session(db)
    turn = _exchange(db, session, intent, asked.text, tags=["INTENT_MISUNDERSTOOD"])

    plan = coaching.coaching_for(db, turn=turn, locale="uz")
    assert plan.model_answer == "I have been driving six hours today."


# --- skill_state: the north star that had no writer --------------------------------------


def _account(db):
    import uuid

    return identity.register_account(db, f"coach-{uuid.uuid4().hex[:8]}@example.com", "pw-123456")


def test_practice_is_recorded_against_the_driver(db):
    intent = _intent(db)
    variant = _variant(db, intent, "How many hours have you been driving today?")
    account = _account(db)

    state = coaching.record_practice(
        db, account_id=account.id, variant_id=variant.id, success=True
    )

    assert state.exposure_count == 1
    assert state.success_count == 1
    assert state.srs_interval == 1
    assert state.srs_due_at is not None


def test_the_interval_climbs_with_success_and_resets_on_failure(db):
    """Spaced repetition works because the interval reflects what you can currently do. A
    phrase you got wrong today is not 'nearly due in a week'."""
    intent = _intent(db)
    variant = _variant(db, intent, "How many hours have you been driving today?")
    account = _account(db)

    intervals = []
    for _ in range(3):
        intervals.append(
            coaching.record_practice(
                db, account_id=account.id, variant_id=variant.id, success=True
            ).srs_interval
        )
    assert intervals == [1, 3, 7]

    failed = coaching.record_practice(
        db, account_id=account.id, variant_id=variant.id, success=False
    )
    assert failed.srs_interval == 1
    assert failed.exposure_count == 4
    assert failed.success_count == 3


def test_a_guest_records_nothing_and_is_not_an_error(db):
    """`skill_state.account_id` is NOT NULL because skill belongs to a person rather than
    a browser session. Raising here would break the loop for the guest in front of it —
    FR1's claim flow is what turns their work into a record."""
    intent = _intent(db)
    variant = _variant(db, intent, "How many hours have you been driving today?")

    recorded = coaching.record_practice(
        db, account_id=None, variant_id=variant.id, success=True
    )
    assert recorded is None
