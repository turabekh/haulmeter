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
from pathlib import Path

from app.foundation.f02_facility import public as facility
from app.foundation.f14_admin import public as admin
from app.ingest import runners


def _run_for(db, path):
    """This test's own job_run row, identified by the digest of the file it loaded."""
    want = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    for run in admin.job_history(db, "ingest_osm", limit=50):
        if (run.summary or {}).get("snapshot", {}).get("sha256") == want:
            return run
    raise AssertionError(f"no job_run recorded for {path}")


def test_a_file_load_records_what_it_loaded(db, tmp_path):
    src = tmp_path / "wisconsin.geojson"
    src.write_text('{"type": "FeatureCollection", "features": []}')

    runners.run_osm(db, str(src), commit=False)

    # AI-CONTEXT: find OUR row by its digest, not by "the latest". Since the started row
    # is committed on its own connection so it survives a kill, job_run rows persist
    # across tests — "latest" is whatever ran last, which is not necessarily this test.
    run = _run_for(db, src)
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

    digests = {
        _run_for(db, path).summary["snapshot"]["sha256"] for path in (old, new)
    }
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
    run = admin.job_history(db, "ingest_osm", limit=50)[0]
    assert run.ok is False
    assert run.error
    assert isinstance(run.finished_at, datetime) and run.finished_at.tzinfo is not None
    assert run.started_at <= datetime.now(UTC)


def test_the_ATTEMPT_is_visible_before_the_work_finishes(db, tmp_path):
    """The failure this missed, found by losing a real ingest on the box.

    `test_a_failed_load_is_recorded_as_a_failure_not_silence` covers an EXCEPTION —
    the code catches it and writes `ok=False`. It does NOT cover the process being
    KILLED, and on a 2 GB e2-medium that is the likely ending, not the exotic one. The
    started row was written inside the same transaction as the work, so the kill rolled
    it back with everything else: no facilities, no failure row, no trace that anything
    had been attempted. "One row per ATTEMPT" was true for the cases that politely raise.

    Committing the start separately is what makes the row survive its own process. A
    started-but-never-finished row is exactly the evidence an operator needs — it says
    "this died", which silence does not."""
    src = tmp_path / "region.geojson"
    src.write_text('{"type": "FeatureCollection", "features": []}')

    seen = {}

    def spy(*args, **kwargs):
        # what a SECOND connection can see while the load is still running
        from sqlalchemy.orm import Session as SASession

        bind = db.get_bind()
        other = SASession(bind=getattr(bind, "engine", bind))
        try:
            rows = admin.job_history(other, "ingest_osm", limit=20)
            seen["rows"] = [r for r in rows if r.finished_at is None]
        finally:
            other.close()
        return facility.IngestStats()

    runners.run_osm(db, str(src), commit=False, _work=spy)

    assert seen["rows"], "a killed load would leave no trace at all"
    assert seen["rows"][0].ok is False, "an unfinished attempt must not look successful"
    assert seen["rows"][0].finished_at is None
