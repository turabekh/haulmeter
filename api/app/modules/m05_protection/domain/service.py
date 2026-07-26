"""AI-CONTEXT: M5 Protection & Document Wallet (PRD §8.5) — the shield to M3/M4's
sword. The same evidence engine pointed at protecting the driver: on-time proof
before anyone accuses them of being late, cargo condition before/after every
load, credentials one tap away and never silently expired. Composes foundation
publics only (F4 evidence, F5 stop, F6 documents, F8 notices); M5 owns its own
F4 logs so it never writes F5's tables. Runs behind the F13 flag m05_protection.
This is the App Store narrative for background location: continuous, visible
benefit.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.foundation.f04_evidence import public as evidence
from app.foundation.f06_documents import public as documents
from app.foundation.f08_notifications import public as notify

from .enums import CONDITION_SEQUENCE, INSPECTION_DOC_TYPES, CapturePhase
from .models import ConditionCapture, Incident, OnTimeConsent, OnTimeProof

FLAG_KEY = "m05_protection"
MODULE = "m05"
DEFAULT_PHOTO_CONTENT_TYPE = "image/jpeg"


def _persist_photo_bytes(
    log_id, content: bytes, content_type: str | None
) -> tuple[str, str] | None:
    # store the captured image bytes in F6 object storage (MinIO in dev) so the
    # Evidence view can serve a real thumbnail. Returns (storage_key, content_type)
    # or None if the store fails — capture never blocks on storage (the hash and
    # chain still record; the image is simply unavailable to serve).
    content_type = content_type or DEFAULT_PHOTO_CONTENT_TYPE
    key = f"evidence/{log_id}/{uuid.uuid4()}"
    try:
        documents.default_storage().put(key, content, content_type)
    except Exception:
        return None
    return key, content_type


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags
    from app.foundation.f14_admin import public as admin

    flags.register_flag(db, FLAG_KEY, description="M5 Protection & Document Wallet")
    admin.register_admin_view(db, "m05.protection", MODULE, "Protection", "/admin/m05/protection")


# --- On-time arrival proof (M5-FR1) ---
def file_on_time_proof(
    db: Session,
    stop,
    account_id,
    checked_in_at: datetime,
    notify_counterparty: bool = False,
    counterparty_ref=None,
    counterparty_email: str | None = None,
    gateway=None,
) -> OnTimeProof:
    deadline = stop.appointment_end or stop.appointment_start
    within = deadline is None or _as_utc(checked_in_at) <= _as_utc(deadline)

    log = evidence.create_log(db, account_id, stop_ref=stop.id, label="on-time-proof")
    evidence.append_record(
        db,
        log,
        evidence.RecordType.SYSTEM,
        {"event": "on_time_check", "within_window": within},
        occurred_at=checked_in_at,
    )

    notice_sent = False
    if notify_counterparty and within and gateway is not None:
        hhmm = _as_utc(checked_in_at).strftime("%H:%M")
        thread = notify.create_thread(
            db, account_id, subject="On-time arrival", counterparty_ref=counterparty_ref
        )
        notify.send_counterparty_message(
            db,
            thread,
            f"Driver checked in on time at {hhmm} per the appointment.",
            gateway,
            counterparty_email or "counterparty@unknown",
            now=checked_in_at,
        )
        notice_sent = True

    proof = OnTimeProof(
        account_id=account_id,
        stop_ref=stop.id,
        checked_in_at=checked_in_at,
        within_window=within,
        notice_sent=notice_sent,
        evidence_log_ref=log.id,
    )
    db.add(proof)
    db.flush()
    return proof


# --- Cargo-condition protocol (M5-FR2) ---
def condition_sequence() -> list[str]:
    return list(CONDITION_SEQUENCE)


def start_condition_capture(db: Session, stop, account_id, phase: CapturePhase) -> ConditionCapture:
    log = evidence.create_log(db, account_id, stop_ref=stop.id, label=f"condition-{phase.value}")
    capture = ConditionCapture(
        account_id=account_id, stop_ref=stop.id, phase=phase, evidence_log_ref=log.id
    )
    db.add(capture)
    db.flush()
    return capture


def condition_photo_count(db: Session, stop_ref) -> int:
    # total cargo-condition photos captured for a stop (across capture sessions) —
    # so the Load tab can confirm "Photos captured" instead of a static label
    total = db.scalar(
        select(func.coalesce(func.sum(ConditionCapture.photo_count), 0)).where(
            ConditionCapture.stop_ref == stop_ref
        )
    )
    return int(total or 0)


def add_condition_photo(
    db: Session,
    capture: ConditionCapture,
    prompt: str,
    content: bytes | None = None,
    content_hash: str | None = None,
    exif: dict | None = None,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    captured_at: datetime | None = None,
    content_type: str | None = None,
):
    log = db.get(evidence.EvidenceLog, capture.evidence_log_ref)
    meta = {**(exif or {}), "prompt": prompt}
    storage_key = None
    if content is not None:
        stored = _persist_photo_bytes(log.id, content, content_type)
        if stored is not None:
            storage_key, meta["content_type"] = stored
    artifact = evidence.attach_artifact(
        db,
        log,
        evidence.ArtifactType.photo,
        content=content,
        content_hash=content_hash,
        exif=meta,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        captured_at=captured_at,
        storage_key=storage_key,
    )
    capture.photo_count += 1
    db.flush()
    return artifact


# --- Document wallet + expiry (M5-FR3) ---
def wallet(db: Session, account_id, as_of: date | None = None) -> dict:
    as_of = as_of or datetime.now(UTC).date()
    docs, expiring = [], []
    for doc in documents.documents_for_account(db, account_id):
        status = "ok"
        if doc.expires_on is not None:
            if doc.expires_on < as_of:
                status = "expired"
            elif documents.active_reminder_offset(doc.expires_on, as_of) is not None:
                status = "expiring"
        row = {
            "id": str(doc.id),
            "doc_type": doc.doc_type.value,
            "expires_on": doc.expires_on.isoformat() if doc.expires_on else None,
            "status": status,
        }
        docs.append(row)
        if status in ("expiring", "expired"):
            expiring.append(row)
    return {"documents": docs, "expiring": expiring}


def inspection_mode(db: Session, account_id, as_of: date | None = None) -> list[dict]:
    return [
        d
        for d in wallet(db, account_id, as_of)["documents"]
        if d["doc_type"] in INSPECTION_DOC_TYPES
    ]


# --- Incident capture (M5-FR4) ---
def capture_incident(
    db: Session, account_id, kind: str, note: str | None = None, load_ref=None
) -> Incident:
    log = evidence.create_log(db, account_id, label=f"incident-{kind}")
    incident = Incident(
        account_id=account_id, load_ref=load_ref, kind=kind, note=note, evidence_log_ref=log.id
    )
    db.add(incident)
    db.flush()
    return incident


def add_incident_photo(
    db: Session,
    incident: Incident,
    content: bytes,
    captured_at=None,
    content_type: str | None = None,
):
    log = db.get(evidence.EvidenceLog, incident.evidence_log_ref)
    meta: dict = {}
    storage_key = None
    stored = _persist_photo_bytes(log.id, content, content_type)
    if stored is not None:
        storage_key, meta["content_type"] = stored
    return evidence.attach_artifact(
        db,
        log,
        evidence.ArtifactType.photo,
        content=content,
        captured_at=captured_at,
        exif=meta,
        storage_key=storage_key,
    )


def incident_pack(db: Session, incident: Incident):
    log = db.get(evidence.EvidenceLog, incident.evidence_log_ref)
    # an accident, a damage discovery or a dispute is not a cargo condition report,
    # and the template decides the title a clerk reads first
    return evidence.compose_pack(db, log, evidence.PackTemplate.incident)


# --- Protection summary per stop (M5-FR5) ---
def protection_summary(db: Session, stop) -> dict:
    on_time = db.scalar(select(OnTimeProof).where(OnTimeProof.stop_ref == stop.id)) is not None
    captures = list(
        db.scalars(select(ConditionCapture).where(ConditionCapture.stop_ref == stop.id))
    )
    pickup = any(c.phase == CapturePhase.pickup and c.photo_count > 0 for c in captures)
    delivery = any(c.phase == CapturePhase.delivery and c.photo_count > 0 for c in captures)
    documented = {"on_time_proof": on_time, "pickup_photos": pickup, "delivery_photos": delivery}
    missing = [k for k, ok in documented.items() if not ok]
    return {"documented": documented, "missing": missing}


# --- FR2/FR4 export + share (design-prd §17) ---
def condition_pack(db: Session, stop_ref, phase: CapturePhase | None = None):
    """FR2's "one-tap condition report". A stop's condition captures share one
    subject, so the export is per-STOP rather than per-capture session: a clerk
    asking "what did the trailer look like" wants pickup and delivery in one
    document, not two files to reconcile."""
    captures = list(
        db.scalars(
            select(ConditionCapture)
            .where(ConditionCapture.stop_ref == stop_ref)
            .order_by(ConditionCapture.created_at)
        )
    )
    if phase is not None:
        captures = [c for c in captures if c.phase == phase]
    if not captures:
        return None
    # one log per capture session; the newest carries the fullest picture of the
    # phase being exported, and every photo in it is chained to the same head
    log = db.get(evidence.EvidenceLog, captures[-1].evidence_log_ref)
    return evidence.compose_pack(db, log, evidence.PackTemplate.cargo_condition)


def _pack_images(db: Session, pack) -> dict:
    """Thumbnail bytes for the renderer, fetched HERE rather than inside F4 — the
    evidence engine does not reach into object storage mid-render, so a storage miss
    degrades to a labelled placeholder instead of taking the document down."""
    images = {}
    storage = documents.default_storage()
    for artifact in pack.artifacts:
        key = artifact.get("storage_key")
        if not key:
            continue
        try:
            images[artifact["content_hash"]] = storage.get(key)
        except Exception:
            continue
    return images


def render_pack(db: Session, pack, context=None):
    context = context or evidence.PackContext()
    if not context.images:
        context.images = _pack_images(db, pack)
    return evidence.render_pack_pdf(pack, context)


def share_pack(db: Session, log_ref, pack, account_id, recipient=None, now=None, context=None):
    """Render, pin, and hand back the record. The share is the moment the document
    stops being a view of the chain and becomes a thing that was SENT."""
    log = db.get(evidence.EvidenceLog, log_ref)
    content = render_pack(db, pack, context)
    return evidence.share_pack(
        db, log, pack.template, content, account_id, recipient=recipient, now=now
    )


# --- FR1: the per-load opt-in and the automatic filing ---
def set_on_time_consent(
    db: Session, account_id, load_ref, enabled: bool, counterparty_email: str | None = None
) -> OnTimeConsent:
    consent = db.scalar(select(OnTimeConsent).where(OnTimeConsent.load_ref == load_ref))
    if consent is None:
        consent = OnTimeConsent(account_id=account_id, load_ref=load_ref)
        db.add(consent)
    consent.enabled = enabled
    if counterparty_email is not None:
        consent.counterparty_email = counterparty_email
    db.flush()
    return consent


def on_time_consent(db: Session, load_ref) -> OnTimeConsent | None:
    return db.scalar(select(OnTimeConsent).where(OnTimeConsent.load_ref == load_ref))


def auto_file_on_arrival(db: Session, stop, account_id, arrived_at=None, gateway=None):
    """PRD §8.5 FR1: geofence ENTER inside the appointment window auto-fires the
    notice and files the proof. Runs on M3's existing arming — no new geofence
    machinery, because the arrival that starts the detention clock IS the arrival
    that proves you were on time.

    Two rules the wording of the FR implies and this makes explicit:

    · **The proof is filed on every arrival**, in or out of the window and opted in
      or not. It is the driver's own protection; someone who declined to notify the
      broker still wants to be able to prove when they got there.
    · **A late arrival notifies nobody.** The only notice this FR can send says the
      driver was on time, and sending that when they were not is the single thing it
      must never do. Silence is the honest outcome, and the artifact still exists.
    """
    arrived_at = arrived_at or datetime.now(UTC)
    existing = db.scalar(select(OnTimeProof).where(OnTimeProof.stop_ref == stop.id))
    if existing is not None:
        return existing  # one proof per stop; a re-arm is not a second arrival

    consent = on_time_consent(db, stop.load_id)
    wants_notice = bool(consent and consent.enabled)
    return file_on_time_proof(
        db,
        stop,
        account_id,
        checked_in_at=arrived_at,
        notify_counterparty=wants_notice,
        counterparty_email=consent.counterparty_email if consent else None,
        gateway=gateway if wants_notice else None,
    )
