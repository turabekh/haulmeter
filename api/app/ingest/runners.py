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
    BEFORE the broken one and the box reports data it is not running."""
    run = admin.start_job_run(db, job_name, datetime.now(UTC))
    try:
        snapshot = source() if callable(source) else source
        stats = work()
    except Exception as exc:
        admin.finish_job_run(db, run, datetime.now(UTC), ok=False, error=str(exc)[:500])
        db.flush()
        raise
    admin.finish_job_run(
        db,
        run,
        datetime.now(UTC),
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


def run_osm(db: Session, geojson_path: str, commit: bool = True) -> facility.IngestStats:
    def load():
        geojson = facility.ingest.read_geojson_file(geojson_path)
        return facility.ingest_records(db, facility.parse_osm(geojson), batch_id=_batch("osm"))

    stats = _record_load(db, "ingest_osm", lambda: _snapshot(geojson_path), load)
    if commit:
        db.commit()
    return stats


def run_document_expiry(db: Session, commit: bool = True) -> dict:
    """M5-FR3's unattended half. F6 computes what is due at 30/14/3; this is the
    caller F6 deliberately does not have, since a documents service should not know
    what a notification is."""
    from app.foundation.f08_notifications import public as notify
    from app.modules.m05_protection import public as m5

    gateway = notify.RecordingNotificationGateway()
    sent = m5.dispatch_expiry_reminders(db, gateway)
    if commit:
        db.commit()
    return {"considered": len(sent), "delivered": len(gateway.sent)}


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
    if commit:
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
