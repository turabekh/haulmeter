"""AI-CONTEXT: M2 Facility Intelligence & Scorecard (PRD §8.2). The layer no
incumbent owns properly: objective dwell statistics + structured reviews, keyed
off the F2 facility. Composes foundation publics only (import-linter): F2
(facility), F3 (dwell samples), F9 (review embeddings), F10 (points), F14
(moderation + audit + admin). Publishes only aggregated factual measurements
(with sample sizes, never faked) plus clearly-attributed, moderated opinions —
the defamation posture (PRD §13). Runs behind the F13 flag m02_facility_intel.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility_registry
from app.foundation.f03_location import public as location
from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f10_crowd import public as crowd
from app.foundation.f14_admin import public as admin

from .enums import RATING_ASPECTS, ReviewStatus
from .models import FacilityProfile, FacilityReview

FLAG_KEY = "m02_facility_intel"
MODULE = "m02"
REVIEW_POINTS = 10  # points earned for an approved review (-> F13 config later)
FACTUAL_FIELDS = {
    "check_in_procedure",
    "ppe_rules",
    "restrooms",
    "overnight_parking",
    "backing_type",
    "hazards",
}


class FacilityNotFound(Exception):
    pass


class InvalidRatings(Exception):
    pass


class NotFactualField(Exception):
    pass


@dataclass
class ParsedDwell:
    overall: dict
    by_hour: dict


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags

    flags.register_flag(db, FLAG_KEY, description="M2 Facility Intelligence & Scorecard")
    admin.register_admin_view(
        db, "m02.scorecard", MODULE, "Facility Scorecard", "/admin/m02/scorecard"
    )


# --- Profile + self-service factual claim (M2-FR1, FR7) ---
def get_or_create_profile(db: Session, facility_id) -> FacilityProfile:
    if facility_registry.get_facility(db, facility_id) is None:
        raise FacilityNotFound(str(facility_id))
    profile = db.get(FacilityProfile, facility_id)
    if profile is None:
        profile = FacilityProfile(facility_id=facility_id, hazards={})
        db.add(profile)
        db.flush()
    return profile


def update_factual_attributes(
    db: Session, facility_id, updates: dict, actor_account_id=None
) -> FacilityProfile:
    unknown = set(updates) - FACTUAL_FIELDS
    if unknown:
        raise NotFactualField(f"not factual/editable: {sorted(unknown)}")
    profile = get_or_create_profile(db, facility_id)
    for key, value in updates.items():
        setattr(profile, key, value)
    db.flush()
    admin.record_action(
        db,
        "facility_attribute_claim",
        actor_account_id=actor_account_id,
        target_kind="facility",
        target_ref=facility_id,
        detail={"fields": sorted(updates)},
    )
    return profile


# --- Structured reviews (M2-FR1, FR4) ---
def _validate_ratings(ratings: dict) -> None:
    unknown = set(ratings) - set(RATING_ASPECTS)
    if unknown:
        raise InvalidRatings(f"unknown aspects: {sorted(unknown)}")
    for aspect, score in ratings.items():
        if not isinstance(score, int) or not (1 <= score <= 5):
            raise InvalidRatings(f"{aspect} must be an int 1-5")


def submit_review(
    db: Session, facility_id, account_id, ratings: dict, text: str | None = None
) -> FacilityReview:
    if facility_registry.get_facility(db, facility_id) is None:
        raise FacilityNotFound(str(facility_id))
    _validate_ratings(ratings)
    review = FacilityReview(
        facility_id=facility_id,
        account_id=account_id,
        ratings=ratings,
        text=text,
        status=ReviewStatus.pending,
    )
    db.add(review)
    db.flush()
    item = admin.enqueue_moderation(db, "review", review.id, submitted_by=account_id)
    review.moderation_ref = item.id
    db.flush()
    return review


def moderate_review(
    db: Session,
    review: FacilityReview,
    approve: bool,
    provider=None,
    moderator_account_id=None,
) -> FacilityReview:
    status = ReviewStatus.approved if approve else ReviewStatus.rejected
    review.status = status
    review.decided_at = datetime.now(UTC)
    if review.moderation_ref is not None:
        item = db.get(admin.ModerationItem, review.moderation_ref)
        if item is not None:
            admin.decide_moderation(
                db,
                item,
                admin.ModerationStatus.approved if approve else admin.ModerationStatus.rejected,
                moderator_account_id=moderator_account_id,
            )
    if approve:
        crowd.issue_points(db, review.account_id, REVIEW_POINTS)
        if provider is not None and review.text:
            ai.embed_and_store(
                db, provider, MODULE, "facility_review", review.facility_id, review.text
            )
    db.flush()
    return review


def list_reviews(db: Session, facility_id, only_approved: bool = True) -> list[FacilityReview]:
    stmt = select(FacilityReview).where(FacilityReview.facility_id == facility_id)
    if only_approved:
        stmt = stmt.where(FacilityReview.status == ReviewStatus.approved)
    return list(db.scalars(stmt.order_by(FacilityReview.created_at.desc())))


def aggregate_ratings(db: Session, facility_id) -> dict:
    reviews = list_reviews(db, facility_id, only_approved=True)
    totals: dict[str, list[int]] = {}
    for review in reviews:
        for aspect, score in (review.ratings or {}).items():
            totals.setdefault(aspect, []).append(score)
    per_aspect = {a: round(sum(v) / len(v), 2) for a, v in totals.items()}
    all_scores = [s for v in totals.values() for s in v]
    return {
        "per_aspect": per_aspect,
        "overall": round(sum(all_scores) / len(all_scores), 2) if all_scores else None,
        "review_count": len(reviews),
    }


# --- Objective dwell statistics (M2-FR2) ---
def _percentile(values: list[float], p: float):
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def dwell_stats(db: Session, facility_id) -> ParsedDwell:
    samples = location.dwell_samples(db, facility_id)
    overall = [s["seconds"] for s in samples]
    by_hour_secs: dict[int, list[float]] = {}
    for s in samples:
        by_hour_secs.setdefault(s["arrival_hour"], []).append(s["seconds"])
    return ParsedDwell(
        overall={
            "median_seconds": _percentile(overall, 0.5),
            "p90_seconds": _percentile(overall, 0.9),
            "sample_size": len(overall),  # always shown (§11.7 / PRD M2-FR2)
        },
        by_hour={
            hour: {"median_seconds": _percentile(v, 0.5), "sample_size": len(v)}
            for hour, v in sorted(by_hour_secs.items())
        },
    )


# --- Detention-risk indicator (M2-FR3) — seam until M3 ---
def detention_risk(db: Session, facility_id) -> dict:
    return {"rate": None, "sample_size": 0, "basis": "m3_pending"}


# --- Semantic review search (M2-FR6) ---
def search_reviews(db: Session, provider, query: str, limit: int = 5) -> list[dict]:
    hits = ai.search_similar(db, provider, MODULE, "facility_review", query, limit=limit)
    return [{"facility_id": str(emb.owner_ref), "distance": dist} for emb, dist in hits]
