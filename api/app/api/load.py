"""AI-CONTEXT: Active-load HTTP endpoints — the lifecycle behind The Meter (the
product's signature element, design-prd §9). Composes F2 (facility) + F5 (load/
stop) + F3 (geofence arrival) + M3 (detention clock): create a load and arm its
stop, record arrival (a geofence ENTER that starts the clock), and read the live
detention Meter. The client remembers its active stop_id and ticks the Meter
locally from `arrived_at`; this API is the source of truth for the terms + state.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f04_evidence import public as evidence
from app.foundation.f05_load import public as loads
from app.foundation.f06_documents import public as documents
from app.foundation.f08_notifications import public as notify
from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f14_admin import public as admin
from app.modules.m03_detention import public as m3
from app.modules.m05_protection import public as m5

router = APIRouter(prefix="/load", tags=["load"])

_GATEWAY = notify.RecordingNotificationGateway()  # F8 seam (dev)


class CreateLoadIn(BaseModel):
    facility_name: str
    lat: float
    lon: float
    counterparty: str
    appointment: datetime | None = None
    # omit to use the live F13-config detention terms (default 2h free / $75/h)
    free_time_minutes: int | None = None
    rate_cents_per_hour: int | None = None
    # AI-CONTEXT: set when the driver confirmed a MATCHED facility on the rate-con
    # import screen. Without it this route called create_facility unconditionally, so
    # every load a driver filed added another row for a dock that was already in the
    # registry — and those duplicates are what M2's dwell history aggregates over.
    facility_id: uuid.UUID | None = None
    # what the terms came from, so the load records that it was read off a contract
    # rather than typed, and the wallet keeps the contract itself
    rate_con_document_id: uuid.UUID | None = None
    reference_number: str | None = None


def _resolve_facility(db: Session, body: CreateLoadIn):
    """Reuse before create. `facility_id` is the confirmed match from the import
    screen; without one, fall back to the same name+geohash rule ingest already
    trusts to merge two records unattended — a dock at the same coordinates with
    a matching name is the same dock, however the driver got here."""
    if body.facility_id is not None:
        existing = facility.get_facility(db, body.facility_id)
        if existing is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "facility not found")
        return existing
    matches = facility.find_duplicate_candidates(db, body.facility_name, body.lat, body.lon)
    if matches:
        return matches[0]
    return facility.create_facility(
        db, facility.FacilityType.shipper_receiver, body.facility_name, body.lat, body.lon
    )


def _owned_stop(db: Session, stop_id: uuid.UUID, account: identity.Account):
    # every stop-scoped action is gated to the load's owner: 404 if it doesn't
    # exist, 403 if it isn't the caller's (a driver only touches their own loads)
    stop = loads.get_stop(db, stop_id)
    if stop is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stop not found")
    load = loads.get_load(db, stop.load_id)
    if load is None or load.account_id != account.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your load")
    return stop


@router.post("", status_code=201)
def create_load(
    body: CreateLoadIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    fac = _resolve_facility(db, body)
    cp = loads.create_counterparty(db, body.counterparty, loads.CounterpartyKind.broker)
    # unset terms fall back to the live F13-config detention defaults (M3 owns them)
    free_time = (
        body.free_time_minutes
        if body.free_time_minutes is not None
        else m3.default_free_time_minutes(db)
    )
    rate = (
        body.rate_cents_per_hour
        if body.rate_cents_per_hour is not None
        else m3.default_rate_cents_per_hour(db)
    )
    # a load whose terms were read off a photographed contract records that it was —
    # `appointment_source` on the Meter payload is how M5-FR1 tells the driver whether
    # a machine read their appointment window or they typed it
    load = loads.create_load(
        db,
        account.id,
        counterparty_id=cp.id,
        reference_number=body.reference_number,
        detention_rate_cents_per_hour=rate,
        free_time_minutes=free_time,
        source=(
            loads.LoadSource.rate_con_parse
            if body.rate_con_document_id is not None
            else loads.LoadSource.manual
        ),
    )
    stop = loads.add_stop(
        db,
        load,
        fac.id,
        loads.StopType.delivery,
        appointment_start=body.appointment,
        free_time_minutes=free_time,
        detention_rate_cents_per_hour=rate,
    )
    loads.arm_stop(db, stop)  # opens the F4 evidence log + arms the F3 geofence
    # F14: North Star funnel step 1 — a live load exists (feeds /admin/analytics)
    admin.emit(db, "load_added", "m03", datetime.now(UTC), account_id=account.id)
    return {"load_id": str(load.id), "stop_id": str(stop.id)}


class ImportRateConIn(BaseModel):
    content_b64: str
    filename: str | None = None
    content_type: str | None = None


@router.post("/import", status_code=201)
def import_rate_con(
    body: ImportRateConIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """AI-CONTEXT: §10.2's empty state — "Add a load" by rate-con photo, which PRD
    §108 calls the PRIMARY way a load is created and which has never existed outside a
    test. F6 stores `rate_con`, F9 parses documents, `create_load_from_parsed_terms`
    takes the result — and the only place the three were ever joined was
    `tests/e2e/test_common_ground_e2e.py`. The Load tab offered a four-field manual
    form instead.

    It returns a DRAFT and creates nothing. M4-FR4 specifies a driver-confirm step,
    and that step is the point: a machine read of a photographed contract is a
    proposal, and only the driver can see both the paper and the screen. The rate con
    itself is filed to the wallet either way — the document is worth keeping even when
    the parse fails, because it is the contract the claim will be argued from.
    """
    import base64

    try:
        content = base64.b64decode(body.content_b64)
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unreadable upload") from exc

    document = m5.capture_document(
        db,
        account.id,
        "rate_con",
        content,
        filename=body.filename or "rate-con",
        content_type=body.content_type or "image/jpeg",
    )

    try:
        draft = loads.draft_from_rate_con(
            db,
            ai.resolve_provider(),
            document.content_hash,
            account_id=account.id,
            document_b64=body.content_b64,
            media_type=document.content_type,
        )
    except Exception:
        # The document is filed and the driver types the terms instead. This is the
        # honest failure: with no model key configured, or a rate con the parse cannot
        # read, inventing plausible terms would put a number the contract never
        # contained behind a detention claim.
        return {
            "document_id": str(document.id),
            "parsed": None,
            "silent_on": [],
            "facility_candidates": [],
            "readable": False,
        }
    return {"document_id": str(document.id), **draft}


@router.get("/active")
def active_load(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # resume point: the driver's current armed stop (or null). Lets a fresh device
    # re-open The Meter without relying on client-persisted activeStopId.
    stop = loads.active_stop_for_account(db, account.id)
    return {"stop_id": str(stop.id) if stop else None}


@router.post("/{stop_id}/arrive", status_code=201)
def arrive(
    stop_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    stop = _owned_stop(db, stop_id, account)
    fac = facility.get_facility(db, stop.facility_id)
    lat, lon = facility.coordinates(db, fac)
    # a geofence ENTER at the stop is the arrival the detention clock triggers on
    location.evaluate_ping(db, account.id, lat, lon, occurred_at=datetime.now(UTC))
    claim = m3.claim_for_stop(db, stop.id) or m3.start_claim(db, stop)
    # M5-FR1: the arrival that starts the detention clock IS the arrival that proves
    # the driver was on time, so the proof is filed here rather than on its own
    # geofence. The notice needs the load's opt-in; the artifact never does.
    proof = m5.auto_file_on_arrival(db, stop, account.id, gateway=_GATEWAY)
    # F14: North Star funnel step 2 — the driver reached the dock (clock started)
    admin.emit(db, "arrived", "m03", datetime.now(UTC), account_id=account.id)
    return {
        "claim_id": str(claim.id),
        "arrived": True,
        "on_time": proof.within_window,
        "notice_sent": proof.notice_sent,
    }


@router.post("/{stop_id}/end", status_code=201)
def end_load(
    stop_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # durable "end this load": mark the stop departed so /load/active stops
    # resurfacing it (ownership-checked — a driver only ends their own stop)
    stop = _owned_stop(db, stop_id, account)
    loads.depart_stop(db, stop, occurred_at=datetime.now(UTC))
    return {"stop_id": str(stop.id), "status": stop.status.value}


@router.get("/{stop_id}/meter")
def meter(
    stop_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    stop = _owned_stop(db, stop_id, account)
    fac = facility.get_facility(db, stop.facility_id)
    load = loads.get_load(db, stop.load_id)
    cp = loads.get_counterparty(db, load.counterparty_id) if load else None
    free_time, rate = loads.effective_detention_terms(db, stop)
    claim = m3.claim_for_stop(db, stop.id)
    arrived = location.is_present(db, account.id, stop.facility_id)
    # the clock snapshot (M3) lets the client reconstruct arrival and tick the
    # Meter locally each second without polling (design-prd §9).
    # once a pack is generated the claim leaves "open" — the Meter FREEZES at the
    # filed amount (§9), and stays frozen across navigations (state is on the claim)
    filed = claim is not None and claim.state.value != "open"
    phase = "not_arrived"
    free_remaining = None
    detention_seconds = 0
    detention_cents = 0
    if filed:
        phase = "accruing"
        free_remaining = 0
        detention_seconds = claim.detention_seconds
        detention_cents = claim.amount_cents
    elif claim is not None:
        state = m3.clock(db, claim, now=datetime.now(UTC))
        phase = state.phase.value
        free_remaining = state.free_time_remaining_seconds
        detention_seconds = state.detention_seconds
        detention_cents = state.amount_cents
    return {
        "stop_id": str(stop.id),
        "claim_id": str(claim.id) if claim else None,
        "facility_name": fac.name,
        "counterparty": cp.name if cp else None,
        "appointment": stop.appointment_start.isoformat() if stop.appointment_start else None,
        "arrived": arrived,
        "free_time_minutes": free_time,
        "rate_cents_per_hour": rate,
        "phase": phase,
        "free_time_remaining_seconds": free_remaining,
        "detention_seconds": detention_seconds,
        "detention_cents": detention_cents,
        "notice_sent": bool(claim is not None and claim.start_notice_sent_at is not None),
        "filed": filed,
        "photos_captured": m5.condition_photo_count(db, stop.id),
        # §10.2 specifies "photos 2/4". The denominator IS the feature: a bare count
        # cannot tell a driver whether they are finished, and FR5 exists to make a
        # gap visible while it can still be closed.
        "photos_required": len(m5.condition_sequence()),
        # the checklist rendered an unconditional tick for the BOL. A checklist that
        # always says yes is decoration.
        "bol_captured": m5.has_bol(db, stop.id),
        # M5-FR1: a driver can only protect themselves from a MIS-PARSED appointment
        # if they can see the window before they arrive AND tell whether a machine
        # read it. A value typed by hand carries different confidence from one an
        # OCR pass produced, and only the driver knows which is right.
        "appointment_end": stop.appointment_end.isoformat() if stop.appointment_end else None,
        "appointment_source": load.source.value if load is not None else None,
    }


@router.get("/{stop_id}/claim")
def claim_detail(
    stop_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # the filed claim's contents: the money, the terms, and the GPS-verified
    # evidence chain behind it (owner-gated, read-only)
    stop = _owned_stop(db, stop_id, account)
    claim = m3.claim_for_stop(db, stop.id)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no claim for this stop")
    load = loads.get_load(db, stop.load_id)
    cp = loads.get_counterparty(db, load.counterparty_id) if load and load.counterparty_id else None
    fac = facility.get_facility(db, stop.facility_id)
    return {
        "claim_id": str(claim.id),
        "amount_cents": claim.amount_cents,
        "detention_seconds": claim.detention_seconds,
        "free_time_minutes": claim.free_time_minutes,
        "rate_cents_per_hour": claim.detention_rate_cents_per_hour,
        "state": claim.state.value,
        "mode": claim.mode.value,
        "facility": fac.name if fac else None,
        "counterparty": cp.name if cp else None,
        "notice_sent": claim.start_notice_sent_at is not None,
        "filed": claim.state.value != "open",
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
        **m3.claim_evidence(db, claim),
    }


@router.get("/{stop_id}/evidence")
def evidence_detail(
    stop_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # everything captured for this load in one place: GPS timeline + cargo-condition
    # photos (all F4 logs for the stop) + the documents on file (owner-gated)
    stop = _owned_stop(db, stop_id, account)
    fac = facility.get_facility(db, stop.facility_id)
    docs = m5.wallet(db, account.id)["documents"]
    return {
        "stop_id": str(stop.id),
        "facility": fac.name if fac else None,
        "documents": [{"doc_type": d["doc_type"], "status": d["status"]} for d in docs],
        **evidence.stop_evidence(db, stop.id),
    }


@router.get("/{stop_id}/evidence/photo/{artifact_id}")
def evidence_photo(
    stop_id: uuid.UUID,
    artifact_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> Response:
    # serve the real captured image bytes for one evidence photo (owner-gated).
    # The artifact must belong to a log tied to THIS owned stop — no cross-load
    # peeking at another driver's evidence.
    stop = _owned_stop(db, stop_id, account)
    artifact = evidence.get_artifact(db, artifact_id)
    if artifact is None or not artifact.storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no image")
    log = db.get(evidence.EvidenceLog, artifact.log_id)
    if log is None or log.stop_ref != stop.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no image")
    try:
        data = documents.default_storage().get(artifact.storage_key)
    except Exception as exc:  # bytes missing (e.g. stored before MinIO wiring)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no image") from exc
    content_type = (artifact.exif or {}).get("content_type") or "image/jpeg"
    return Response(content=data, media_type=content_type)


def _claim_or_409(db: Session, stop) -> m3.DetentionClaim:
    claim = m3.claim_for_stop(db, stop.id)
    if claim is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "arrive first — no active claim")
    return claim


@router.post("/{stop_id}/notice", status_code=201)
def send_notice(
    stop_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # M3 counterparty notice — no-ops while still within free time (nothing owed yet)
    claim = _claim_or_409(db, _owned_stop(db, stop_id, account))
    message = m3.send_detention_start_notice(db, claim, _GATEWAY, datetime.now(UTC))
    return {"sent": message is not None}


@router.post("/{stop_id}/claim", status_code=201)
def generate_claim(
    stop_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # close the loop: the running clock -> a GPS-backed, filed detention claim
    claim = _claim_or_409(db, _owned_stop(db, stop_id, account))
    result = m3.generate_pack(db, claim, now=datetime.now(UTC), gateway=_GATEWAY)
    # F14: North Star funnel step 3 — the loop closes into a filed, GPS-backed claim
    admin.emit(db, "claim_sent", "m03", datetime.now(UTC), account_id=account.id)
    return {
        "claim_id": str(claim.id),
        "amount_cents": claim.amount_cents,
        "state": claim.state.value,
        "chain_valid": result["pack"].verification["chain_valid"],
        "receivable_ref": str(claim.receivable_ref) if claim.receivable_ref else None,
    }
