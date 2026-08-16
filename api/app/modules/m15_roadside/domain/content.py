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
from .models import CoachingContent, PhraseVariant, SignItem


class ContentNotReviewed(ValueError):
    """A release was attempted without a human reviewer, or without a version bump."""


class HoldoutLeak(AssertionError):
    """A holdout variant reached a teaching surface. Raised by the generators' own guard."""


# --- Q-6: draft -> reviewed -> released ---------------------------------------------


def mark_reviewed(item: PhraseVariant | SignItem | CoachingContent, reviewer: str | None) -> None:
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


def release(item: PhraseVariant | SignItem | CoachingContent, *, previous_version: int) -> None:
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


def _assert_no_holdout(variants: list[PhraseVariant]) -> None:
    leaked = [v.id for v in variants if v.holdout]
    if leaked:
        raise HoldoutLeak(
            f"holdout variants reached a teaching surface: {leaked}. Q-5 — a driver who "
            "practised the item they are later tested on has been measured on memory."
        )
