"""AI-CONTEXT: M8 Decision Intelligence HTTP endpoints — thin over
m08_intelligence.public. The true-profit calculator, appointment-hour optimizer,
"where do I sleep tonight" solver, and detention-risk flag. Every response
carries its basis (sample size / heuristic) so the UI never fakes precision.
"""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import canonical_facility_id, current_account, get_db, require_module
from app.foundation.f01_identity import public as identity
from app.foundation.f13_flags import public as flags
from app.modules.m08_intelligence import public as m8

router = APIRouter(prefix="/intel", tags=["intelligence"],
    # PRD §6: the module's own flag, gating every route in it (§23 entry 105)
    dependencies=[Depends(require_module("m08_intelligence"))],
)


class TrueProfitIn(BaseModel):
    revenue_cents: int
    loaded_miles: float
    # AI-CONTEXT: NULL means "use whatever this driver reported", and the default that
    # used to sit here (6.0) is gone from the wire (§23 entry 154). A default on the
    # request model made the hardcode invisible: every client that omitted the field got
    # a fuel economy nobody had chosen, and no part of the response admitted it.
    mpg: float | None = None
    tolls_cents: int = 0
    receiver_facility_id: uuid.UUID
    free_time_minutes: int
    rate_cents_per_hour: int
    origin_lat: float
    origin_lon: float
    heading_deg: float = 0
    max_distance_m: float = 40000


@router.post("/true-profit")
def true_profit(
    body: TrueProfitIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # AI-CONTEXT: the driver's own fuel economy, and the request may still name one —
    # a driver checking "what if I ran this in the day cab" is asking a real question.
    # What it may no longer do is arrive silently: whichever of the three this is, the
    # response says so (§23 entry 154).
    profile = db.get(identity.DriverProfile, account.id)
    reported = profile.mpg if profile is not None else None
    if body.mpg is not None:
        mpg_value, mpg_basis = float(body.mpg), "request"
    elif reported is not None:
        mpg_value, mpg_basis = float(reported), "driver"
    else:
        mpg_value, mpg_basis = float(identity.DEFAULT_MPG), "default"
    r = m8.true_profit(
        db,
        account.id,
        revenue_cents=body.revenue_cents,
        loaded_miles=body.loaded_miles,
        mpg=mpg_value,
        mpg_basis=mpg_basis,
        tolls_cents=body.tolls_cents,
        receiver_facility_id=canonical_facility_id(body.receiver_facility_id, db),
        free_time_minutes=body.free_time_minutes,
        rate_cents_per_hour=body.rate_cents_per_hour,
        origin_lat=body.origin_lat,
        origin_lon=body.origin_lon,
        heading_deg=body.heading_deg,
        max_distance_m=body.max_distance_m,
    )
    return {
        "revenue_cents": r.revenue_cents,
        "fuel_cost_cents": r.fuel_cost_cents,
        "tolls_cents": r.tolls_cents,
        "expected_detention_cents": r.expected_detention_cents,
        "net_cents": r.net_cents,
        "rpm_after_cents": r.rpm_after_cents,
        "fuel_net_cents_per_gal": r.fuel_net_cents_per_gal,
        "basis": r.basis,
    }


@router.get("/appointment-hours/{facility_id}")
def appointment_hours(
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {
            "hour": r.hour,
            "median_seconds": r.median_seconds,
            "sample_size": r.sample_size,
            "confidence": r.confidence,
        }
        for r in m8.appointment_hours(db, facility_id)
    ]


@router.get("/detention-risk/{facility_id}")
def detention_risk(
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    free_time_minutes: int = 120,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    f = m8.detention_risk_flag(db, facility_id, free_time_minutes)
    return {
        "exceed_rate": f.exceed_rate,
        "exceeded": f.exceeded,
        "sample_size": f.sample_size,
        "confidence": f.confidence,
        "basis": f.basis,
    }


@router.get("/pre-acceptance/{facility_id}")
def pre_acceptance(
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    free_time_minutes: int = 120,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """AI-CONTEXT: the two reads a driver needs at the moment they DECIDE (J1-A3).

    One round trip, because this renders inside a confirm step the driver is already
    waiting on, and the sample floor is applied HERE rather than in each client — there
    are two clients now, and a floor enforced twice is a floor that will one day be
    enforced once.

    Behind `j1_preaccept_intel`, and OFF returns the same shape with both halves absent.
    The screen cannot tell a switched-off capability from a dock with no history, and
    that is correct: in both cases we have nothing to tell the driver, and inventing a
    distinction would put a "this feature is off" message where a driver expects facts
    about a dock.
    """
    if not flags.is_enabled(db, m8.PREACCEPT_FLAG):
        return {"risk": None, "best_hour": None, "min_sample": m8.MIN_SAMPLE}
    return m8.pre_acceptance(db, facility_id, free_time_minutes)


@router.get("/sleep")
def where_to_sleep(
    lat: float,
    lon: float,
    hos_minutes_remaining: int,
    heading_deg: float = 0,
    avg_speed_mph: float = 55,
    arrival_hour: int | None = None,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    plan = m8.where_to_sleep(
        db,
        account.id,
        lat,
        lon,
        heading_deg,
        hos_minutes_remaining,
        avg_speed_mph=avg_speed_mph,
        arrival_hour=arrival_hour,
    )
    return {
        "range_m": plan.range_m,
        "stops": [
            {
                "facility_id": str(s.facility_id),
                "name": s.name,
                "facility_type": s.facility_type,
                "distance_m": s.distance_m,
                "predicted_status": s.predicted_status,
                "predicted_basis": s.predicted_basis,
                "guaranteed_bookable": s.guaranteed_bookable,
            }
            for s in plan.stops
        ],
        "guaranteed": (
            {
                "spot_id": str(plan.guaranteed.spot_id),
                "property_name": plan.guaranteed.property_name,
                "price_cents_per_night": plan.guaranteed.price_cents_per_night,
            }
            if plan.guaranteed
            else None
        ),
        "fuel": (
            {
                "facility_id": str(plan.fuel.facility_id),
                "name": plan.fuel.name,
                "net_cents_per_gal": plan.fuel.net_cents_per_gal,
            }
            if plan.fuel
            else None
        ),
        "basis": plan.basis,
    }
