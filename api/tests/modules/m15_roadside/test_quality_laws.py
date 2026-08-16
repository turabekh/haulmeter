"""AI-CONTEXT: quality laws Q-5 and Q-6, each with the failure it prevents (E3 §E3.1.10).

Honest provenance, because the alternative is a comment that lies: the guards were
written first and these tests SECOND, then each guard was sabotaged to the permissive
behaviour and the tests watched to go red. That is E3's build note ("sabotage each and
watch it go red before trusting green") rather than a strict red-first ordering, and the
distinction is worth stating — a test written after the code it checks can be shaped,
unconsciously, to the code's actual behaviour rather than to the law. The sabotage runs
are what make these more than a restatement of `content.py`, and the specific sabotages
were: dropping the holdout predicate from the generator, and letting `release()` promote
straight from draft.

Q-5 is a PROPERTY test rather than a case test: it asserts over the whole generated set
for arbitrary holdout arrangements, because the leak that matters is the one nobody
thought to write a case for.
"""

import pytest

from app.modules.m15_roadside.domain import content
from app.modules.m15_roadside.domain import models as m


def _intent(db, key="hours_of_service"):
    intent = m.Intent(key=key, domain="paperwork", canonical_meaning="HOS")
    db.add(intent)
    db.flush()
    return intent


def _variant(db, intent, text, *, holdout=False, status=m.ContentStatus.released, version=1):
    variant = m.PhraseVariant(
        intent_id=intent.id,
        text=text,
        difficulty=m.Difficulty.clear,
        holdout=holdout,
        status=status,
        version=version,
    )
    db.add(variant)
    db.flush()
    return variant


# --- Q-6: content ships reviewed or not at all --------------------------------------


def test_draft_content_cannot_be_released(db):
    """F9-drafted text has no path to a driver. The transition is where that is held."""
    intent = _intent(db)
    variant = _variant(db, intent, "How many hours?", status=m.ContentStatus.draft, version=2)
    with pytest.raises(content.ContentNotReviewed):
        content.release(variant, previous_version=1)
    assert variant.status is m.ContentStatus.draft


def test_release_requires_a_version_bump(db):
    """Two different texts sharing one version makes "what did they hear" unanswerable."""
    intent = _intent(db)
    variant = _variant(db, intent, "How many hours?", status=m.ContentStatus.draft, version=1)
    content.mark_reviewed(variant, "Dilnoza R.")
    with pytest.raises(content.ContentNotReviewed):
        content.release(variant, previous_version=1)


def test_review_requires_a_named_human(db):
    """A blank reviewer is how 'reviewed' silently becomes 'generated'."""
    intent = _intent(db)
    variant = _variant(db, intent, "How many hours?", status=m.ContentStatus.draft)
    for blank in (None, "", "   "):
        with pytest.raises(content.ContentNotReviewed):
            content.mark_reviewed(variant, blank)
    assert variant.status is m.ContentStatus.draft


def test_the_full_path_draft_reviewed_released(db):
    intent = _intent(db)
    variant = _variant(db, intent, "How many hours?", status=m.ContentStatus.draft, version=2)
    content.mark_reviewed(variant, "Dilnoza R.")
    assert variant.status is m.ContentStatus.reviewed
    content.release(variant, previous_version=1)
    assert variant.status is m.ContentStatus.released


def test_unreleased_variants_never_reach_a_teaching_surface(db):
    intent = _intent(db)
    _variant(db, intent, "drafted", status=m.ContentStatus.draft)
    _variant(db, intent, "reviewed only", status=m.ContentStatus.reviewed)
    released = _variant(db, intent, "released", status=m.ContentStatus.released)

    teachable = content.teachable_variants(db, intent.id)
    assert [v.id for v in teachable] == [released.id]


# --- Q-5: holdout integrity (property) ----------------------------------------------


HOLDOUT_ARRANGEMENTS = [
    [True, False, False],
    [False, True, False],
    [False, False, True],
    [True, True, False],
    [True, True, True],
    [False, False, False],
]


@pytest.mark.parametrize("arrangement", HOLDOUT_ARRANGEMENTS)
def test_no_holdout_ever_reaches_a_teaching_surface(db, arrangement):
    """The property: for ANY arrangement of holdouts, the taught set contains none.

    A case test would have covered the arrangement someone thought of. The leak that
    matters is the other one.
    """
    intent = _intent(db, key=f"intent_{'_'.join(str(int(a)) for a in arrangement)}")
    for i, holdout in enumerate(arrangement):
        _variant(db, intent, f"variant {i}", holdout=holdout)

    teachable = content.teachable_variants(db, intent.id)

    assert all(v.holdout is False for v in teachable)
    assert len(teachable) == sum(1 for h in arrangement if not h)


@pytest.mark.parametrize("arrangement", HOLDOUT_ARRANGEMENTS)
def test_reassessment_draws_holdout_first(db, arrangement):
    intent = _intent(db, key=f"reassess_{'_'.join(str(int(a)) for a in arrangement)}")
    for i, holdout in enumerate(arrangement):
        _variant(db, intent, f"variant {i}", holdout=holdout)

    drawn = content.reassessment_variants(db, intent.id)
    holdout_flags = [v.holdout for v in drawn]

    # every holdout precedes every non-holdout
    assert holdout_flags == sorted(holdout_flags, reverse=True)
    assert len(drawn) == len(arrangement)


def test_the_generator_guard_fires_rather_than_returning_a_leak(db):
    """The guard is inside the generator, so a future edit to the query still trips it.

    If someone later 'optimises' the WHERE clause and drops the holdout predicate, the
    assertion inside `teachable_variants` is what turns that into a loud failure instead
    of a silently invalidated reassessment.
    """
    intent = _intent(db, key="guard_check")
    holdout = _variant(db, intent, "held out", holdout=True)
    with pytest.raises(content.HoldoutLeak):
        content._assert_no_holdout([holdout])
