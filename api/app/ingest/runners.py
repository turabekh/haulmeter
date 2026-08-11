"""AI-CONTEXT: ingestion runners (composition layer — PRD §12). Compose the F2
pipeline (facilities) with F10 (authoritative belief) for TPIMS dynamic. Live HTTP
happens here, invoked from make targets / the worker — never from CI (tests drive
the pure adapters + pipeline against committed fixtures). Idempotent by design.
"""

import os
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility
from app.foundation.f10_crowd import public as crowd
from app.foundation.f14_admin import public as admin
from app.modules.m07_fuel import public as m7

from . import sources


def _batch(name: str) -> str:
    return f"{name}-{int(datetime.now(UTC).timestamp())}"


# AI-CONTEXT: A12 requirement 3 — "every data load records a snapshot identifier, so
# what the box is running is answerable". It was not answerable: `run_osm` recorded no
# JobRun at all, and an ingest left nothing behind but a `batch_id` string.
#
# The digest is the identifier, not the filename and not the date. Two boxes both
# holding "wisconsin.geojson" prove nothing about running the same data — and this
# session is the argument: the old filter and the corrected one produce a file of the
# same name that differ by 65 repair shops. "When did the box get the good one" is a
# question only content can answer.
# big enough that the per-chunk commit is not the cost, small enough that a killed
# region run loses minutes rather than everything
OSM_COMMIT_EVERY = 500


def _snapshot(path: str) -> dict:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = os.stat(path)
    return {
        "name": os.path.basename(path),
        "path": path,
        "bytes": stat.st_size,
        "sha256": digest.hexdigest(),
        "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
    }


def _record_load(db: Session, job_name: str, source, work):
    """One row per ATTEMPT, following the JobRun rule the worker already uses: a load
    that dies leaves a row saying so, or the newest healthy-looking row is from the run
    BEFORE the broken one and the box reports data it is not running.

    AI-CONTEXT: the started row is COMMITTED before the work, and that is not tidiness.
    The first version wrote it inside the same transaction as the ingest, which covers a
    load that politely raises and NOT a load that is killed — and on the deployed
    e2-medium (~2 GB free, and a region ingest sits at 3 GB) killed is the likely ending,
    not the exotic one. A real us-midwest run died that way: the rollback took the
    failure row with it, so there were no facilities, no error, and no trace that
    anything had been attempted at all.

    A started-but-never-finished row is precisely the evidence an operator wants. It
    says "this died", which silence does not.
    """
    from sqlalchemy.orm import Session as _Session

    # OWN CONNECTION, not the ingest's. Telemetry that shares the transaction it reports
    # on disappears with it — which is the whole failure: a rollback (or a kill) took the
    # evidence along with the data. On its own connection the started row is durable the
    # moment it is written, and the ingest's own rollback cannot reach it.
    #
    # Bound to the CALLER'S engine rather than `SessionLocal`, and that is not a detail:
    # the test suite runs against a separate database, so a hardcoded SessionLocal wrote
    # the row into the DEV database while the test looked in the test one — never found
    # it, and quietly polluted dev on every run.
    bind = db.get_bind()
    engine = getattr(bind, "engine", bind)
    telemetry = _Session(bind=engine)
    try:
        run = admin.start_job_run(telemetry, job_name, datetime.now(UTC))
        telemetry.commit()
        run_id = run.id
    finally:
        telemetry.close()

    def _finish(**fields):
        session = _Session(bind=engine)
        try:
            row = session.get(admin.JobRun, run_id)
            admin.finish_job_run(session, row, datetime.now(UTC), **fields)
            session.commit()
        finally:
            session.close()

    try:
        snapshot = source() if callable(source) else source
        stats = work()
    except Exception as exc:
        _finish(ok=False, error=str(exc)[:500])
        raise
    _finish(
        ok=True,
        summary={
            "snapshot": snapshot,
            "staged": stats.staged,
            "created": stats.created,
            "matched": stats.matched,
            "skipped": stats.skipped,
            "facilities": len(stats.facility_ids),
        },
    )
    return stats


def _merge(total: facility.IngestStats, part: facility.IngestStats) -> None:
    total.staged += part.staged
    total.created += part.created
    total.matched += part.matched
    total.skipped += part.skipped
    total.facility_ids |= part.facility_ids


def run_ntad(
    db: Session, page_size: int | None = None, commit: bool = True
) -> facility.IngestStats:
    base = sources.source_url(db, "ntad_featureserver")
    size = page_size or facility.ingest.fetch_ntad_max_record_count(base)
    batch = _batch("ntad")
    total = facility.IngestStats()
    for page in facility.iter_ntad_pages(base, size):
        _merge(total, facility.ingest_records(db, facility.parse_ntad(page), batch_id=batch))
        if commit:
            db.commit()
    return total


def run_tpims_static(db: Session, commit: bool = True) -> facility.IngestStats:
    records = facility.ingest.fetch_tpims(sources.source_url(db, "tpims_static"))
    stats = facility.ingest_records(
        db, facility.parse_tpims_static(records), batch_id=_batch("tpims-static")
    )
    if commit:
        db.commit()
    return stats


def run_tpims_dynamic(db: Session, now: datetime | None = None, commit: bool = True) -> dict:
    now = now or datetime.now(UTC)
    records = facility.ingest.fetch_tpims(sources.source_url(db, "tpims_dynamic"))
    statuses = facility.parse_tpims_dynamic(records)
    applied = 0
    skipped = 0
    for st in statuses:
        fac = facility.facility_for_source(db, facility.SourceKind.tpims, st.site_id)
        if fac is None:
            skipped += 1  # site not in the registry yet (run tpims_static first)
            continue
        if not facility.has_usable_reading(st):
            skipped += 1  # "Unknown"/no reading on an open site -> no belief (any trustData)
            continue
        submission = crowd.submit_authoritative(
            db,
            fac.id,
            crowd.SignalType.parking_fullness,
            {
                "status": facility.derive_parking_status(st),
                "available": st.available,
                "trend": st.trend,
                "source": "tpims",
            },
            submitted_at=st.reported_at,
            source="tpims",
            trust_data=st.trust_data,  # trustData=false -> not recorded (condition A)
        )
        if submission is None:
            skipped += 1
            continue
        crowd.update_belief(db, fac.id, crowd.SignalType.parking_fullness, as_of=now)
        applied += 1
    if commit:
        db.commit()
    return {"applied": applied, "skipped": skipped}


def run_osm(
    db: Session, geojson_path: str, commit: bool = True, _work=None
) -> facility.IngestStats:
    def load():
        # STREAMED, not loaded whole. Measured on us-midwest (573 MB): json.load peaks
        # at 4677 MB and the box has ~2 GB, so it would be OOM-killed there; streaming
        # peaks at 80 MB. See `iter_geojson_features`.
        records = facility.parse_osm_features(facility.iter_geojson_features(geojson_path))
        # CHUNKED: A9 batches by region, and one region in one transaction sat at
        # 3.07 GiB of the box's 3.83. Safe only because ingest is idempotent on
        # (source_kind, external_ref) — a run that dies is a shorter re-run.
        # only when the caller actually wants a commit — `commit=False` means "nothing
        # persists", and chunking that ignored it would break that promise quietly,
        # which is worse than not chunking
        return facility.ingest_records(
            db,
            records,
            batch_id=_batch("osm"),
            commit_every=OSM_COMMIT_EVERY if commit else None,
        )

    stats = _record_load(db, "ingest_osm", lambda: _snapshot(geojson_path), _work or load)
    if commit:
        db.commit()
    return stats


def run_document_expiry(db: Session, commit: bool = True) -> dict:
    """M5-FR3's unattended half. F6 computes what is due at 30/14/3; this is the
    caller F6 deliberately does not have, since a documents service should not know
    what a notification is."""
    from app.foundation.f08_notifications import public as notify
    from app.modules.m05_protection import public as m5

    # AI-CONTEXT: the per-ACCOUNT factory, not one shared recorder (§23 entry 111).
    #
    # This walked every driver's due credentials through a single
    # `RecordingNotificationGateway()`, which records and never pushes — so on a box with
    # a VAPID keypair the reminders reached the inbox and no phone. `run_detention_clock`
    # below was given `gateway_for` when entry 111 shipped; this was missed, and it is
    # the job whose whole purpose is reaching a driver who is NOT looking at the app.
    sent = m5.dispatch_expiry_reminders(db, notify.gateway_for)
    if commit:
        db.commit()
    # `delivered` can no longer be counted off one recorder — each account gets its own
    # gateway. F8 records every dispatch, suppressed or not, so the inbox is the honest
    # source; a dispatch that F8 held for quiet hours was never "delivered" anyway.
    return {"considered": len(sent), "delivered": sum(1 for n in sent if n is not None)}


# AI-CONTEXT: finding F11 — a no-op tick used to COMMIT. `run_detention_clock` runs every
# 60 seconds and normally finds nothing due, so the worker opened and committed an empty
# transaction a thousand times a day. Harmless, and still worth not doing: an empty commit
# is a write-ahead log entry, a replication event and a line of noise in any slow-query or
# transaction-rate view, all of it saying that something happened when nothing did.
#
# `scanned` is deliberately NOT counted as work — the whole point of the summary is that a
# scan which decided nothing is not an event.
_SCAN_ONLY_KEYS = frozenset({"scanned", "considered"})


def _did_work(summary: dict) -> bool:
    return any(
        value for key, value in summary.items() if key not in _SCAN_ONLY_KEYS
    )


def run_detention_clock(db: Session, commit: bool = True) -> dict:
    """M3's P0, which nothing had ever fired (§23 entries 106, 107).

    AI-CONTEXT: the detention clock is computed on READ, so the instant free time
    expires passes unobserved unless a driver happens to have the screen open. This is
    the caller that watches it. Since §23 entry 111 it delivers over Web Push where a
    VAPID keypair is configured, and records to the inbox either way.
    """
    from app.foundation.f08_notifications import public as notify
    from app.modules.m03_detention import public as m3

    # AI-CONTEXT: per-CLAIM gateway, because Web Push is addressed to a driver's own
    # browsers (§23 entry 111) — one shared instance could only push to one account.
    # Unconfigured deployments fall back to the recording gateway, so this runs the
    # same everywhere and a laptop still exercises the tiering.
    summary = m3.dispatch_clock_alerts(db, notify.gateway_for)
    # finding F11: only commit when something was actually decided — see `_did_work`
    if commit and _did_work(summary):
        db.commit()
    return summary


def run_dunning(db: Session, commit: bool = True) -> dict:
    """M3-FR6's follow-up cadence, which had no caller at all (finding F6).

    AI-CONTEXT: `dunning_schedule` computed day 3 / 10 / 21 and was called by its own unit
    test and nothing else, so no broker has ever been chased for a detention invoice. This
    is the caller. Daily, because the offsets are measured in days.

    On the counterparty gateway, not a per-driver one: this is outbound mail to a broker,
    not a push to a phone. Where SMTP is unconfigured it falls back to recording, so a
    laptop exercises the cadence without sending anything.

    Commits only when it did work — see `run_detention_clock` (finding F11).
    """
    from app.foundation.f08_notifications import public as notify
    from app.modules.m03_detention import public as m3

    summary = m3.run_dunning(db, notify.counterparty_gateway())
    if commit and _did_work(summary):
        db.commit()
    return summary


def run_eia(db: Session, commit: bool = True) -> dict:
    # weekly EIA regional diesel refresh (M1-FR5). Idempotent upsert per PADD region,
    # so re-running before EIA publishes just rewrites the same week — cadence is
    # forgiving. Live pull; make-target + worker only, never CI.
    payload = m7.fetch_eia(os.environ.get("EIA_API_KEY", ""))
    regions = m7.ingest_eia_prices(db, payload)
    if commit:
        db.commit()
    return {"regions": regions}


def run_outbound_retry(db: Session, commit: bool = True) -> dict:
    """Re-send counterparty mail that did not go out (audit F-06).

    AI-CONTEXT: one SMTP attempt with a ten-second timeout was the entire delivery
    strategy. A transient blip or a Gmail rate limit permanently lost a detention notice
    — the document the whole detention wedge exists to deliver — and because the failure
    was swallowed into a string nobody read, with `sent_at` written anyway, nothing in
    the product could tell you it had happened.

    Runs on the counterparty gateway rather than a per-driver one: this is outbound mail
    to a broker, not a push to a phone. Where SMTP is unconfigured the gateway falls back
    to recording, so a laptop exercises the sweep without sending anything.
    """
    from app.foundation.f08_notifications import public as notify

    summary = notify.retry_unsent_messages(db, notify.counterparty_gateway())
    if commit:
        db.commit()
    return summary


def run_location_retention(db: Session, commit: bool = True) -> dict:
    """Delete raw GPS pings past the configured retention window (audit F-09).

    AI-CONTEXT: `purge_pings_older_than` had existed and been exported since F3 was
    written, and its only caller in the tree was a single test — so the retention PRD
    §7.3 calls "configurable" was enforced nowhere and `location_ping` grew without
    bound. The window itself is an F13 key, not a constant here: how long a product
    keeps a driver's movements is a policy decision, and the number that is right for
    it is not one an ingest runner should be asserting.

    Daily rather than hourly, and NOT batched. Both are the same argument: with a
    365-day default on a product whose oldest ping is weeks old, this deletes nothing
    for a year, so a chunking loop written now would be a year of untested code
    guarding a case nobody has measured. The day the window is shortened is the day to
    measure it — `deleted` is in the summary and lands in `f14.job_run`.
    """
    from app.foundation.f03_location import public as location
    from app.foundation.f05_load import public as loads

    summary = location.purge_expired_pings(db)
    # AI-CONTEXT: the arming reconcile PIGGYBACKS here rather than getting a job of its own
    # (F3-1). It is the same shape of work — a nightly janitor over F3's own tables — and a
    # second job would be a second thing to register, flag, lease and watch for one query.
    #
    # It is what makes production SELF-HEAL. Every box already carries an arming per stop
    # since the Foundation, and the wiring at `depart_stop` only fixes accounts that depart
    # a stop from now on; this reaches the ones that never will. Account-wide (`None`), so
    # a driver who has abandoned the app is covered too.
    summary["armings"] = location.reconcile_armings(db, loads.has_live_stop_at)
    if commit:
        db.commit()
    return summary
