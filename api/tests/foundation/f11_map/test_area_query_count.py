"""AI-CONTEXT: A9 §4 predicted this and named the wrong culprit.

§4 says "`_enrich` is per-pin ... bulk reads in M3, M6 and M7 come first". Measured on
the deployed box at national density (15,147 facilities), `_enrich` is not the problem:

    flags.is_enabled                 1.7 ms
    facilities_in_area (1 type)     33.1 ms
    facilities_in_area (5 types)   284.9 ms
    pins_for                         5.2 ms

The area lookup issues ONE QUERY PER FACILITY TYPE, and the Drive preset has five. Each
costs ~33 ms even though `EXPLAIN` shows the geography predicate executing in under a
millisecond against `ix_facility_geog` — the time is PostGIS geography query PLANNING,
paid once per type. The whole overlay endpoint was 639 ms against §20's 300 ms
tab-switch budget.

Counting queries rather than timing them: a wall-clock assertion on shared CI is a flake
with a stopwatch, and the defect is structural — N queries where one will do.
"""

from sqlalchemy import event

from app.foundation.f02_facility import public as facility
from app.foundation.f11_map import public as mapsvc

DALLAS = (32.7767, -96.7970)
KINDS = [
    facility.FacilityType.truck_stop,
    facility.FacilityType.rest_area,
    facility.FacilityType.fuel_station,
    facility.FacilityType.weigh_station,
    facility.FacilityType.scale,
]


def _count_selects(db, fn):
    seen = []

    def before(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "f02.facility" in statement:
            seen.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", before)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", before)
    return len(seen)


def test_one_query_covers_every_facility_type(db):
    for i, kind in enumerate(KINDS):
        facility.create_facility(db, kind, f"Site {i}", DALLAS[0] + i * 0.001, DALLAS[1])
    db.flush()

    n = _count_selects(
        db, lambda: mapsvc.facilities_in_area(db, *DALLAS, 8000, facility_types=KINDS)
    )
    assert n == 1, f"the area lookup issued {n} queries for {len(KINDS)} types"


def test_it_still_returns_exactly_the_types_asked_for(db):
    facility.create_facility(db, facility.FacilityType.truck_stop, "Stop", *DALLAS)
    facility.create_facility(db, facility.FacilityType.repair, "Shop", DALLAS[0] + 0.001, DALLAS[1])
    db.flush()

    got = mapsvc.facilities_in_area(
        db, *DALLAS, 8000, facility_types=[facility.FacilityType.truck_stop]
    )
    assert [f.name for f in got] == ["Stop"]

    both = mapsvc.facilities_in_area(
        db, *DALLAS, 8000,
        facility_types=[facility.FacilityType.truck_stop, facility.FacilityType.repair],
    )
    assert sorted(f.name for f in both) == ["Shop", "Stop"]


def test_no_duplicates_when_types_overlap(db):
    # the loop it replaces deduplicated by id into a dict; a single IN query must not
    # reintroduce duplicates when a caller passes the same kind twice
    facility.create_facility(db, facility.FacilityType.truck_stop, "Stop", *DALLAS)
    db.flush()
    got = mapsvc.facilities_in_area(
        db, *DALLAS, 8000,
        facility_types=[facility.FacilityType.truck_stop, facility.FacilityType.truck_stop],
    )
    assert len(got) == 1
