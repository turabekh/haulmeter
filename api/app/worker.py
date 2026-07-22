"""AI-CONTEXT: Background worker (dev/CI parity). Runs the F2 refresh jobs behind
F13 flags (PRD §12): TPIMS dynamic availability (~3 min) and TPIMS static metadata
(daily). NTAD + OSM are manual make-target pulls, not scheduled here. A minimal
interval scheduler (no extra deps); each job has exponential failure backoff so a
dead feed doesn't log-spam every interval. Jobs no-op unless their flag is enabled.
"""

import signal
import sys
import time
from dataclasses import dataclass

from app.core.db import SessionLocal
from app.foundation.f13_flags import public as flags
from app.ingest import flags as ingest_flags
from app.ingest import runners, sources

TICK_SECONDS = 5
BACKOFF_CAP_SECONDS = 3600


@dataclass
class Job:
    name: str
    flag_key: str
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
    ]


def _run_job(job: Job, monotonic: float) -> None:
    db = SessionLocal()
    try:
        if not flags.is_enabled(db, job.flag_key):
            job.next_run = monotonic + job.interval_seconds  # flag off -> idle, quietly
            return
        summary = job.run(db)
        job.failures = 0
        job.next_run = monotonic + job.interval_seconds
        _log(f"{job.name} ok: {summary}")
    except Exception as exc:  # a dead feed must not spam every interval -> back off
        job.failures += 1
        backoff = min(job.interval_seconds * (2**job.failures), BACKOFF_CAP_SECONDS)
        job.next_run = monotonic + backoff
        _log(f"{job.name} failed ({job.failures}x): {exc!r} — retrying in {int(backoff)}s")
    finally:
        db.close()


def _startup() -> None:
    db = SessionLocal()
    try:
        ingest_flags.register_ingest_flags(db)
        sources.register_source_config(db)
        db.commit()
    except Exception as exc:
        _log(f"startup registration skipped: {exc!r}")
    finally:
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
