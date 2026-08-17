"""AI-CONTEXT: the daily drill (M15-FR6), and the four properties that make it a plan.

`drill_plan` existed as a table and was written by nothing, like `skill_state` before it.

  · a day is DUE items plus a little new, capped — a driver who misses four days does not
    come back to a punishment
  · items INTERLEAVE across intents, which is the difference between learning the answer
    and learning the question
  · Q-5 holds on a drill exactly as in a session: a holdout is never practised
  · the plan is idempotent per day, so it cannot reshuffle under a driver mid-drill
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.modules.m15_roadside.domain import coaching, drills
from app.modules.m15_roadside.domain import models as m


def _account(db):
    return identity.register_account(db, f"drill-{uuid.uuid4().hex[:8]}@example.com", "pw-123456")


def _intent(db, key):
    intent = m.Intent(key=key, domain="stop", canonical_meaning=key)
    db.add(intent)
    db.flush()
    return intent


def _variant(db, intent, text, *, holdout=False, version=1, status=m.ContentStatus.released):
    variant = m.PhraseVariant(
        intent_id=intent.id, text=text, difficulty=m.Difficulty.clear,
        status=status, holdout=holdout, version=version,
    )
    db.add(variant)
    db.flush()
    return variant


def test_a_day_is_built_from_what_is_due_plus_a_little_new(db):
    account = _account(db)
    intent = _intent(db, "hos")
    practised = _variant(db, intent, "practised phrasing")
    _variant(db, intent, "never seen", version=2)
    coaching.record_practice(db, account_id=account.id, variant_id=practised.id, success=False)
    # make it due
    state = drills.due_items(db, account.id, now=datetime.now(UTC) + timedelta(days=2))
    assert [s.variant_id for s in state] == [practised.id]

    plan = drills.todays_drill(db, account.id, now=datetime.now(UTC) + timedelta(days=2))

    ids = plan.items["variant_ids"]
    assert str(practised.id) in ids
    assert len(ids) == 2, "the due item and one unseen phrasing"


def test_overdue_is_simply_due(db):
    """A driver who misses four days comes back to one queue, not four days of backlog.
    The alternative punishes exactly the driver the product is trying to keep."""
    account = _account(db)
    intent = _intent(db, "hos")
    variant = _variant(db, intent, "a phrasing")
    coaching.record_practice(db, account_id=account.id, variant_id=variant.id, success=False)

    assert len(drills.due_items(db, account.id, now=datetime.now(UTC) + timedelta(days=40))) == 1


def test_a_holdout_is_never_drilled(db):
    """Q-5 on a teaching surface. A drill IS one."""
    account = _account(db)
    intent = _intent(db, "hos")
    _variant(db, intent, "held out", holdout=True)

    assert drills.unseen_variants(db, account.id) == []


def test_a_draft_phrasing_is_never_drilled(db):
    """Q-6 — the drill draws through `teachable_variants` rather than its own query."""
    account = _account(db)
    intent = _intent(db, "hos")
    _variant(db, intent, "still drafting", status=m.ContentStatus.draft)

    assert drills.unseen_variants(db, account.id) == []


def test_items_interleave_across_intents(db):
    """THE ONE WORTH HAVING. Six phrasings of one question in a row teaches the answer to
    that question; alternating teaches which question is being asked."""
    account = _account(db)
    a, b = _intent(db, "hos"), _intent(db, "destination")
    for i in range(3):
        _variant(db, a, f"hos phrasing {i}", version=i + 1)
        _variant(db, b, f"destination phrasing {i}", version=i + 1)

    plan = drills.todays_drill(db, account.id)
    ids = [uuid.UUID(v) for v in plan.items["variant_ids"]]
    intents = [db.get(m.PhraseVariant, v).intent_id for v in ids]

    assert len(intents) >= 2
    assert intents[0] != intents[1], "two questions of the same intent back to back"


def test_the_plan_is_the_same_plan_all_day(db):
    """A plan regenerated on every open reshuffles under a driver mid-drill and loses
    their place."""
    account = _account(db)
    intent = _intent(db, "hos")
    _variant(db, intent, "a phrasing")

    first = drills.todays_drill(db, account.id)
    second = drills.todays_drill(db, account.id)

    assert first.id == second.id


def test_completing_is_idempotent(db):
    account = _account(db)
    intent = _intent(db, "hos")
    _variant(db, intent, "a phrasing")
    plan = drills.todays_drill(db, account.id)

    drills.complete_drill(db, plan)
    stamped = plan.completed_at
    drills.complete_drill(db, plan)

    assert plan.completed_at == stamped


def test_a_guest_has_no_plan(db):
    """`drill_plan.account_id` is NOT NULL — a 30-day plan belongs to a person. Returning
    None rather than raising keeps the surface honest instead of broken."""
    assert drills.todays_drill(db, None) is None


def test_nothing_to_drill_is_no_plan_rather_than_an_empty_one(db):
    """An empty plan row would make "day 3 of 30" count days a driver never practised."""
    account = _account(db)

    assert drills.todays_drill(db, account.id) is None
