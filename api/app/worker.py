"""AI-CONTEXT: Background worker (dev/CI parity). Runs the refresh jobs behind F13
flags (PRD §12): TPIMS dynamic availability (~3 min), TPIMS static metadata (daily),
and the EIA regional diesel baseline (weekly, M1-FR5). NTAD + OSM are manual
make-target pulls, not scheduled here. A minimal interval scheduler (no extra deps);
each job has exponential failure backoff so a dead feed doesn't log-spam every
interval. Jobs no-op unless their flag is enabled.
"""

import signal
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.db import SessionLocal
from app.foundation.f13_flags import public as flags
from app.foundation.f14_admin import public as admin
from app.ingest import flags as ingest_flags
from app.ingest import runners, sources
from app.modules.m03_detention import public as m3
from app.modules.m05_protection import public as m5

TICK_SECONDS = 5
BACKOFF_CAP_SECONDS = 3600


@dataclass
class Job:
    name: str
    # AI-CONTEXT: None means ALWAYS RUN. Every job here gates on a module flag, and
    # `is_enabled` returns False for a flag nobody registered — so giving a foundation
    # safety net a flag is how it becomes another engine that is built, wired and
    # permanently idle. `outbound_retry` is delivery insurance for mail F8 has already
    # decided to send; there is no activation decision to make about it.
    flag_key: str | None
    interval_seconds: float
    run: object  # callable(db) -> summary
    next_run: float = 0.0
    failures: int = 0


def _log(msg: str) -> None:
    sys.stdout.write(f"worker: {msg}\n")
    sys.stdout.flush()


def _jobs() -> list[Job]:
    return [
        Job("tpims_dynamic", ingest_flags.FLAG_TPIMS_DYNAMIC, 180, runners.run_tpims_dynamic),
        Job("tpims_static", ingest_flags.FLAG_TPIMS_STATIC, 86400, runners.run_tpims_static),
        # weekly (EIA publishes on-highway diesel Mondays ~5pm ET); upsert is
        # idempotent so the interval need not align to the exact release.
        Job("eia_regional", ingest_flags.FLAG_EIA, 604800, runners.run_eia),
        # M5-FR3: the 30/14/3 credential warnings. Daily, because the offsets are
        # measured in days and a driver does not need to hear about a renewal twice
        # before lunch. F8's caps decide what actually leaves.
        Job("document_expiry", m5.FLAG_KEY, 86400, runners.run_document_expiry),
        # M3's P0 (§23 entry 106). Every OTHER job here refreshes a feed; this one
        # watches a clock that decides money, so the interval is the alert's accuracy:
        # a driver is told free time expired up to a minute after it did. Sixty seconds
        # against a two-hour free window is honest, and cheaper than the alternative of
        # scheduling a wake-up per claim. F8's own budget decides what actually leaves.
        Job("detention_clock", m3.FLAG_KEY, 60, runners.run_detention_clock),
        # audit F-06: counterparty mail that did not go out. Five minutes, because the
        # failures this exists for are transient — a restart window, a rate limit — and
        # a detention notice an hour late is still a detention notice, while one that
        # never goes is the defect. Unflagged: see Job.flag_key.
        Job("outbound_retry", None, 300, runners.run_outbound_retry),
        # audit F-09: raw GPS pings were never purged — the purge existed and nothing
        # called it. Daily; the window is an F13 key (`f03.ping_retention_days`) and 0
        # disables it. Unflagged for the same reason as outbound_retry: a foundation
        # retention job gated on a flag nobody registered is a retention policy that
        # silently does not run, which is indistinguishable from the defect being fixed.
        # The config value is the switch, and it is the honest one — an operator turning
        # this off should be setting a retention policy, not disabling a job.
        Job("location_retention", None, 86400, runners.run_location_retention),
    ]


def _run_job(job: Job, monotonic: float) -> None:
    # AI-CONTEXT: every attempt is persisted to f14.job_run as well as logged, so the
    # Admin Console Overview can answer "did the feeds run, and is anything stuck?"
    # without anyone reading container logs. A flag-off tick is NOT recorded — an
    # idle job is not an event, and recording it would bury real runs in noise.
    db = SessionLocal()
    run = None
    try:
        if job.flag_key is not None and not flags.is_enabled(db, job.flag_key):
            job.next_run = monotonic + job.interval_seconds  # flag off -> idle, quietly
            return
        started = datetime.now(UTC)
        run = admin.start_job_run(db, job.name, started)
        db.commit()

        summary = job.run(db)
        job.failures = 0
        job.next_run = monotonic + job.interval_seconds
        admin.finish_job_run(
            db,
            run,
            datetime.now(UTC),
            ok=True,
            summary=_summary_dict(summary),
            consecutive_failures=0,
            next_run_at=datetime.now(UTC) + timedelta(seconds=job.interval_seconds),
        )
        db.commit()
        _log(f"{job.name} ok: {summary}")
    except Exception as exc:  # a dead feed must not spam every interval -> back off
        job.failures += 1
        backoff = min(job.interval_seconds * (2**job.failures), BACKOFF_CAP_SECONDS)
        job.next_run = monotonic + backoff
        _record_failure(db, run, job, exc, backoff)
        _log(f"{job.name} failed ({job.failures}x): {exc!r} — retrying in {int(backoff)}s")
    finally:
        db.close()


def _summary_dict(summary: object) -> dict:
    # runners return either a dict or an IngestStats dataclass; the console wants one
    # JSON shape, and `facility_ids` is a set of UUIDs that would not serialize
    if isinstance(summary, dict):
        return summary
    return {
        key: value
        for key, value in vars(summary).items()
        if isinstance(value, (int, float, str, bool)) or value is None
    }


def _record_failure(db, run, job: Job, exc: Exception, backoff: float) -> None:
    # telemetry must never be the reason a worker dies: the session may already be
    # broken by whatever raised, so this rolls back first and swallows its own errors
    try:
        db.rollback()
        target = run if run is not None else admin.start_job_run(db, job.name, datetime.now(UTC))
        admin.finish_job_run(
            db,
            target,
            datetime.now(UTC),
            ok=False,
            error=repr(exc),
            consecutive_failures=job.failures,
            next_run_at=datetime.now(UTC) + timedelta(seconds=backoff),
        )
        db.commit()
    except Exception:
        db.rollback()


def _startup() -> None:
    # AI-CONTEXT: register EVERY model before any job runs. A job touches only its
    # own tables, but those tables carry cross-schema foreign keys (f10.submission ->
    # f01.account), and SQLAlchemy cannot configure a mapper whose FK target was
    # never imported. Importing a subset left tpims_dynamic raising
    # NoReferencedTableError on every tick — silently, because the worker logged only
    # to stdout. This is the same registration the migrations and purge scripts do.
    try:
        import db_registry

        db_registry.import_all_models()
    except Exception as exc:
        _log(f"model registration failed: {exc!r}")

    # session creation is INSIDE the guard: a database that is a few seconds late
    # coming up must leave the worker running to retry on the next tick, not kill it
    # at boot. The jobs are all flag-gated and idempotent, so a skipped startup
    # registration costs nothing but a cycle.
    db = None
    try:
        db = SessionLocal()
        ingest_flags.register_ingest_flags(db)
        sources.register_source_config(db)
        db.commit()
    except Exception as exc:
        _log(f"startup registration skipped: {exc!r}")
    finally:
        if db is not None:
            db.close()


def main() -> None:
    running = {"on": True}

    def stop(*_: object) -> None:
        running["on"] = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    _startup()
    jobs = _jobs()
    _log(f"started; jobs: {', '.join(j.name for j in jobs)} (flag-gated)")
    while running["on"]:
        now = time.monotonic()
        for job in jobs:
            if now >= job.next_run:
                _run_job(job, now)
        time.sleep(TICK_SECONDS)
    _log("stopped")


if __name__ == "__main__":
    main()
