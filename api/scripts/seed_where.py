"""AI-CONTEXT: where are the DEV pins? — `make seed-where`. Dev only.

The env was not self-describing, and that is not a cosmetic gap: the owner spoofed a
browser to Tampa, opened the map, and saw nothing, because an earlier session had seeded
the `DEV —` facilities around Madison. Both halves were working exactly as built —
`_seed_origin` plants pins wherever you tell it, and the map draws what is near you — and
the only thing missing was any way to find out where "wherever" had been, short of reading
the database. You cannot arm a stop against a facility that is not near you, so the whole
stop auto-pilot was unwalkable for a reason that had nothing to do with the auto-pilot.

Deliberately a CLI target and not a screen. Answering this in the browser would need an
API route that exists in the production image and is refused only by an environment check
— more surface than the question is worth, and this is asked while seeding, which is
already a terminal. (Owner decision, 2026-08-02.)

Prints what `seed_demo._seed_origin` planted, in the form the spoofer wants: the ORIGIN to
paste into DevTools Sensors, then each facility with its distance from that origin.
"""

import db_registry

db_registry.import_all_models()

from sqlalchemy import select  # noqa: E402

from app.core.db import SessionLocal  # noqa: E402
from app.foundation.f02_facility import public as facility_registry  # noqa: E402
from app.foundation.f02_facility.domain.models import Facility  # noqa: E402
from app.foundation.f03_location.public import DEFAULT_RADIUS_M  # noqa: E402

# `_seed_origin` puts the shipper due north of the origin by this much; everything else is
# derived from it. Recovering the origin from the shipper is exact, which is why the
# shipper is the anchor rather than an average of the three.
SHIPPER_LAT_OFFSET = 0.0008
SHIPPER_NAME = "DEV — Test Shipper"


def _meters(lat1, lon1, lat2, lon2):
    import math

    r = 6371000.0
    to_rad = math.pi / 180
    x = (lon2 - lon1) * to_rad * math.cos((lat1 + lat2) / 2 * to_rad)
    y = (lat2 - lat1) * to_rad
    return math.sqrt(x * x + y * y) * r


def main():
    db = SessionLocal()
    rows = list(
        db.scalars(select(Facility).where(Facility.name.like("DEV — %")).order_by(Facility.name))
    )
    if not rows:
        print("no DEV — facilities in this database.")
        print("seed some:  make seed ORIGIN=<lat>,<lon>   (e.g. ORIGIN=27.9506,-82.4572)")
        return

    at = {f.id: facility_registry.coordinates(db, f) for f in rows}
    shippers = [f for f in rows if f.name == SHIPPER_NAME]
    if not shippers:
        # a partial seed, or someone deleted the shipper. Say so rather than guessing an
        # origin from the others — a wrong origin is worse than none, because it sends the
        # spoofer somewhere confidently.
        print("DEV facilities exist but no shipper, so the origin cannot be recovered:")
        for f in rows:
            print(f"  {f.name:<28} {at[f.id][0]:.6f},{at[f.id][1]:.6f}")
        return

    for shipper in shippers:
        s_lat, s_lon = at[shipper.id]
        origin_lat = s_lat - SHIPPER_LAT_OFFSET
        origin_lon = s_lon
        print(f"\nORIGIN  {origin_lat:.6f},{origin_lon:.6f}   <- paste into DevTools Sensors")
        near = sorted(rows, key=lambda f: _meters(origin_lat, origin_lon, *at[f.id]))
        for f in near:
            f_lat, f_lon = at[f.id]
            d = _meters(origin_lat, origin_lon, f_lat, f_lon)
            if d > 3000:
                continue  # a different seed's cluster; it gets its own ORIGIN block
            print(f"  {f.name:<28} {f_lat:.6f},{f_lon:.6f}   {d:6.0f} m from origin")
        # the number that decides whether a walk can produce an EXIT at all
        print(
            f"  geofence radius {DEFAULT_RADIUS_M:.0f} m — to leave the shipper, move MORE than "
            f"that from it (~0.0022 lat ≈ 240 m from ORIGIN), then wait up to 60 s for a ping."
        )


if __name__ == "__main__":
    main()
