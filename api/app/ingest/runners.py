"""AI-CONTEXT: ingestion runners (composition layer — PRD §12). Compose the F2
pipeline (facilities) with F10 (authoritative belief) for TPIMS dynamic. Live HTTP
happens here, invoked from make targets / the worker — never from CI (tests drive
the pure adapters + pipeline against committed fixtures). Idempotent by design.
"""

import os
from datetime import UTC, datetime

from sqlalchemy import select
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


def run_arrival_reminders(db: Session, commit: bool = True) -> dict:
    """J1-D1's clock. The reminder fires at `appointment - lead` for an armed stop the
    driver is not already standing at.

    AI-CONTEXT: gated on `j1_arrival_nudge` inside `dispatch_arrival_reminders` rather
    than by the worker's own `flag_key`, so the job keeps ticking and reports zero while
    the flag is off. A job that does not run cannot be observed running, and the failure
    this class is most likely to have is silence — which looks identical to "the flag is
    off" from outside.

    Per-ACCOUNT gateway factory (entry 111): the scan crosses accounts and Web Push is
    addressed to one driver's own browsers.
    """
    from app.foundation.f08_notifications import public as notify
    from app.modules.m05_protection import public as m5

    sent = m5.dispatch_arrival_reminders(db, notify.gateway_for)
    if commit:
        db.commit()
    return {"reminders": len(sent)}


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


def run_outbound_mail(db: Session, commit: bool = True) -> dict:
    """Deliver counterparty mail. THE only thing that sends it (audit F-06 built the net).

    AI-CONTEXT: this used to be a retry net beside an inline send. It is now the send.

    `send_counterparty_message` opened an SMTP connection inside the request handler —
    measured at 2.5 s of connect/STARTTLS/AUTH against the configured provider before a
    byte of the notice moved, with a 10 s timeout, holding a POOLED DATABASE CONNECTION
    and a threadpool slot for the whole round trip. §23 records that exact outage
    ("QueuePool limit of size 5 overflow 10 reached"). The row was always the record that
    we DECIDED to send; now it is also the queue.

    Runs on the counterparty gateway rather than a per-driver one: this is outbound mail
    to a broker, not a push to a phone. Where SMTP is unconfigured the gateway falls back
    to recording, so a laptop exercises the sweep without sending anything.

    THE RECONCILE IS WHY THIS RETURNS WHAT IT RETURNS. `notice_delivery` records an
    "ACCEPTED ASYMMETRY": a message that succeeds on the sweep gains no `notice_sent`
    evidence record, because nothing re-enters M3's code path. That was tolerable while
    the sweep only caught rare failures. Now that it carries EVERY send, the same gap
    would strip "we notified the broker at 10:05" out of every detention pack — the line a
    dispute turns on. F8 cannot close it (it sits below the modules); this runner can, and
    does, because it may see both layers.
    """
    from app.foundation.f08_notifications import public as notify
    from app.modules.m03_detention import public as m3
    from app.modules.m05_protection import public as m5

    summary = notify.retry_unsent_messages(db, notify.counterparty_gateway())
    delivered = summary.pop("delivered", [])
    # both modules cache a "the counterparty was reached" fact that the request can no
    # longer write. Reported separately so a zero in either is visible rather than summed
    # away — M3's is the detention pack's evidence line, M5's is the on-time proof.
    summary["reconciled_notices"] = m3.reconcile_delivered_notices(db, delivered)
    summary["reconciled_on_time"] = m5.reconcile_on_time_notices(db, delivered)
    if commit:
        db.commit()
    return summary


def run_push_delivery(db: Session, commit: bool = True) -> dict:
    """Hand queued driver pushes to the push service.

    AI-CONTEXT: the push half of what `outbound_mail` does for counterparty email.
    `dispatch` called `send_push` inline — a POST per subscription with a ten-second
    timeout, once per browser the driver has, inside the request handler and holding a
    pooled database connection on a third party. §23 records that failure mode as an
    outage.

    SIXTY SECONDS, matching `outbound_mail` and `detention_clock`, because the P0 this
    carries is "free time has expired and your money is accruing". A minute late is
    honest; five would make the deadline notifications this exists for arrive after the
    driver has already pulled off the dock.

    Unflagged: this is delivery for notifications F8 has already DECIDED to send, with
    every §13.1 law — quiet hours, the interruption budget, DRIVING/RESTING — already
    applied at decision time. A flag nobody registered would mean no driver push leaves
    this box at all.
    """
    from app.foundation.f08_notifications import public as notify

    summary = notify.deliver_queued_notifications(db)
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


def run_image_thumbnails(db: Session, commit: bool = True, batch: int = 200) -> dict:
    """Derive a small JPEG for every stored image that does not have one yet.

    AI-CONTEXT: this job IS the backfill, and that is deliberate rather than lazy.

    Every existing row carries `thumbnail_state IS NULL`, which means "not reached yet",
    so the 89 evidence artifacts and 106 documents already on the dev box are simply the
    first few passes' worth of work. A separate one-shot script would be a second thing
    to write, run once, and never test again — and the shape it would have is exactly
    this loop. HANDOFF-121's N-03 is the warning: a migration and the code that needs it
    landing at different moments is how seven jobs ran against the wrong schema.

    BOUNDED PER PASS. A driver who photographs a whole route lands a few dozen rows at
    once, and decoding every image on the box in one transaction is how a five-minute
    janitor becomes an outage. `batch` is the ceiling and the remainder waits five
    minutes, which is invisible: nothing blocks on a thumbnail, the surfaces fall back to
    the original while it is missing.

    "none" IS A SUCCESS. A PDF rate con has no image to derive from, and recording that
    is what stops it being re-decoded forever. Only `failed` is worth retrying, and it is
    left NULL precisely so the next pass picks it up — a transient MinIO blip should heal
    itself, and it is the one case where doing nothing is the right record.
    """
    from app.foundation.f04_evidence import public as evidence
    from app.foundation.f06_documents import public as documents

    storage = documents.default_storage()
    made = 0
    skipped = 0
    failed = 0
    missing = 0

    def _derive(storage_key: str) -> str | None:
        """'ready' / 'none' / 'missing' / None, where None means 'try again next pass'."""
        nonlocal made, skipped, failed, missing
        try:
            original = storage.get(storage_key)
        except Exception as exc:
            # AI-CONTEXT: two failures that look alike and are opposites. An object that
            # is GONE will never appear, and re-reading it every five minutes forever is
            # what this job did on its first real run — 27 rows on the dev box point at
            # bytes lost in the era `main._wire_object_storage` describes. A store that
            # is briefly unreachable must heal instead, so it stays NULL and the next
            # pass picks it up.
            if documents.is_missing_object(exc):
                missing += 1
                return "missing"
            failed += 1
            return None
        thumb = documents.make_thumbnail(original)
        if thumb is None:
            skipped += 1
            return "none"
        try:
            storage.put(
                documents.thumbnail_key(storage_key), thumb, documents.THUMB_CONTENT_TYPE
            )
        except Exception:
            failed += 1
            return None
        made += 1
        return "ready"

    for model in (documents.Document, evidence.EvidenceArtifact):
        rows = db.scalars(
            select(model)
            .where(model.thumbnail_state.is_(None), model.storage_key.is_not(None))
            .limit(batch)
        ).all()
        for row in rows:
            state = _derive(row.storage_key)
            if state is not None:
                row.thumbnail_state = state

    if commit:
        db.commit()
    # `missing` is reported separately from `failed` on purpose: it is not this job
    # misbehaving, it is a count of stored records whose bytes are gone, and burying it
    # in a failure total is how that stops being visible to anyone.
    return {"made": made, "skipped": skipped, "failed": failed, "missing": missing}


def run_m14_poll(db: Session, commit: bool = True, client_factory=None) -> dict:
    """Poll every connected fleet's telematics provider once (M14-FR2, E2 slice 1).

    AI-CONTEXT: the flag gate is the WORKER's, not this function's — `Job("m14_poll",
    m14.FLAG_KEY, ...)` means an unregistered or disabled flag never reaches here. That is
    the established pattern and it matters more than usual for this job: it makes an
    outbound call to a third party on a fleet's credential, so "off" has to mean no
    packets leave the box at all.

    ONE CONNECTOR'S FAILURE DOES NOT STOP THE OTHERS. A revoked key at one fleet marks
    that connector `failing` with the provider's own words and the loop continues — the
    alternative is one fleet's expired token silently stopping every other fleet's
    detention evidence, which is the kind of shared-fate failure that is invisible until
    somebody asks why a claim never drafted.

    `client_factory` exists for `make m14-poll-once` and for tests; production passes
    nothing and `poll_connector` builds a real client from the decrypted key.
    """
    from app.modules.m14_recovery import public as m14

    connectors = m14.active_connectors(db)
    imported = duplicates = skipped = failed = 0
    events = 0
    for connector in connectors:
        client = client_factory(connector) if client_factory is not None else None
        try:
            result = m14.poll_connector(db, connector, client=client)
        except Exception:  # noqa: BLE001 — recorded on the row by `poll_connector`
            failed += 1
            continue
        imported += result.imported
        duplicates += result.duplicates
        skipped += result.skipped_unmapped
        events += len(result.events)
    if commit:
        db.commit()
    # `skipped_unmapped` is reported beside the rest rather than folded into it: it is the
    # number that explains a connected fleet drafting no claims, and burying it is how a
    # half-mapped fleet looks like a quiet one.
    return {
        "connectors": len(connectors),
        "imported": imported,
        "duplicates": duplicates,
        "skipped_unmapped": skipped,
        "events": events,
        "failed": failed,
    }
