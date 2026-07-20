"""AI-CONTEXT: M2 Facility Intelligence HTTP endpoints — thin over
m02_facility_intel.public. Publishes aggregated factual measurements (dwell
stats with sample sizes) + approved, moderated reviews (PRD §13 posture).
Semantic search uses the F9 provider seam (deterministic fake in dev until the
real model adapter is wired).
"""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f09_ai_gateway import public as ai
from app.modules.m02_facility_intel import public as m2

router = APIRouter(prefix="/facility", tags=["facility"])

# AI-CONTEXT: F9 provider seam — swap the deterministic fake for the real model
# adapter (latest Claude models via the claude-api skill) at activation.
_PROVIDER = ai.FakeModelProvider()


def _serialize_review(review) -> dict:
    return {
        "id": str(review.id),
        "ratings": review.ratings,
        "text": review.text,
        "created_at": review.created_at,
    }


@router.get("/{facility_id}/profile")
def profile(
    facility_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    prof = m2.get_or_create_profile(db, facility_id)
    dwell = m2.dwell_stats(db, facility_id)
    return {
        "facility_id": str(facility_id),
        "check_in_procedure": prof.check_in_procedure,
        "ppe_rules": prof.ppe_rules,
        "restrooms": prof.restrooms,
        "overnight_parking": prof.overnight_parking,
        "backing_type": prof.backing_type,
        "hazards": prof.hazards,
        "dwell": {"overall": dwell.overall, "by_hour": dwell.by_hour},
        "ratings": m2.aggregate_ratings(db, facility_id),
        "detention_risk": m2.detention_risk(db, facility_id),
        "reviews": [_serialize_review(r) for r in m2.list_reviews(db, facility_id)],
    }


class ReviewIn(BaseModel):
    ratings: dict
    text: str | None = None


@router.post("/{facility_id}/review", status_code=201)
def submit_review(
    facility_id: uuid.UUID,
    body: ReviewIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    review = m2.submit_review(db, facility_id, account.id, body.ratings, body.text)
    return {"review_id": str(review.id), "status": review.status.value}


@router.get("/search")
def search(
    q: str,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    return m2.search_reviews(db, _PROVIDER, q)
