"""AI-CONTEXT: A12 requirement 3 — "every data load records a snapshot identifier, so
what the box is running is answerable".

It was not answerable. `run_osm` recorded no JobRun at all, and the only trace an
ingest left was a `batch_id` string on source rows. So "which Wisconsin extract is
this map built from?" had no answer — and this session proved why that matters: the
extract was silently WRONG for the entire life of the project, and there was nowhere
an operator could have looked to see which one had been loaded, or when, or whether
the box and a laptop were running the same one.
"""

import hashlib
from datetime import UTC, datetime

from app.foundation.f14_admin import public as admin
from app.ingest import runners


def test_a_file_load_records_what_it_loaded(db, tmp_path):
    src = tmp_path / "wisconsin.geojson"
    src.write_text('{"type": "FeatureCollection", "features": []}')

    runners.run_osm(db, str(src), commit=False)

    run = admin.latest_job_runs(db, job_names=["ingest_osm"])["ingest_osm"]
    snap = run.summary["snapshot"]
    assert snap["name"] == "wisconsin.geojson"
    assert snap["bytes"] == src.stat().st_size
    # the CONTENT, not the path: two boxes claiming "wisconsin.geojson" prove nothing
    # about running the same data, and a re-extract keeps the name while changing
    # everything else
    assert snap["sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
    assert run.ok is True


def test_the_identifier_distinguishes_two_extracts_of_the_SAME_STATE(db, tmp_path):
    """The case this exists for. The old filter and the corrected one both produce
    `wisconsin.geojson`; they differ by 65 repair shops. A name and a date cannot tell
    them apart, and "when did the box get the good one" is exactly the question."""
    old = tmp_path / "a.geojson"
    new = tmp_path / "b.geojson"
    old.write_text('{"type": "FeatureCollection", "features": []}')
    new.write_text('{"type": "FeatureCollection", "features": [] }')  # one byte apart

    runners.run_osm(db, str(old), commit=False)
    runners.run_osm(db, str(new), commit=False)

    runs = admin.job_history(db, "ingest_osm", limit=2)
    digests = {r.summary["snapshot"]["sha256"] for r in runs}
    assert len(digests) == 2


def test_a_failed_load_is_recorded_as_a_failure_not_silence(db, tmp_path):
    """A load that dies leaves a row saying so. Otherwise the newest successful-looking
    row is from the run BEFORE the broken one, and the box reports data it is not
    running."""
    missing = tmp_path / "not-there.geojson"
    try:
        runners.run_osm(db, str(missing), commit=False)
    except Exception:
        pass
    run = admin.latest_job_runs(db, job_names=["ingest_osm"])["ingest_osm"]
    assert run.ok is False
    assert run.error
    assert isinstance(run.finished_at, datetime) and run.finished_at.tzinfo is not None
    assert run.started_at <= datetime.now(UTC)
