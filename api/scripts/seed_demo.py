"""AI-CONTEXT: DEV-ONLY demo seed. Populates a coherent cluster of facilities
around downtown Dallas (a US location) so the signed-in browser experience is
rich: truck stops with live parking status, a bookable parking lot, receivers
with dock-time, fuel stations with net pricing, and a couple of approved reviews
for the public scorecard. Idempotent-ish: skips if the marker facility exists.
Run: docker compose -f infra/docker-compose.yml exec api python scripts/seed_demo.py
"""

from datetime import UTC, datetime, timedelta

from app.core.db import SessionLocal
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f10_crowd import public as crowd
from app.modules.m02_facility_intel import public as m2
from app.modules.m06_parking import public as m6
from app.modules.m07_fuel import public as m7

CENTER = (32.7767, -96.7970)  # downtown Dallas — spoof your browser GPS here
MARKER = "Love's Travel Stop #212 (demo)"
NOW = datetime.now(UTC)


def _facility(db, ftype, name, dlat, dlon):
    return facility.create_facility(db, ftype, name, CENTER[0] + dlat, CENTER[1] + dlon)


def _parking(db, seeder, fac, status):
    crowd.submit(
        db,
        seeder.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": status},
        NOW,
        award=False,
    )
    crowd.update_belief(db, fac.id, crowd.SignalType.parking_fullness, as_of=NOW)


def _dwell(db, fac, i, hours=2.0):
    # a tracked visit (arrive -> depart) feeds M2 dock-time; repeat for a sample.
    # ping AT the facility's real coords (not the cluster center) so ENTER fires.
    flat, flon = facility.coordinates(db, fac)
    drv = identity.register_account(db, f"demo-dwell-{fac.name[:6]}-{i}@seed.local", "pw-123456")
    location.arm_geofence(db, drv.id, fac.id)
    location.evaluate_ping(db, drv.id, flat, flon, occurred_at=NOW - timedelta(hours=hours))
    location.evaluate_ping(db, drv.id, 33.3, -97.5, occurred_at=NOW)  # far -> exit
    location.disarm_geofence(db, drv.id, fac.id, occurred_at=NOW)


def _make_dev_driver_owner_operator(db):
    # give the dev-driver OWN authority so filed detention claims are invoiced to
    # the broker (money owed to the driver) instead of exported to a carrier. In
    # production this comes from the driver's onboarding-declared authority
    # (own_mc / leased / company), ideally FMCSA-verified.
    from sqlalchemy import select

    from app.foundation.f01_identity.domain.models import Account

    drv = db.scalar(select(Account).where(Account.email == "dev-driver@longhaul.local"))
    if drv is None:
        drv = identity.register_account(db, "dev-driver@longhaul.local", "longhaul-dev-1")
    identity.upsert_driver_profile(db, drv, authority_type=identity.AuthorityType.own_mc)
    # activate the FMCSA verification seam and pre-verify the dev-driver so the
    # verified-authority pill shows in the browser (Fake verifier, no webKey needed).
    from app.foundation.f13_flags import public as flags

    identity.register_authority_verification(db)
    flags.enable(db, identity.AUTHORITY_VERIFICATION_FLAG)
    identity.verify_authority(db, drv, mc_number="123456", dot_number="1000001")
    db.commit()
    print("dev-driver set to own_mc (owner-operator), authority verified — pill will show")


def main():
    db = SessionLocal()
    _make_dev_driver_owner_operator(db)  # always run — independent of the cluster guard
    existing = (
        [f for f in facility.nearest(db, *CENTER, 8000) if f.name == MARKER]
        if hasattr(facility, "nearest")
        else []
    )
    if existing:
        print("demo data already seeded — skipping cluster. Center:", CENTER)
        db.close()
        return

    seeder = identity.register_account(
        db, f"demo-seeder-{NOW.timestamp():.0f}@seed.local", "pw-123456"
    )
    owner = identity.register_account(
        db, f"demo-owner-{NOW.timestamp():.0f}@seed.local", "pw-123456"
    )
    merchant = m7.register_merchant(db, "TripFuel Network")

    # truck stops + rest area with live parking status
    loves = _facility(db, facility.FacilityType.truck_stop, MARKER, 0.012, -0.010)
    _parking(db, seeder, loves, "some")
    pilot = _facility(
        db, facility.FacilityType.truck_stop, "Pilot Flying J #88 (demo)", -0.010, 0.014
    )
    _parking(db, seeder, pilot, "full")
    ta = _facility(db, facility.FacilityType.truck_stop, "TA Dallas South (demo)", 0.020, -0.024)
    _parking(db, seeder, ta, "empty")
    rest = _facility(db, facility.FacilityType.rest_area, "I-35 Rest Area (demo)", -0.018, -0.008)
    _parking(db, seeder, rest, "some")

    # bookable parking property (M6) + spots
    prop = m6.create_property(
        db,
        owner.id,
        "Yardline Secured Parking (demo)",
        CENTER[0] + 0.004,
        CENTER[1] + 0.006,
        vetted=True,
    )
    m6.add_spot(db, prop, "A1", price_cents_per_night=2400)
    m6.add_spot(db, prop, "A2", price_cents_per_night=2800)

    # receivers with dock-time (M2) + approved reviews (public scorecard)
    ddc = _facility(
        db,
        facility.FacilityType.shipper_receiver,
        "Dallas Distribution Center (demo)",
        0.008,
        0.012,
    )
    for i in range(3):
        _dwell(db, ddc, i, hours=2.0 + i * 0.5)
    r1 = m2.submit_review(
        db,
        ddc.id,
        seeder.id,
        {"check_in_speed": 4, "staff_courtesy": 5},
        text="Quick check-in, staff waved me right to door 4.",
    )
    m2.moderate_review(db, r1, approve=True)
    r2 = m2.submit_review(
        db,
        ddc.id,
        seeder.id,
        {"dock_availability": 4},
        text="Doors usually open, minimal detention.",
    )
    m2.moderate_review(db, r2, approve=True)
    _facility(
        db, facility.FacilityType.shipper_receiver, "North Texas Cold Storage (demo)", -0.014, 0.004
    )

    # fuel stations with net pricing (M7)
    q = _facility(db, facility.FacilityType.fuel_station, "QuikFuel Dallas (demo)", 0.016, 0.010)
    m7.set_station_pricing(
        db, q.id, gross_cents_per_gal=419, discount_cents_per_gal=25, merchant_id=merchant.id
    )
    rf = _facility(
        db, facility.FacilityType.fuel_station, "RoadFuel Express (demo)", -0.006, -0.020
    )
    m7.set_station_pricing(
        db, rf.id, gross_cents_per_gal=409, discount_cents_per_gal=15, merchant_id=merchant.id
    )

    db.commit()
    print("Seeded demo cluster around Dallas", CENTER)
    print(
        "  facilities: 3 truck stops (some/full/empty) + rest area + 2 receivers + 2 fuel stations"
    )
    print("  bookable:   Yardline Secured Parking + 2 spots")
    print("  scorecard:  Dallas Distribution Center — dock-time + 2 approved reviews")
    db.close()


if __name__ == "__main__":
    main()
