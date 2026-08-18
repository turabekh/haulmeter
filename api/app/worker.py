"""AI-CONTEXT: Background worker (dev/CI parity). Runs the refresh jobs behind F13
flags (PRD §12): TPIMS dynamic availability (~3 min), TPIMS static metadata (daily),
and the EIA regional diesel baseline (weekly, M1-FR5). NTAD + OSM are manual
make-target pulls, not scheduled here. A minimal interval scheduler (no extra deps);
each job has exponential failure backoff so a dead feed doesn't log-spam every
interval. Jobs no-op unless their flag is enabled.
"""

import os
import signal
import socket
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
# who holds a lease, for the operator staring at a job that has not moved. Hostname is
# the container id under compose, which is the thing they can actually go and look at.
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


@dataclass
class Job:
    name: str
    # AI-CONTEXT: None means ALWAYS RUN. Every job here gates on a module flag, and
    # `is_enabled` returns False for a flag nobody registered — so giving a foundation
    # safety net a flag is how it becomes another engine that is built, wired and
    # permanently idle. `outbound_mail` is the delivery path for mail F8 has already
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
        # M3-FR6's dunning cadence (finding F6). Daily: the offsets are day 3 / 10 / 21,
        # so a finer interval buys nothing and a coarser one would miss a day's window.
        # Behind M3's own flag — unlike `outbound_mail`, this is not merely delivery
        # for mail already decided on, it DECIDES to send, and that is an activation
        # question the module's flag owns. The day-21 escalation offer additionally waits
        # on the `collection_partner_agreement` gate; see `run_dunning`.
        Job("dunning", m3.FLAG_KEY, 86400, runners.run_dunning),
        # AI-CONTEXT: counterparty mail — now the ONLY thing that sends it, not a retry
        # net (audit F-06 built it; §23 built the rest around it).
        #
        # SIXTY SECONDS, not the five minutes this ran at when it only picked up failures.
        # The interval used to be a retry cadence, where "a detention notice an hour late
        # is still a detention notice" was the right argument. It is now FIRST-DELIVERY
        # latency: it is how long after a driver taps Send that a broker's mail actually
        # leaves, and the screen says `queued` for exactly this long. A minute is a
        # truthful "sending"; five would make the queued state something a driver waits on
        # and doubts. The sweep is one indexed query against `sent_at IS NULL`, so the
        # extra ticks cost nothing when there is nothing to send.
        #
        # Unflagged: see Job.flag_key. This is delivery for mail F8 has already decided to
        # send — there is no activation decision, and a flag nobody registered would mean
        # no counterparty mail leaves this box at all.
        Job("outbound_mail", None, 60, runners.run_outbound_mail),
        # J1-D1's arrival reminder. Sixty seconds because the lead time is minutes, not
        # hours, and a tick coarser than the window would miss appointments entirely.
        # Unflagged HERE and gated inside the dispatcher instead: a job that does not run
        # cannot be observed running, and silence is this class's most likely failure.
        Job("arrival_reminders", None, 60, runners.run_arrival_reminders),
        # AI-CONTEXT: officer-line synthesis (E3 §E3.1.2). FLAGGED, unlike the sweep
        # below it: that one is a promise, this one is a cost. Fifteen minutes because
        # content is released by a human a few lines at a time, and a driver reaching a
        # newly released line before its voice exists simply reads it — the surface
        # already treats text as the simulation when audio is absent.
        Job("m15_content_audio", "m15_roadside", 900, runners.run_m15_content_audio),
        # AI-CONTEXT: EVERY 2s, and the number is the fix for a 13-second result screen.
        # The conversation defers the rubric (~3.4s a turn) so the officer can answer in
        # ~2s — which means a driver who leaves a 3-turn stop early used to arrive at the
        # result screen with THREE unsettled turns and wait 13.2s, measured, in front of
        # anonymous skeletons. At 2s the sweep settles each turn while the driver is
        # speaking the next answer, so by the end there is usually nothing left to do.
        # The query is a partial-indexed `where scoring_state = 'pending' limit 50`; the
        # tick costs approximately nothing and buys back most of that wait.
        Job("m15_score_turns", None, 2, runners.run_m15_score_turns),
        # AI-CONTEXT: the 30-day audio retention sweep (E3 §E3.4.3, D14). UNFLAGGED for
        # the same reason `outbound_mail` is, and the runner argues it at length: a
        # retention promise a feature flag can revoke was never a promise. Hourly because
        # the window is thirty days — a coarser tick would be indistinguishable and a
        # finer one would scan for nothing all day.
        Job("audio_retention", None, 3600, runners.run_audio_retention),
        # AI-CONTEXT: driver push, and the same argument as `outbound_mail` one line up.
        # `dispatch` opened an HTTP connection per subscription inside the request that
        # decided to notify — every §13.1 law is still applied there, at the moment the
        # driver would be interrupted; only the transport moved. Sixty seconds because
        # the P0 this carries is a detention clock, and unflagged because a flag nobody
        # registered would mean no push ever leaves the box.
        Job("push_delivery", None, 60, runners.run_push_delivery),
        # audit F-09: raw GPS pings were never purged — the purge existed and nothing
        # called it. Daily; the window is an F13 key (`f03.ping_retention_days`) and 0
        # disables it. Unflagged for the same reason as outbound_mail: a foundation
        # retention job gated on a flag nobody registered is a retention policy that
        # silently does not run, which is indistinguishable from the defect being fixed.
        # The config value is the switch, and it is the honest one — an operator turning
        # this off should be setting a retention policy, not disabling a job.
        Job("location_retention", None, 86400, runners.run_location_retention),
        # AI-CONTEXT: image derivatives. "Thumbnail" was a variable name in two surfaces
        # and never a file — both rendered the ORIGINAL into a box a few dozen dp across,
        # so opening a past load pulled every full-size photograph of every stop.
        #
        # Five minutes rather than a minute: nothing BLOCKS on a thumbnail. A surface with
        # no derivative yet falls back to the original, which is exactly the behaviour
        # that shipped, so the cost of being late is that one contact sheet is briefly as
        # slow as it always was. Being aggressive here would buy nothing and would put
        # image decoding on the same cadence as M3's money clock.
        #
        # Unflagged, for the same reason as `outbound_mail` and `location_retention`:
        # this is infrastructure behind surfaces that are already live, not a capability
        # with an activation decision. A flag nobody registered returns False, and a
        # derivative job that silently never runs is indistinguishable from the defect it
        # was written to fix.
        Job("image_thumbnails", None, 300, runners.run_image_thumbnails),
        # AI-CONTEXT: M14-FR2, and it is FLAGGED unlike the four jobs above it.
        #
        # The distinction those carry is "infrastructure behind surfaces that are already
        # live has no activation decision". This is the opposite: it makes an outbound
        # call to a third party using a fleet's own credential, so there is very much an
        # activation decision and `m14_overlay` is it. A flag nobody registered returns
        # False, which is exactly the behaviour wanted here — no key, no packets.
        #
        # 60 s gives ±60 s arrival granularity against F3's ±3 min target, which is fine
        # and is DISCLOSED in the pack rather than implied away: an ELD-derived arrival is
        # a provider breadcrumb, not a GPS-second observation.
        Job("m14_poll", m14_flag_key(), 60, runners.run_m14_poll),
    ]


def m14_flag_key() -> str:
    # imported lazily: the worker module is imported by tests that never touch M14, and a
    # module-level import here would drag the whole overlay into every one of them
    from app.modules.m14_recovery import public as m14

    return m14.FLAG_KEY


def _run_job(job: Job, monotonic: float) -> None:
    # AI-CONTEXT: every attempt is persisted to f14.job_run as well as logged, so the
    # Admin Console Overview can answer "did the feeds run, and is anything stuck?"
    # without anyone reading container logs. A flag-off tick is NOT recorded — an
    # idle job is not an event, and recording it would bury real runs in noise.
    db = SessionLocal()
    run = None
    claimed = False
    try:
        if job.flag_key is not None and not flags.is_enabled(db, job.flag_key):
            job.next_run = monotonic + job.interval_seconds  # flag off -> idle, quietly
            return
        # audit F-10: the DB decides who runs this, not this process's own clock.
        # The flag check stays FIRST — claiming a job only to find its flag is off
        # would take a lease, log nothing, and make a disabled job look contended.
        if not admin.claim_job(db, job.name, datetime.now(UTC), job.interval_seconds, WORKER_ID):
            job.next_run = monotonic + TICK_SECONDS  # another worker has it, or not due
            return
        claimed = True
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
        if claimed:
            _release(db, job)
        db.close()


def _release(db, job: Job) -> None:
    # the lease must come off even when the run raised, or the job waits it out for no
    # reason. Its own failures are swallowed for the same reason `_record_failure`
    # swallows: bookkeeping must never be what kills the worker.
    try:
        db.rollback()
        seconds = job.interval_seconds if job.failures == 0 else min(
            job.interval_seconds * (2**job.failures), BACKOFF_CAP_SECONDS
        )
        admin.release_job(
            db,
            job.name,
            datetime.now(UTC) + timedelta(seconds=seconds),
            consecutive_failures=job.failures,
        )
    except Exception as exc:
        db.rollback()
        _log(f"{job.name} lease release failed: {exc!r}")


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

    # AI-CONTEXT: the worker needs OBJECT STORAGE too, and for the life of this project
    # it did not have it. `_wire_object_storage` ran in the API's FastAPI lifespan, and
    # this is a different process — so `default_storage()` here was the empty in-memory
    # dict every process starts with. No job had ever reached for a stored byte, so
    # nothing had failed; the first one that did (image derivatives) failed on every
    # single row and would have gone on doing so forever, reporting a count.
    #
    # Logged either way. A worker silently running against in-memory storage is exactly
    # the class of defect the API's own warning was added for.
    try:
        from app.wiring import wire_object_storage

        _log("object storage: minio" if wire_object_storage("worker") else "object storage: MEMORY")
    except Exception as exc:
        _log(f"object storage wiring failed: {exc!r}")

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


def _seed_schedule(jobs: list[Job], db=None) -> None:
    """AI-CONTEXT: audit F-10's second half — `next_run` was an in-memory 0.0, so EVERY
    restart fired EVERY job immediately. Idempotent upserts did not care; a crash-loop
    replaying `document_expiry` sends a driver the same credential warning over and
    over, with only F8's caps between it and the phone.

    A job with no row is due NOW, which is the right answer for a genuinely new job and
    preserves today's behaviour on a fresh box. A job WITH a row resumes where it was.

    Guarded like `_startup`: a database a few seconds late must leave the worker running
    to retry, not kill it at boot. Falling back to the in-memory schedule is exactly the
    old behaviour, which is the safe direction to fail in.
    """
    own_session = db is None
    try:
        db = SessionLocal() if own_session else db
        now = datetime.now(UTC)
        for job in jobs:
            admin.ensure_job_schedule(db, job.name, now)
        db.commit()
        monotonic = time.monotonic()
        for name, row in admin.job_schedules(db).items():
            job = next((j for j in jobs if j.name == name), None)
            if job is None:
                continue
            job.failures = row.consecutive_failures
            job.next_run = monotonic + max(0.0, (row.next_run_at - now).total_seconds())
    except Exception as exc:
        _log(f"schedule seeding skipped: {exc!r}")
    finally:
        if own_session and db is not None:
            db.close()


def main() -> None:
    running = {"on": True}

    def stop(*_: object) -> None:
        running["on"] = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    _startup()
    jobs = _jobs()
    _seed_schedule(jobs)
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
