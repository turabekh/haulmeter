"""AI-CONTEXT: M5 Protection & Document Wallet (PRD §8.5) — the shield to M3/M4's
sword. The same evidence engine pointed at protecting the driver: on-time proof
before anyone accuses them of being late, cargo condition before/after every
load, credentials one tap away and never silently expired. Composes foundation
publics only (F4 evidence, F5 stop, F6 documents, F8 notices); M5 owns its own
F4 logs so it never writes F5's tables. Runs behind the F13 flag m05_protection.
This is the App Store narrative for background location: continuous, visible
benefit.
"""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f04_evidence import public as evidence
from app.foundation.f06_documents import public as documents
from app.foundation.f08_notifications import public as notify

from .enums import CONDITION_SEQUENCE, INSPECTION_DOC_TYPES, CapturePhase
from .models import ConditionCapture, Incident, OnTimeProof

FLAG_KEY = "m05_protection"
MODULE = "m05"


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
):
    log = db.get(evidence.EvidenceLog, capture.evidence_log_ref)
    artifact = evidence.attach_artifact(
        db,
        log,
        evidence.ArtifactType.photo,
        content=content,
        content_hash=content_hash,
        exif={**(exif or {}), "prompt": prompt},
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        captured_at=captured_at,
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


def add_incident_photo(db: Session, incident: Incident, content: bytes, captured_at=None):
    log = db.get(evidence.EvidenceLog, incident.evidence_log_ref)
    return evidence.attach_artifact(
        db, log, evidence.ArtifactType.photo, content=content, captured_at=captured_at
    )


def incident_pack(db: Session, incident: Incident):
    log = db.get(evidence.EvidenceLog, incident.evidence_log_ref)
    return evidence.compose_pack(db, log, evidence.PackTemplate.cargo_condition)


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
