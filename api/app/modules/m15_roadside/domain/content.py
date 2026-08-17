"""AI-CONTEXT: the content pipeline and the scenario generators (E3 §E3.1.10 Q-5, Q-6).

TWO QUALITY LAWS LIVE HERE, and both are enforced at the only place that can hold them.

**Q-6 — content ships reviewed or not at all.** `released` requires a human reviewer and a
version bump; F9-drafted text has no path to a driver. The enforcement is `release()`
refusing rather than a caller remembering, because "the publish endpoint checks it" is a
claim about every future caller and this is a claim about the transition.

**Q-5 — holdout integrity.** A `holdout=true` variant never appears in a drill or in
coaching, and reassessment draws holdout-first. This is enforced in the GENERATORS rather
than by a filter callers apply, for the same reason: a filter a caller must remember is a
filter that will be forgotten, and forgetting it silently destroys the only measurement
that makes "improved" mean anything. If a driver has practised the item they are later
tested on, the reassessment measures memory of that item and nothing about their English.

WHY THE TWO BELONG IN ONE FILE: they are the same rule pointed at different audiences.
Q-6 keeps unreviewed content away from a driver; Q-5 keeps taught content out of the
measurement. Both are about material reaching somewhere it invalidates something.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .enums import ContentStatus
from .models import (
    CoachingContent,
    Intent,
    ModelAnswer,
    OfficerAck,
    PhraseVariant,
    ScenarioVersion,
    SignItem,
)


class ContentNotReviewed(ValueError):
    """A release was attempted without a human reviewer, or without a version bump."""


class HoldoutLeak(AssertionError):
    """A holdout variant reached a teaching surface. Raised by the generators' own guard."""


# --- Q-6: draft -> reviewed -> released ---------------------------------------------


# every kind of content this module publishes; the transitions below are the same for all
Publishable = (
    PhraseVariant | SignItem | CoachingContent | ScenarioVersion | ModelAnswer | OfficerAck
)


def mark_reviewed(item: Publishable, reviewer: str | None) -> None:
    """A human says they read it. `reviewer` is required and is the whole point.

    AI-CONTEXT: F9 may DRAFT content — that is what the classify/draft prompts are for —
    but a machine cannot occupy this step. An empty reviewer is how "reviewed" quietly
    becomes "generated", which is the audit's named anti-pattern about machine translation
    shipped unreviewed, in a different costume.
    """
    if not reviewer or not reviewer.strip():
        raise ContentNotReviewed(
            "review requires a named human reviewer; a blank reviewer is how 'reviewed' "
            "silently becomes 'generated' (Q-6)"
        )
    _set_status(item, ContentStatus.reviewed)


def release(item: Publishable, *, previous_version: int) -> None:
    """Promote reviewed -> released. Refuses from draft, and refuses without a bump.

    The version bump is not bookkeeping: released content is what a driver is scored
    against, so "which text did they hear" must be answerable later. Releasing without a
    bump makes two different texts share one version and the question unanswerable.
    """
    if _status(item) is not ContentStatus.reviewed:
        raise ContentNotReviewed(
            f"content must be reviewed before release; this is {_status(item).value}. "
            "F9-drafted text has no path to a driver (Q-6)."
        )
    if item.version <= previous_version:
        raise ContentNotReviewed(
            f"release requires a version bump (have {item.version}, previous "
            f"{previous_version}); released content is what a driver was scored against "
            "and must stay identifiable"
        )
    _set_status(item, ContentStatus.released)


# AI-CONTEXT: `ScenarioVersion` joined the union when the publish surface was built. It
# always carried `status` and `version` and was always content by any reading — it simply
# had no operator path, so nothing had ever asked it to move. The transition rules are the
# ones above, unchanged: a scenario cannot be released from draft either, and it needs the
# same version bump for the same reason (which definition was a driver scored against).
def _status(item) -> ContentStatus:
    return item.review_status if isinstance(item, CoachingContent) else item.status


def _set_status(item, status: ContentStatus) -> None:
    if isinstance(item, CoachingContent):
        item.review_status = status
    else:
        item.status = status


# --- Q-5: holdout integrity ----------------------------------------------------------


def teachable_variants(db: Session, intent_id) -> list[PhraseVariant]:
    """Variants a drill or a coaching surface may use. Holdouts are excluded HERE.

    AI-CONTEXT: released-only AND holdout-free, in the generator rather than at the call
    site. Both halves matter and they fail differently: an unreleased variant reaching a
    driver is Q-6, a holdout variant reaching them is Q-5, and the second is worse because
    it leaves no trace — the drill looks normal and the later reassessment silently stops
    measuring anything.
    """
    variants = list(
        db.scalars(
            select(PhraseVariant).where(
                PhraseVariant.intent_id == intent_id,
                PhraseVariant.holdout.is_(False),
                PhraseVariant.status == ContentStatus.released,
            )
        )
    )
    _assert_no_holdout(variants)
    return variants


def reassessment_variants(db: Session, intent_id) -> list[PhraseVariant]:
    """Holdout-first, because reassessment on a practised item measures memory.

    Holdouts come first and unseen material is preferred; released non-holdouts follow
    only so a reassessment is still possible for an intent whose holdouts are exhausted.
    """
    holdouts = list(
        db.scalars(
            select(PhraseVariant).where(
                PhraseVariant.intent_id == intent_id,
                PhraseVariant.holdout.is_(True),
                PhraseVariant.status == ContentStatus.released,
            )
        )
    )
    return holdouts + teachable_variants(db, intent_id)


# --- what a driver may be offered ----------------------------------------------------


def startable_scenarios(db: Session) -> list[ScenarioVersion]:
    """Released scenarios that can actually produce a turn.

    AI-CONTEXT: TWO conditions, and the second is the one worth having. A scenario may be
    released while the intents it names have no released variants — the scenario and its
    phrasing are separate content moving through the pipeline separately — and offering one
    of those to a driver produces a session that opens and immediately closes on
    `NoContentAvailable`. The driver's reading of that is "this feature is broken", which
    is a fair reading.

    So "startable" means EVERY allowed intent can be spoken, checked through
    `teachable_variants` rather than by a query written here: that function is where Q-5
    and Q-6 are enforced together, and a second implementation of the same filter is a
    second place for them to drift apart.

    An empty list is a legitimate answer and the surfaces are built for it. It is the
    honest state of a module whose content has not been reviewed yet, and it is what the
    driver sees rather than draft text.
    """
    released = list(
        db.scalars(
            select(ScenarioVersion)
            .where(ScenarioVersion.status == ContentStatus.released)
            .order_by(ScenarioVersion.version)
        )
    )
    return [s for s in released if _every_intent_can_speak(db, s)]


def _every_intent_can_speak(db: Session, scenario: ScenarioVersion) -> bool:
    keys = list(scenario.allowed_intents or [])
    if not keys:
        return False
    intents = list(db.scalars(select(Intent).where(Intent.key.in_(keys))))
    if len(intents) != len(set(keys)):
        return False
    return all(teachable_variants(db, intent.id) for intent in intents)


def _assert_no_holdout(variants: list[PhraseVariant]) -> None:
    leaked = [v.id for v in variants if v.holdout]
    if leaked:
        raise HoldoutLeak(
            f"holdout variants reached a teaching surface: {leaked}. Q-5 — a driver who "
            "practised the item they are later tested on has been measured on memory."
        )
