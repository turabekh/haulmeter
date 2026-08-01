"""AI-CONTEXT: A9 §4 — can the database answer the question this package actually asks?

Every distance query in F2 casts to geography (`ST_DWithin(geom::geography, ...)`), and
`spatial_index=True` on `geom` builds a GEOMETRY index, which cannot answer that. So all
six were sequential scans, and nobody noticed because 6,516 rows is 28 ms on the box.

A9 multiplies that table by roughly six. A sequential scan is linear (~4.3 µs/row
measured), and `_facilities_in_area` issues one query PER FACILITY TYPE — the Drive
preset's five kinds would cost most of a second at national density, against a §20
budget of 4 s for the entire cold map.

These assert the PROPERTY, not a timing. A wall-clock assertion on a shared CI box is a
flake with a stopwatch; "the planner can use an index for this predicate" is the fact
that actually decides whether A9 is an ingest or an outage.
"""

from sqlalchemy import text

from app.foundation.f02_facility import public as facility

SEATTLE = (47.6062, -122.3321)

GEO_QUERY = """
EXPLAIN SELECT f.id FROM f02.facility f
 WHERE f.merged_into_id IS NULL
   AND ST_DWithin(f.geom::geography,
                  ST_SetSRID(ST_MakePoint(-122.3321, 47.6062), 4326)::geography, 8000)
"""


def test_the_geography_index_exists(db):
    """Declared on the MODEL, not only in the migration — the test database is built by
    `create_all`, so an index that lives only in alembic is invisible here. That is a
    small version of the same defect: a thing that exists where nothing looks at it."""
    rows = db.execute(
        text("select indexdef from pg_indexes where schemaname='f02' and indexname=:n"),
        {"n": "ix_facility_geog"},
    ).scalars().all()
    assert rows, "ix_facility_geog is missing — every F2 distance query is a seq scan"
    assert "gist" in rows[0].lower()
    assert "geography" in rows[0].lower(), "an index on the COLUMN cannot answer the CAST"


def test_the_planner_can_answer_a_geography_predicate_with_an_index(db):
    """The property that matters. On a table of a handful of test rows the planner will
    rightly prefer a sequential scan, so `enable_seqscan=off` asks the question this test
    is actually about: IF it wanted an index, is there one it can use? With only the
    geometry index there is not."""
    facility.create_facility(db, facility.FacilityType.repair, "Probe Diesel", *SEATTLE)
    db.execute(text("SET LOCAL enable_seqscan = off"))
    plan = "\n".join(db.execute(text(GEO_QUERY)).scalars().all())
    assert "ix_facility_geog" in plan, f"the geography predicate cannot use an index:\n{plan}"
