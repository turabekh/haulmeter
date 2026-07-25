"""AI-CONTEXT: worker startup — model registration and job telemetry.

This file exists because of a bug the Admin Console 2.0 telemetry surfaced on its
first run: `tpims_dynamic` had been raising NoReferencedTableError on **every tick
since 25 July** and nobody knew, because the worker logged only to stdout.

The cause: a job touches only its own tables, but those tables carry cross-schema
foreign keys (`f10.submission` -> `f01.account`), and SQLAlchemy cannot configure a
mapper whose FK target was never imported. The worker imported a subset.

The test below cannot reproduce the failure in-process — pytest's conftest imports
every model before any test runs, which is precisely why the break survived a green
suite. So it asserts the guarantee instead: startup performs the full registration,
and the metadata a job needs is actually present afterwards.
"""

import inspect

from app.core.db import Base


def test_startup_registers_every_model_not_a_subset():
    # the assertion that would have caught the original break at review time
    import app.worker as worker

    source = inspect.getsource(worker._startup)
    assert "db_registry" in source
    assert "import_all_models" in source


def test_the_cross_schema_targets_a_job_needs_are_registered():
    import db_registry

    db_registry.import_all_models()
    tables = set(Base.metadata.tables)

    # f10.submission's FK target — the one that was missing
    assert "f01.account" in tables
    assert "f10.submission" in tables
    # and f02, which the TPIMS runner writes through
    assert "f02.facility" in tables


def test_registration_failure_never_kills_the_worker(monkeypatch):
    """Telemetry and bookkeeping must not become the reason a worker dies. A broken
    registration should log and continue, leaving the job to fail loudly on its own
    terms rather than taking the process down at boot."""
    import app.worker as worker

    def explode(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(worker, "SessionLocal", explode)
    logged: list[str] = []
    monkeypatch.setattr(worker, "_log", logged.append)

    worker._startup()  # must not raise
    assert any("skipped" in line for line in logged)


def test_a_job_summary_is_reduced_to_json_safe_values():
    # IngestStats carries a set of UUIDs that would not serialize into the telemetry
    # row; the console needs one JSON shape per job, whatever the runner returns
    import app.worker as worker
    from app.foundation.f02_facility import public as facility

    stats = facility.IngestStats(staged=51, created=0, matched=51, skipped=0)
    stats.facility_ids = {"not-json-safe"}

    summary = worker._summary_dict(stats)
    assert summary == {"staged": 51, "created": 0, "matched": 51, "skipped": 0}
    assert "facility_ids" not in summary


def test_a_dict_summary_passes_through_unchanged():
    import app.worker as worker

    assert worker._summary_dict({"regions": 6}) == {"regions": 6}
