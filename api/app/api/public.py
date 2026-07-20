"""AI-CONTEXT: Public Scorecard endpoints — the ONLY unauthenticated surface
(no session, no `current_account`). The public face of the M2 facility data: a
searchable directory + an aggregate scorecard (objective dwell + driver rating).
Aggregate-only, minimum-sample suppressed — NEVER identifiable driver data (§13
privacy). Backs the web-first Public Scorecard portal (design-prd §18).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.foundation.f02_facility import public as facility
from app.modules.m02_facility_intel import public as m2

router = APIRouter(prefix="/public", tags=["public"])

# never publish an objective dwell figure below this — small samples could
# expose or mislead (§11.7 no fake precision; §13 aggregate-only)
PUBLIC_MIN_SAMPLE = 3


@router.get("/facilities")
def facilities(
    q: str = "",
    limit: int = 20,
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(facility.Facility).where(
        facility.Facility.status != facility.FacilityStatus.merged
    )
    if q:
        stmt = stmt.where(facility.Facility.name.ilike(f"%{q}%"))
    stmt = stmt.order_by(facility.Facility.name).limit(min(max(limit, 1), 50))
    return [
        {"id": str(f.id), "name": f.name, "facility_type": f.facility_type.value}
        for f in db.scalars(stmt)
    ]


@router.get("/facility/{facility_id}")
def scorecard(
    facility_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:
    fac = facility.get_facility(db, facility_id)
    if fac is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "facility not found")
    overall = m2.dwell_stats(db, facility_id).overall
    ratings = m2.aggregate_ratings(db, facility_id)
    # suppress dwell below the public minimum sample (never a small-n figure)
    dwell = None
    if overall["sample_size"] >= PUBLIC_MIN_SAMPLE:
        dwell = {
            "median_seconds": int(overall["median_seconds"]),
            "p90_seconds": int(overall["p90_seconds"]),
            "sample_size": overall["sample_size"],
        }
    return {
        "id": str(fac.id),
        "name": fac.name,
        "facility_type": fac.facility_type.value,
        "dwell": dwell,
        "rating": {"overall": ratings["overall"], "review_count": ratings["review_count"]},
    }
