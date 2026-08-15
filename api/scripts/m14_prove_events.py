"""AI-CONTEXT: STEP 4 — prove geofence events fire from ELD pings, before the claim path exists.

This is the observation the whole slice stands on, and the kickoff is explicit that a green
unit test is not it: *"seed the Tampa DEV facilities, point the fake Motive server's
breadcrumbs at a walk into the DEV shipper, and watch `GeofenceEvent` rows appear with the
ELD source — ENTER, DWELL_TICK, EXIT, on an armed stop created through the EXISTING rate-con
path. Put the query output in the handoff."*

WHAT THIS DELIBERATELY DOES NOT DO. It does not touch M3, draft a claim, or reach a send
path — none of that exists yet at this point in the build order, and that ordering is the
kickoff's requirement rather than a convenience: *"ELD traces that provably produce
ENTER/EXIT are a complete increment; a half-built claim path that can reach a send button is
a hazard, not progress."*

The stop is armed through `f05.arm_stop` — the SAME arming M3 rides. There is no second
arming path and there must never be one; the ELD route's entire trick is that
`f03.evaluate_ping` is account-centric, so a provider breadcrumb becomes a first-class ping
and the geofence engine cannot tell a phone was not involved.

    make m14-prove
"""

import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.modules.m14_recovery import public as m14


def _dev_shipper(db):
    """The seeded Tampa DEV shipper — the same pin `make seed-where` prints."""
    # `search_by_name` returns (Facility, score) pairs — the score travels with the row
    rows = [
        f
        for f, _score in facility.search_by_name(db, "DEV — Test Shipper", limit=10)
        if f.facility_type == facility.FacilityType.shipper_receiver
    ]
    return rows[0] if rows else None


def main() -> int:
    now = datetime.now(UTC)
    with SessionLocal() as db:
        shipper = _dev_shipper(db)
        if shipper is None:
            print("DEV shipper not seeded — run `make seed-where` first")
            return 1
        # `coordinates` returns (lat, lon) — it unpacks ST_X/ST_Y internally and swaps
        # them back. Getting this the wrong way round put the truck at lat -82, in the
        # Southern Ocean, and the probe reported zero events rather than a wrong place.
        lat, lon = facility.coordinates(db, shipper)
        print(f"facility : {shipper.name}  ({lat:.6f}, {lon:.6f})")

        account = identity.register_account(
            db, f"m14-probe-{now.timestamp()}@example.com", "pw-123456"
        )

        # --- an armed stop through the EXISTING path, not a second one -----------------
        load = loads.create_load(db, account.id, reference_number="M14-PROBE")
        stop = loads.add_stop(db, load, shipper.id, loads.StopType.delivery, sequence=1)
        loads.arm_stop(db, stop)
        db.flush()
        print("stop     : armed via f05.arm_stop (the arming M3 rides)")

        # --- a connector and a mapped vehicle -----------------------------------------
        connector = m14.connect_fleet(db, load.id, "probe-key-not-real", m14.Provider.motive)
        m14.map_vehicle(db, connector, "veh-42", account.id)
        print(f"connector: {connector.provider.value}  key ****{connector.key_last4}")

        # --- the walk: outside -> inside -> dwell -> outside ---------------------------
        # 0.01 deg latitude is ~1.1 km, comfortably outside the 150 m fence
        far = (lat + 0.01, lon)
        crumbs = [
            m14.Breadcrumb("veh-42", far[0], far[1], now - timedelta(minutes=95), speed_mps=20.0),
            m14.Breadcrumb("veh-42", lat, lon, now - timedelta(minutes=90), speed_mps=0.5),
            m14.Breadcrumb("veh-42", lat, lon, now - timedelta(minutes=60), speed_mps=0.0),
            m14.Breadcrumb("veh-42", lat, lon, now - timedelta(minutes=30), speed_mps=0.0),
            m14.Breadcrumb("veh-42", lat, lon, now - timedelta(minutes=5), speed_mps=0.0),
            m14.Breadcrumb("veh-42", far[0], far[1], now, speed_mps=18.0),
        ]
        result = m14.ingest_breadcrumbs(db, connector, crumbs, now=now)
        print(f"ingested : {result.imported} pings, {result.duplicates} dupes, "
              f"{result.skipped_unmapped} unmapped")

        # --- idempotence: the same window again must add nothing -----------------------
        again = m14.ingest_breadcrumbs(db, connector, crumbs, now=now)
        print(f"replay   : {again.imported} imported, {again.duplicates} duplicates "
              f"(polling overlaps by construction)")

        db.flush()

        # --- THE OBSERVATION ----------------------------------------------------------
        print("\n--- f03.location_ping, by source ---")
        for src, count in db.execute(
            select(location.LocationPing.source, func.count())
            .where(location.LocationPing.account_id == account.id)
            .group_by(location.LocationPing.source)
        ):
            print(f"  {src:16} {count}")

        print("\n--- f03.geofence_event for this account ---")
        events = list(
            db.scalars(
                select(location.GeofenceEvent)
                .where(location.GeofenceEvent.account_id == account.id)
                .order_by(location.GeofenceEvent.occurred_at)
            )
        )
        for e in events:
            print(f"  {e.occurred_at.isoformat()}  {e.event_type.value}")
        if not events:
            print("  (none — the slice's central claim is FALSE, stop and read why)")

        kinds = [e.event_type.value for e in events]
        print(f"\nRESULT: {len(events)} events — {kinds}")
        db.rollback()  # a probe leaves no rows behind
        return 0 if events else 4


if __name__ == "__main__":
    sys.exit(main())
