"""AI-CONTEXT: M8 Decision Intelligence (PRD §8.8) — the decisions a driver makes
ten times a week, computed from the platform's own data. A SCHEMA-LESS serving
layer (F11 precedent): it owns no tables, it composes the modules below it
through their public interfaces and takes the driver's inputs.

The three headline tools (DoD): the true-profit load calculator (M8-FR1), the
appointment-hour optimizer (M8-FR2), and the "where do I sleep tonight" solver
(M8-FR3). Plus a parking-fill forecast (M8-FR4) and a detention-risk
pre-acceptance flag (M8-FR6). Every output carries its BASIS — sample size or
"heuristic" — and nothing fabricates precision (M8-FR5 / design-prd §11.7).

Composes F3 (dwell distribution) + m01 (corridor/forecast) + m02 (dwell-by-hour)
+ m03 (detention valuation) + m06 (bookable inventory) + m07 (route fuel). Runs
behind the F13 flag m08_intelligence.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.foundation.f03_location import public as location
from app.modules.m01_map import public as m1
from app.modules.m02_facility_intel import public as m2
from app.modules.m03_detention import public as m3
from app.modules.m06_parking import public as m6
from app.modules.m07_fuel import public as m7

from .enums import Confidence, confidence_for

FLAG_KEY = "m08_intelligence"
MODULE = "m08"
MILE_M = 1609.34
_STATUS_RANK = {"empty": 0, "some": 1, None: 2, "full": 3}


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags
    from app.foundation.f14_admin import public as admin

    flags.register_flag(db, FLAG_KEY, description="M8 Decision Intelligence", default_on=True)
    admin.register_admin_view(db, "m08.intel", MODULE, "Decision Intelligence", "/admin/m08/intel")


# --- Expected accessorial time cost from the facility's dwell distribution ---
def expected_detention_cost(
    db: Session, facility_id, free_time_minutes: int, rate_cents_per_hour: int
) -> tuple[int, int]:
    # AI-CONTEXT: value each historical stop with the SAME M3 clock the live
    # meter uses, then average — the expected detention this receiver will cost.
    samples = location.dwell_samples(db, facility_id)
    if not samples:
        return 0, 0
    total = 0
    for s in samples:
        state = m3.compute_detention(
            s["enter_at"],
            free_time_minutes,
            rate_cents_per_hour,
            now=s["exit_at"],
            departed_at=s["exit_at"],
        )
        total += state.amount_cents
    return round(total / len(samples)), len(samples)


def route_fuel_cost(
    db: Session,
    account_id,
    lat: float,
    lon: float,
    heading_deg: float,
    range_m: float,
    miles: float,
    mpg: float,
) -> tuple[int, int | None, str]:
    gallons = miles / mpg if mpg else 0
    stops = m7.corridor_fuel(db, account_id, lat, lon, heading_deg, range_m, gallons=gallons)
    if not stops:
        return 0, None, "no_network_fuel"
    cheapest = stops[0]  # corridor_fuel is sorted by net price
    return cheapest.true_cost_cents, cheapest.net_cents_per_gal, f"m7:{cheapest.name}"


# --- M8-FR1: true-profit load calculator ---
@dataclass
class ProfitResult:
    revenue_cents: int
    fuel_cost_cents: int
    tolls_cents: int
    expected_detention_cents: int
    net_cents: int
    # rate-per-mile after this receiver's dwell history. NONE, not 0, when there are no
    # loaded miles to divide by (audit F-26): zero renders as a real rate of $0.00/mi,
    # which is absence dressed as a result — the §11.7 failure, and the same shape as
    # the merged-facility crowd report that told a driver their submission landed.
    # `basis["rpm"]` says which it is, because a caller must not have to infer it.
    rpm_after_cents: int | None
    fuel_net_cents_per_gal: int | None
    basis: dict = field(default_factory=dict)


def true_profit(
    db: Session,
    account_id,
    *,
    revenue_cents: int,
    loaded_miles: float,
    mpg: float,
    tolls_cents: int,
    receiver_facility_id,
    free_time_minutes: int,
    rate_cents_per_hour: int,
    origin_lat: float,
    origin_lon: float,
    heading_deg: float,
    max_distance_m: float,
) -> ProfitResult:
    fuel_cost, fuel_net, fuel_basis = route_fuel_cost(
        db, account_id, origin_lat, origin_lon, heading_deg, max_distance_m, loaded_miles, mpg
    )
    det_cost, det_n = expected_detention_cost(
        db, receiver_facility_id, free_time_minutes, rate_cents_per_hour
    )
    net = revenue_cents - fuel_cost - tolls_cents - det_cost
    rpm = round(net / loaded_miles) if loaded_miles else None
    return ProfitResult(
        revenue_cents=revenue_cents,
        fuel_cost_cents=fuel_cost,
        tolls_cents=tolls_cents,
        expected_detention_cents=det_cost,
        net_cents=net,
        rpm_after_cents=rpm,
        fuel_net_cents_per_gal=fuel_net,
        basis={
            "fuel": fuel_basis,
            "detention_sample_size": det_n,
            "detention_confidence": confidence_for(det_n).value,
            "rpm": "computed" if rpm is not None else "no_loaded_miles",
        },
    )


# --- M8-FR2: appointment-time optimizer ---
@dataclass
class HourRec:
    hour: int
    median_seconds: int
    sample_size: int
    confidence: str


def appointment_hours(db: Session, facility_id) -> list[HourRec]:
    dwell = m2.dwell_stats(db, facility_id)
    recs = [
        HourRec(
            hour=hour,
            median_seconds=int(stat["median_seconds"]),
            sample_size=stat["sample_size"],
            confidence=confidence_for(stat["sample_size"]).value,
        )
        for hour, stat in dwell.by_hour.items()
    ]
    recs.sort(key=lambda r: r.median_seconds)  # fastest-unloading hour first
    return recs


# --- M8-FR4: parking-fill forecast (heuristic bootstrap, basis always shown) ---
@dataclass
class ParkingForecast:
    status: str
    basis: str
    note: str


def predict_parking(db: Session, facility_id, hour_of_day: int) -> ParkingForecast:
    # AI-CONTEXT: wraps M1's heuristic today; the pipeline upgrades to a learned
    # model as M2/M3 data accrues (M8-FR4/FR5). The basis is never hidden.
    p = m1.predict_parking_fill(db, facility_id, hour_of_day)
    return ParkingForecast(status=p.status, basis=p.basis, note=p.note)


# --- M8-FR6: detention-risk pre-acceptance flag ---
@dataclass
class RiskFlag:
    exceed_rate: float | None  # fraction of tracked stops that ran past free time
    sample_size: int
    confidence: str
    basis: str


def detention_risk_flag(db: Session, facility_id, free_time_minutes: int) -> RiskFlag:
    samples = location.dwell_samples(db, facility_id)
    n = len(samples)
    if n == 0:
        return RiskFlag(None, 0, Confidence.heuristic.value, "no_data")
    free_seconds = (free_time_minutes or 0) * 60
    exceeded = sum(1 for s in samples if s["seconds"] > free_seconds)
    return RiskFlag(
        exceed_rate=exceeded / n,
        sample_size=n,
        confidence=confidence_for(n).value,
        basis="tracked_stops",
    )


# --- M8-FR3: "where do I sleep tonight" solver ---
@dataclass
class StopRec:
    facility_id: object
    name: str
    facility_type: str
    distance_m: float
    predicted_status: str | None
    predicted_basis: str | None
    guaranteed_bookable: bool


@dataclass
class SleepPlan:
    range_m: float
    stops: list[StopRec]
    guaranteed: object  # cheapest bookable spot within range (M6), or None
    fuel: object  # cheapest net fuel on the corridor (M7), or None
    basis: dict = field(default_factory=dict)


def where_to_sleep(
    db: Session,
    account_id,
    lat: float,
    lon: float,
    heading_deg: float,
    hos_minutes_remaining: int,
    avg_speed_mph: float = 55.0,
    arrival_hour: int | None = None,
) -> SleepPlan:
    range_m = (hos_minutes_remaining / 60.0) * avg_speed_mph * MILE_M
    corridor = m1.corridor_view(
        db, account_id, lat, lon, heading_deg, range_m, preset=m1.Preset.tonight
    )
    stops: list[StopRec] = []
    for e in corridor:
        forecast = (
            predict_parking(db, e.facility_id, arrival_hour) if arrival_hour is not None else None
        )
        stops.append(
            StopRec(
                facility_id=e.facility_id,
                name=e.name,
                facility_type=e.facility_type,
                distance_m=e.distance_m,
                predicted_status=forecast.status if forecast else None,
                predicted_basis=forecast.basis if forecast else None,
                guaranteed_bookable=e.facility_type == "parking_property",
            )
        )
    # guaranteed-bookable first, then best predicted availability, then nearest
    stops.sort(
        key=lambda s: (
            0 if s.guaranteed_bookable else 1,
            _STATUS_RANK.get(s.predicted_status, 2),
            s.distance_m,
        )
    )
    bookable = m6.bookable_near(db, lat, lon, range_m)
    guaranteed = min(bookable, key=lambda b: b.price_cents_per_night, default=None)
    fuel_stops = m7.corridor_fuel(db, account_id, lat, lon, heading_deg, range_m)
    fuel = fuel_stops[0] if fuel_stops else None
    return SleepPlan(
        range_m=range_m,
        stops=stops,
        guaranteed=guaranteed,
        fuel=fuel,
        basis={"hos_minutes_remaining": hos_minutes_remaining, "arrival_hour": arrival_hour},
    )
