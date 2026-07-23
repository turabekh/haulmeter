"""AI-CONTEXT: DEV-ONLY demo seed (PRD §12). OFF by default — real POI data comes
from the F2 ingestion pipeline (NTAD/TPIMS/OSM). This runs ONLY when DEV_SEED=1,
for a rich local browser experience. Optionally DEV_SEED_ORIGIN=lat,lon plants a
few obviously-fake "DEV —" facilities (shipper, truck stop, bookable yard) around
any point on earth, so geofencing + the detention clock can be field-tested
anywhere. Idempotent-ish: skips if the marker facility exists.
Run: make seed   (or DEV_SEED=1 ... python scripts/seed_demo.py)
"""

import os
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
    return facility.create_facility(
        db, ftype, name, CENTER[0] + dlat, CENTER[1] + dlon, is_dev=True
    )


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


def _seed_account(db, email, password="pw-123456"):
    # seeder accounts have deterministic emails; a purge drops facilities but keeps
    # accounts, so get-or-create keeps `make seed` re-runnable after `make purge-demo`.
    return identity.authenticate(db, email, password) or identity.register_account(
        db, email, password
    )


def _dwell(db, fac, i, hours=2.0):
    # a tracked visit (arrive -> depart) feeds M2 dock-time; repeat for a sample.
    # ping AT the facility's real coords (not the cluster center) so ENTER fires.
    flat, flon = facility.coordinates(db, fac)
    drv = _seed_account(db, f"demo-dwell-{fac.name[:6]}-{i}@seed.local")
    location.arm_geofence(db, drv.id, fac.id)
    location.evaluate_ping(db, drv.id, flat, flon, occurred_at=NOW - timedelta(hours=hours))
    location.evaluate_ping(db, drv.id, 33.3, -97.5, occurred_at=NOW)  # far -> exit
    location.disarm_geofence(db, drv.id, fac.id, occurred_at=NOW)


def _crowd_fuel(db, fac, prices):
    # a few drivers report the pump price at this station; the consensus becomes the
    # CROWD price shown on the pin (M7-FR5), displacing the EIA regional baseline —
    # no merchant network needed. Presence is proven (ping AT the station) so each
    # report is geofence-backed, exactly like a real driver at the pump.
    flat, flon = facility.coordinates(db, fac)
    for i, cents in enumerate(prices):
        drv = _seed_account(db, f"demo-fuel-{fac.name[:6]}-{i}@seed.local")
        location.arm_geofence(db, drv.id, fac.id)
        location.evaluate_ping(db, drv.id, flat, flon, occurred_at=NOW)  # presence proof
        m7.confirm_price(db, drv.id, fac.id, cents, submitted_at=NOW)
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


def _seed_origin(db):
    # DEV_SEED_ORIGIN=lat,lon -> a few obviously-fake facilities around any point so
    # geofencing/detention can be field-tested off the US grid. Names start "DEV —".
    raw = os.environ.get("DEV_SEED_ORIGIN")
    if not raw:
        return
    try:
        lat, lon = (float(x.strip()) for x in raw.split(","))
    except ValueError:
        print(f"DEV_SEED_ORIGIN ignored (expected lat,lon): {raw!r}")
        return
    if any(f.name.startswith("DEV —") for f in facility.nearest(db, lat, lon, 3000)):
        print(f"DEV origin facilities already present near {lat},{lon}")
        return
    facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "DEV — Test Shipper", lat + 0.0008, lon,
        is_dev=True,
    )
    ts = facility.create_facility(
        db,
        facility.FacilityType.truck_stop,
        "DEV — Test Truck Stop",
        lat - 0.0008,
        lon + 0.0009,
        is_dev=True,
    )
    seeder = identity.register_account(
        db, f"dev-origin-{NOW.timestamp():.0f}@seed.local", "pw-123456"
    )
    crowd.submit(
        db,
        seeder.id,
        ts.id,
        crowd.SignalType.parking_fullness,
        {"status": "some"},
        NOW,
        award=False,
    )
    crowd.update_belief(db, ts.id, crowd.SignalType.parking_fullness, as_of=NOW)
    owner = identity.register_account(
        db, f"dev-yard-{NOW.timestamp():.0f}@seed.local", "pw-123456"
    )
    prop = m6.create_property(db, owner.id, "DEV — Test Yard", lat, lon - 0.0009, vetted=True)
    m6.add_spot(db, prop, "D1", price_cents_per_night=1500)
    db.commit()
    print(f"DEV origin seeded around {lat},{lon}: shipper, truck stop, bookable yard")


def main():
    if os.environ.get("DEV_SEED") != "1":
        print(
            "seed skipped — DEV_SEED != 1 "
            "(real POI data comes from F2 ingestion). Use `make seed`."
        )
        return
    db = SessionLocal()
    _seed_origin(db)  # honor DEV_SEED_ORIGIN even if the Dallas cluster already exists
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
    # a non-network station priced purely by CROWD reports (M7-FR5) — a couple of
    # drivers report the pump; the pin shows the consensus + "N drivers" freshness.
    indie = _facility(
        db, facility.FacilityType.fuel_station, "Indie Fuel Stop (demo)", 0.006, -0.014
    )
    _crowd_fuel(db, indie, [389, 385, 392])  # ~$3.89 crowd consensus, 3 driver reports

    db.commit()
    print("Seeded demo cluster around Dallas", CENTER)
    print(
        "  facilities: 3 truck stops (some/full/empty) + rest area + 2 receivers + 3 fuel stations"
    )
    print("  bookable:   Yardline Secured Parking + 2 spots")
    print("  scorecard:  Dallas Distribution Center — dock-time + 2 approved reviews")
    print("  fuel:       2 network (net price) + Indie Fuel Stop (crowd price, 3 reports)")
    db.close()


if __name__ == "__main__":
    main()
