"""F-10 — the worker's schedule was in-process only.

`Job.next_run` and `Job.failures` were fields on an in-memory dataclass keyed off
`time.monotonic()`, so two worker containers both ran every job and every restart
fired every job at once. `f14.job_run` records one row per ATTEMPT — history, not
schedule state — so it could not prevent a run it has no row for yet.

The race test does NOT use the `db` fixture, for the reason 119's F-28 test gives:
that fixture's work is invisible to any other connection, which is exactly the
condition a race needs.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.foundation.f14_admin import public as admin

T0 = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


def test_a_job_with_no_row_is_due_now(db):
    admin.ensure_job_schedule(db, "tpims_dynamic", T0)
    assert admin.claim_job(db, "tpims_dynamic", T0, 180) is True


def test_ensure_never_rewinds_an_existing_row(db):
    # this row IS the reason a restart stops refiring every job — seeding it again at
    # boot must not move it back to now
    admin.ensure_job_schedule(db, "eia_regional", T0)
    admin.release_job(db, "eia_regional", T0 + timedelta(days=7))
    admin.ensure_job_schedule(db, "eia_regional", T0)

    assert admin.job_schedules(db)["eia_regional"].next_run_at == T0 + timedelta(days=7)
    assert admin.claim_job(db, "eia_regional", T0, 604800) is False


def test_a_claimed_job_is_not_claimable_again_until_the_lease_expires(db):
    admin.ensure_job_schedule(db, "detention_clock", T0)
    assert admin.claim_job(db, "detention_clock", T0, 60) is True
    # same instant, second worker
    assert admin.claim_job(db, "detention_clock", T0, 60) is False


def test_a_dead_worker_does_not_hold_a_job_forever(db):
    # nothing releases the lease when a container is killed mid-run; the job has to
    # come back by itself rather than needing a human
    admin.ensure_job_schedule(db, "document_expiry", T0)
    assert admin.claim_job(db, "document_expiry", T0, 86400) is True
    lease = admin.job_schedules(db)["document_expiry"].locked_until
    assert admin.claim_job(db, "document_expiry", lease + timedelta(seconds=1), 86400) is True


def test_the_lease_floor_covers_a_job_slower_than_its_own_interval(db):
    # detention_clock runs every 60s. A 60s lease would hand a second worker the run
    # while the first is still inside it — the duplicate-notification case.
    admin.ensure_job_schedule(db, "detention_clock", T0)
    admin.claim_job(db, "detention_clock", T0, 60)
    lease = admin.job_schedules(db)["detention_clock"].locked_until
    assert (lease - T0).total_seconds() >= 300


def test_release_records_the_backoff_streak_so_a_restart_does_not_clear_it(db):
    admin.ensure_job_schedule(db, "tpims_static", T0)
    admin.claim_job(db, "tpims_static", T0, 86400)
    admin.release_job(db, "tpims_static", T0 + timedelta(hours=2), consecutive_failures=3)

    row = admin.job_schedules(db)["tpims_static"]
    assert row.consecutive_failures == 3
    assert row.locked_until is None and row.locked_by is None


def test_the_worker_seeds_its_schedule_from_the_database(db):
    from app.worker import _jobs, _seed_schedule

    jobs = _jobs()
    for job in jobs:
        job.next_run = 0.0  # the in-memory state a restart leaves behind
    _seed_schedule(jobs, db)

    assert {j.name for j in jobs} <= set(admin.job_schedules(db))
    # and a restart no longer means "every job, right now": each carries a real delay
    assert all(job.next_run > 0.0 for job in jobs)


# --- the race, across two real connections ---
def test_only_one_of_two_workers_claims_the_same_job(engine):
    """The only test here that can fail if the claim stops being a claim.

    Everything above runs inside one transaction, where a claim never contends with
    itself. This commits on two independent sessions — a rolling restart, which is the
    moment compose genuinely has two workers.
    """
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    worker_a, worker_b = factory(), factory()
    name = "race_probe_job"
    try:
        admin.ensure_job_schedule(worker_a, name, T0)
        worker_a.commit()

        first = admin.claim_job(worker_a, name, T0, 180, "worker-a")
        second = admin.claim_job(worker_b, name, T0, 180, "worker-b")

        assert [first, second] == [True, False]
        assert admin.job_schedules(worker_b)[name].locked_by == "worker-a"
    finally:
        worker_a.rollback()
        worker_b.rollback()
        cleanup = factory()
        try:
            cleanup.execute(
                text("DELETE FROM f14.job_schedule WHERE job_name = :n"), {"n": name}
            )
            cleanup.commit()
        finally:
            cleanup.close()
        worker_a.close()
        worker_b.close()
