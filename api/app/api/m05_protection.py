"""AI-CONTEXT: M5 Protection HTTP endpoints — thin over m05_protection.public.
Document wallet + inspection mode are reads; on-time proof / condition / incident
are captures (F4 evidence). F8 gateway seam (recording) in dev.
"""

import base64
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f04_evidence import public as evidence
from app.foundation.f05_load import public as loads
from app.foundation.f06_documents import public as documents
from app.foundation.f08_notifications import public as notify
from app.foundation.f12_offline import public as offline
from app.modules.m05_protection import public as m5

router = APIRouter(prefix="/protection", tags=["protection"])

_GATEWAY = notify.RecordingNotificationGateway()  # F8 seam (dev)


class OnTimeIn(BaseModel):
    stop_id: uuid.UUID
    checked_in_at: str  # ISO 8601
    notify_counterparty: bool = False


class IncidentIn(BaseModel):
    kind: str
    note: str | None = None


@router.post("/on-time", status_code=201)
def on_time(
    body: OnTimeIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    from datetime import datetime

    stop = loads.get_stop(db, body.stop_id)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stop not found")
    load = loads.get_load(db, stop.load_id)
    email = None
    if load is not None and load.counterparty_id is not None:
        cp = loads.get_counterparty(db, load.counterparty_id)
        email = cp.contact_email if cp is not None else None
    proof = m5.file_on_time_proof(
        db,
        stop,
        account.id,
        datetime.fromisoformat(body.checked_in_at),
        notify_counterparty=body.notify_counterparty,
        counterparty_ref=load.counterparty_id if load else None,
        counterparty_email=email,
        gateway=_GATEWAY,
    )
    return {
        "proof_id": str(proof.id),
        "within_window": proof.within_window,
        "notice_sent": proof.notice_sent,
    }


@router.get("/wallet")
def wallet(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    return m5.wallet(db, account.id)


@router.get("/inspection")
def inspection(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    return m5.inspection_mode(db, account.id)


@router.post("/incident", status_code=201)
def incident(
    body: IncidentIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None),
) -> dict:
    # F12: a key makes an offline-then-replayed incident create exactly one record
    result: dict = {}

    def _apply(_env):
        inc = m5.capture_incident(db, account.id, body.kind, note=body.note)
        result["incident_id"] = str(inc.id)
        result["evidence_log_ref"] = str(inc.evidence_log_ref)

    if idempotency_key:
        receipt = offline.ingest(
            db,
            account.id,
            idempotency_key,
            "incident",
            {"kind": body.kind},
            datetime.now(UTC),
            handler=_apply,
        )
        return {**result, "applied": receipt.applied}
    _apply(None)
    return {**result, "applied": True}


# --- Cargo-condition capture (M5-FR2): a guided, hash-chained photo sequence ---
class ConditionStartIn(BaseModel):
    stop_id: uuid.UUID
    phase: str = "delivery"  # pickup | delivery


@router.get("/condition/sequence")
def condition_sequence(
    account: identity.Account = Depends(current_account),
) -> list[str]:
    return m5.condition_sequence()


@router.post("/condition/start", status_code=201)
def condition_start(
    body: ConditionStartIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    stop = loads.get_stop(db, body.stop_id)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stop not found")
    phase = m5.CapturePhase(body.phase)
    capture = m5.start_condition_capture(db, stop, account.id, phase)
    return {"capture_id": str(capture.id), "sequence": m5.condition_sequence()}


class ConditionPhotoIn(BaseModel):
    prompt: str
    content_b64: str | None = None  # the captured image; a dev placeholder if absent
    content_type: str | None = None  # the image MIME type, so it serves back honestly


@router.post("/condition/{capture_id}/photo", status_code=201)
def condition_photo(
    capture_id: uuid.UUID,
    body: ConditionPhotoIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None),
) -> dict:
    capture = db.get(m5.ConditionCapture, capture_id)
    if capture is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "capture not found")
    if capture.account_id != account.id:
        # never let another account append to someone's evidence chain (tampering)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your capture")

    def _apply(_env):
        content = (
            base64.b64decode(body.content_b64)
            if body.content_b64
            else f"photo:{body.prompt}".encode()
        )
        m5.add_condition_photo(
            db, capture, body.prompt, content=content, content_type=body.content_type
        )

    # F12: an offline photo replayed with its key appends exactly once (no dup chain)
    applied = True
    if idempotency_key:
        receipt = offline.ingest(
            db,
            account.id,
            idempotency_key,
            "condition_photo",
            {"capture_id": str(capture_id), "prompt": body.prompt},
            datetime.now(UTC),
            handler=_apply,
        )
        applied = receipt.applied
    else:
        _apply(None)
    return {
        "capture_id": str(capture.id),
        "photo_count": capture.photo_count,
        "prompt": body.prompt,
        "applied": applied,
    }


@router.get("/summary/{stop_id}")
def summary(
    stop_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    stop = loads.get_stop(db, stop_id)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stop not found")
    load = loads.get_load(db, stop.load_id)
    if load is None or load.account_id != account.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your stop")
    return m5.protection_summary(db, stop)


# --- FR2/FR4 export + share (design-prd §17: one link, never an attachment) ---
class ShareIn(BaseModel):
    recipient: str | None = None


def _context_for(db: Session, kind: str, ref: uuid.UUID):
    """A condition report with no parties on it is a photo album. The clerk reading
    this did not take the pictures and needs to know whose load, whose dock and which
    reference before the images mean anything (§17)."""
    if kind != "condition":
        return evidence.PackContext()
    stop = loads.get_stop(db, ref)
    if stop is None:
        return evidence.PackContext()
    fac = facility.get_facility(db, stop.facility_id)
    load = loads.get_load(db, stop.load_id)
    references = [("Stop", str(stop.id)[:8])]
    if getattr(load, "reference_number", None):
        references.insert(0, ("Load", load.reference_number))
    if stop.appointment_start:
        references.append(("Appointment", stop.appointment_start.strftime("%Y-%m-%d %H:%M UTC")))
    return evidence.PackContext(
        parties=[("Facility", fac.name)] if fac is not None else [],
        references=references,
        facility_name=fac.name if fac is not None else None,
    )


def _pack_for(db: Session, account, kind: str, ref: uuid.UUID):
    """One resolver so export and share can never disagree about what a given id
    means — the two endpoints must produce the SAME document for the same input."""
    if kind == "condition":
        pack = m5.condition_pack(db, ref)
        if pack is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no condition capture for that stop")
        return pack
    incident = db.get(m5.Incident, ref)
    if incident is None or incident.account_id != account.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "incident not found")
    return m5.incident_pack(db, incident)


@router.get("/{kind}/{ref}/export")
def export_pack(
    kind: str,
    ref: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
):
    """The driver's own copy. Regenerated on demand because rendering is
    deterministic — this is a VIEW of the chain and always current, which is exactly
    what a share must not be."""
    if kind not in ("condition", "incident"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown pack kind")
    pack = _pack_for(db, account, kind, ref)
    content = m5.render_pack(db, pack, _context_for(db, kind, ref))
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{kind}-{str(ref)[:8]}.pdf"'},
    )


@router.post("/{kind}/{ref}/share", status_code=201)
def share(
    kind: str,
    ref: uuid.UUID,
    body: ShareIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """Pins what is being sent. From here the bytes are frozen: the chain may grow,
    and the link will keep serving the document the counterparty was actually
    given."""
    if kind not in ("condition", "incident"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown pack kind")
    pack = _pack_for(db, account, kind, ref)
    shared = m5.share_pack(
        db,
        pack.log_id,
        pack,
        account.id,
        recipient=body.recipient,
        context=_context_for(db, kind, ref),
    )
    return {
        "share_id": str(shared.id),
        # §17: counterparty mail is plain, short, professional, ONE link, no images
        "url": f"/pack/s/{shared.token}",
        "content_hash": shared.content_hash,
        "expires_at": shared.expires_at.isoformat() if shared.expires_at else None,
    }


@router.post("/share/{share_id}/extend")
def extend(
    share_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """A dispute outlives an AP cycle. The driver decides when their evidence stops
    being reachable, because they are the only party who knows the claim is still
    running (see f04 sharing for the cadence this was measured against)."""
    shared = db.get(evidence.SharedPack, share_id)
    if shared is None or shared.shared_by != account.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "share not found")
    evidence.extend_share(db, shared)
    return {
        "share_id": str(shared.id),
        "expires_at": shared.expires_at.isoformat() if shared.expires_at else None,
    }


@router.delete("/share/{share_id}")
def revoke(
    share_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    shared = db.get(evidence.SharedPack, share_id)
    if shared is None or shared.shared_by != account.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "share not found")
    evidence.revoke_share(db, shared)
    # the bytes and their hash survive: closing a link does not unsend a document
    return {"revoked": True, "content_hash": shared.content_hash}


# --- FR3: the wallet's writer (design-prd §8 camera capture) ---
class DocumentIn(BaseModel):
    doc_type: str
    content_b64: str
    filename: str | None = None
    content_type: str | None = None
    expires_on: str | None = None  # ISO date; meaningful only for credentials
    stop_id: uuid.UUID | None = None


@router.get("/documents/types")
def document_types(_account: identity.Account = Depends(current_account)) -> dict:
    """The capture screen offers only what the server will file, and says which of
    them an expiry date means anything for — a BOL does not expire."""
    return {"types": m5.DRIVER_DOC_TYPES, "expiring": m5.EXPIRING_DOC_TYPES}


@router.post("/documents", status_code=201)
def capture_document(
    body: DocumentIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None),
) -> dict:
    """The endpoint the Docs tab never had. Until this existed the wallet was a
    reader with no writer: a vendor could upload a licence through the portal and a
    driver could not upload their own CDL, so the tab was empty and F6's expiry
    engine had nothing to count down from."""
    from datetime import date as _date

    expires_on = None
    if body.expires_on:
        try:
            expires_on = _date.fromisoformat(body.expires_on)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "expiry must be an ISO date"
            ) from exc

    captured = {}

    def _apply(_env):
        try:
            doc = m5.capture_document(
                db,
                account.id,
                body.doc_type,
                base64.b64decode(body.content_b64),
                filename=body.filename,
                content_type=body.content_type,
                expires_on=expires_on,
                stop_ref=body.stop_id,
            )
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown document type"
            ) from exc
        captured["id"] = str(doc.id)

    # F12: a credential photographed in a dead zone replays exactly once
    applied = True
    if idempotency_key:
        receipt = offline.ingest(
            db,
            account.id,
            idempotency_key,
            "document_capture",
            {"doc_type": body.doc_type},
            datetime.now(UTC),
            handler=_apply,
        )
        applied = receipt.applied
    else:
        _apply(None)
    return {"document_id": captured.get("id"), "applied": applied}


@router.get("/documents/{document_id}")
def view_document(
    document_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
):
    """AI-CONTEXT: the bytes. Inspection mode's whole purpose is PRODUCING the
    credential, and until this existed the wallet could only show metadata — an
    officer asking for a CDL got a row reading "CDL · 2028-01-17", which is not a
    credential, it is our claim that the driver has one. Asserting on a driver's
    behalf to a police officer is the worst possible version of the honesty problem
    this product keeps solving elsewhere.

    F6 has had `get_document_bytes` since it was written and no route used it.

    Cached hard on purpose: a scale house is a dead zone, and a document that needs
    the network to render is a document you cannot produce when you are asked for it.
    The bytes are immutable — a document is replaced, never edited — so a long cache
    is safe as well as necessary.
    """
    doc = db.get(documents.Document, document_id)
    if doc is None or doc.account_id != account.id:
        # a stranger's document id must not be distinguishable from a missing one
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    try:
        content = documents.get_document_bytes(db, doc)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document unavailable") from exc
    return Response(
        content=content,
        media_type=doc.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{doc.filename or doc.doc_type.value}"',
            "Cache-Control": "private, max-age=31536000, immutable",
        },
    )


# --- FR1: the per-load opt-in (PRD §8.5 "opt-in per load") ---
class OnTimeConsentIn(BaseModel):
    load_id: uuid.UUID
    enabled: bool
    counterparty_email: str | None = None


@router.put("/on-time/consent")
def set_on_time_consent(
    body: OnTimeConsentIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """The choice has to survive the drive, so it is stored per load rather than
    passed per call. It gates the NOTICE only — the proof artifact is filed on every
    arrival, because a driver who declined to tell the broker still wants to be able
    to prove when they got there."""
    consent = m5.set_on_time_consent(
        db, account.id, body.load_id, body.enabled, body.counterparty_email
    )
    return {
        "load_id": str(consent.load_ref),
        "enabled": consent.enabled,
        "counterparty_email": consent.counterparty_email,
    }


@router.get("/on-time/consent/{load_id}")
def get_on_time_consent(
    load_id: uuid.UUID,
    _account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    consent = m5.on_time_consent(db, load_id)
    return {
        "load_id": str(load_id),
        # absence is not consent: no row means the notice does not go out
        "enabled": bool(consent and consent.enabled),
        "counterparty_email": consent.counterparty_email if consent else None,
    }
