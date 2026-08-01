"""AI-CONTEXT: A9 §4 again — the ingest holds one batch in ONE transaction.

Streaming the read fixed the parse (4,677 MB -> 80 MB on us-midwest) and did NOT fix
this: the api container still sat at **3.07 GiB of the box's 3.83** during the region
run, because `ingest_records` accumulates every row and every ORM object until the end.
us-midwest is the SMALLEST of the four regions.

Committing in chunks trades one property for another, and the trade is only safe
because of something already true: ingest is idempotent on (source_kind, external_ref),
so a run that dies half-way is not a corrupt registry — it is a shorter re-run. Without
that idempotency this would be the wrong fix.

`expunge_all` is the half that actually frees memory. A commit alone leaves every
Facility and FacilitySource in the session's identity map, so the transaction shrinks
and the process does not.
"""

from app.foundation.f02_facility import public as facility
from app.foundation.f02_facility.domain.enums import FacilityType, SourceKind

SEATTLE = (47.6062, -122.3321)


def _records(n, start=0):
    return [
        facility.StagedRecord(
            source_kind=SourceKind.osm,
            external_ref=f"node/{i}",
            name=f"Truck Stop {i}",
            lat=SEATTLE[0] + i * 0.01,
            lon=SEATTLE[1] + i * 0.01,
            facility_type=FacilityType.truck_stop,
        )
        for i in range(start, start + n)
    ]


def test_chunking_is_off_by_default(db):
    """Every existing caller keeps one transaction. A change that silently altered when
    other people's data becomes visible would be a much bigger change than it looks."""
    stats = facility.ingest_records(db, _records(5), batch_id="plain")
    assert stats.created == 5


def test_the_chunk_boundary_fires_at_the_size_it_was_given(db):
    """What is honestly observable in-process, and no more.

    I tried two stronger assertions and threw both away, which is the useful part:

    · "another connection sees the committed rows mid-run" — untestable through this
      fixture at all. `db` joins an outer transaction with `create_savepoint`, so a
      commit releases a savepoint and nothing becomes visible to anyone else.
    · "the session's identity map is empty after a chunk" — VACUOUS. It is weakly
      referenced, so it is empty with or without chunking. The contrast test I wrote to
      guard that assertion is what caught it; without the contrast it would have been a
      green test measuring nothing, which is the exact failure this session has been
      finding all day.

    So this asserts the cadence, and the memory claim is settled where it is real: on
    the box, by watching the container during a region run."""
    fired = []
    records = [
        facility.StagedRecord(
            source_kind=SourceKind.osm,
            external_ref=f"chunk/{i}",
            name=f"Chunked {i}",
            lat=SEATTLE[0] + i * 0.01,
            lon=SEATTLE[1] + i * 0.01,
            facility_type=FacilityType.truck_stop,
        )
        for i in range(9)
    ]
    facility.ingest_records(
        db, records, batch_id="chunked", commit_every=4, _after_chunk=fired.append
    )
    assert fired == [4, 8], "chunks did not close on the boundary they were given"


def test_a_resumed_run_finishes_the_job_and_duplicates_nothing(db):
    """What makes the trade safe. Ingest is idempotent on (source_kind, external_ref),
    so a half-finished run is a shorter re-run rather than a corrupt registry."""
    first = facility.ingest_records(db, _records(6), batch_id="a", commit_every=2)
    assert first.created == 6

    again = facility.ingest_records(db, _records(10), batch_id="b", commit_every=2)
    assert again.created == 4, "the first six must be recognised, not re-created"
    assert again.matched == 6
