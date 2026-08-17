"""AI-CONTEXT: the 30-day drill plan (M15-FR6) — the half that needs no notification.

**THIS REVISES SESSION D'S OWN KICKOFF, which excluded FR6 on the grounds that "a daily
habit has no mechanism until P-1 is signed".** That reasoning was half right. The reminder
is what makes a drill a HABIT, and P-1 `readiness_reminder` is still an unsigned owner fork
(entry 177) — nothing here sends anything. But FR6's own validation is *"a driver completes
a day's drill in airplane mode and the results replay idempotently"*, which says nothing
about being reminded. A driver who opens the app has a drill waiting; a driver who does not
open it is the part that waits for P-1.

WHAT A DAY IS MADE OF (E3 §E3.1.2 FR6): everything due from spaced repetition, plus one or
two variants they have never met, **interleaved across intents**. The interleaving is not
presentation — practising six phrasings of one question in a row teaches the answer to that
question; alternating teaches the driver to recognise which question they are being asked,
which is the thing a roadside stop actually tests.

DUE MEANS DUE, INCLUDING OVERDUE. A driver who misses four days does not come back to four
days of backlog — `srs_due_at <= now` is one queue, and the day is capped. The alternative
punishes exactly the driver the product is trying to keep.

NOTHING HERE IS METERED. Drill audio is cached content (`audio.py`), so practice costs the
platform nothing per repetition and E3's "drills are never metered" holds by construction
rather than by a rule someone has to remember.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .content import teachable_variants
from .models import DrillPlan, Intent, PhraseVariant, SkillState

# E3: "daily 5–8 minute drill". At roughly 20–30 seconds per item — hear it, answer it,
# hear yourself — that is a dozen items at the outside, and fewer when they are hard.
DAY_ITEM_CAP = 12
# "due items plus 1–2 new variants"
NEW_PER_DAY = 2


def due_items(db: DbSession, account_id, *, now: datetime | None = None) -> list[SkillState]:
    """Everything the driver owes, oldest first. Overdue is due."""
    now = now or datetime.now(UTC)
    return list(
        db.scalars(
            select(SkillState)
            .where(
                SkillState.account_id == account_id,
                SkillState.srs_due_at.isnot(None),
                SkillState.srs_due_at <= now,
            )
            .order_by(SkillState.srs_due_at)
        )
    )


def unseen_variants(db: DbSession, account_id, *, limit: int = NEW_PER_DAY) -> list[PhraseVariant]:
    """Released phrasings this driver has never practised.

    Through `teachable_variants` per intent, so Q-5 and Q-6 hold here exactly as they do in
    a session — a drill is a teaching surface and a holdout must never appear on one.
    """
    seen = set(
        db.scalars(select(SkillState.variant_id).where(SkillState.account_id == account_id))
    )
    # AI-CONTEXT: ROUND-ROBIN, not first-intent-first. Taking the first `limit` in intent
    # order handed back two phrasings of the SAME question, which then made interleaving
    # impossible downstream — a driver's "something new today" was two ways of asking one
    # thing. Caught by the interleave test rather than by reading this function.
    buckets = []
    for intent in db.scalars(select(Intent)):
        unseen = [v for v in teachable_variants(db, intent.id) if v.id not in seen]
        if unseen:
            buckets.append(unseen)

    fresh: list[PhraseVariant] = []
    while buckets and len(fresh) < limit:
        for bucket in list(buckets):
            if not bucket:
                buckets.remove(bucket)
                continue
            fresh.append(bucket.pop(0))
            if len(fresh) >= limit:
                break
    return fresh


def _interleave(db: DbSession, variant_ids: list) -> list:
    """Round-robin across intents, so consecutive items are different questions.

    AI-CONTEXT: the whole point of FR6's "interleaved across intents". Six phrasings of one
    question in a row teaches the ANSWER to that question; alternating teaches the driver
    to tell which question they are being asked, which is what a roadside stop tests.
    """
    by_intent: dict = {}
    for variant_id in variant_ids:
        variant = db.get(PhraseVariant, variant_id)
        if variant is None:
            continue
        by_intent.setdefault(variant.intent_id, []).append(variant_id)

    out: list = []
    while any(by_intent.values()):
        for bucket in by_intent.values():
            if bucket:
                out.append(bucket.pop(0))
    return out


def todays_drill(db: DbSession, account_id, *, now: datetime | None = None) -> DrillPlan | None:
    """The day's plan, created once and returned thereafter. None for a guest.

    AI-CONTEXT: IDEMPOTENT PER DAY, and that matters more than it looks. A plan regenerated
    on every open would reshuffle mid-drill and let a driver lose their place, and the
    `completed_at` stamp would have nothing stable to attach to. `plan_day` is the day
    number since the driver's first plan, which is what makes "day 12 of 30" answerable.
    """
    if account_id is None:
        return None

    now = now or datetime.now(UTC)
    existing = list(
        db.scalars(
            select(DrillPlan)
            .where(DrillPlan.account_id == account_id)
            .order_by(DrillPlan.plan_day.desc())
        )
    )
    if existing and existing[0].completed_at is None:
        return existing[0]
    if existing and existing[0].items.get("date") == now.date().isoformat():
        return existing[0]

    due = [s.variant_id for s in due_items(db, account_id, now=now)]
    new = [v.id for v in unseen_variants(db, account_id)]
    ordered = _interleave(db, due + new)[:DAY_ITEM_CAP]
    if not ordered:
        return None

    plan = DrillPlan(
        account_id=account_id,
        plan_day=(existing[0].plan_day + 1) if existing else 1,
        items={"date": now.date().isoformat(), "variant_ids": [str(v) for v in ordered]},
    )
    db.add(plan)
    db.flush()
    return plan


def complete_drill(db: DbSession, plan: DrillPlan, *, now: datetime | None = None) -> DrillPlan:
    """Stamp the day done. Idempotent — a second tap does not move the date."""
    if plan.completed_at is None:
        plan.completed_at = now or datetime.now(UTC)
        db.flush()
    return plan
