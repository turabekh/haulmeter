"""AI-CONTEXT: Active-load HTTP endpoints — the lifecycle behind The Meter (the
product's signature element, design-prd §9). Composes F2 (facility) + F5 (load/
stop) + F3 (geofence arrival) + M3 (detention clock): create a load and arm its
stop, record arrival (a geofence ENTER that starts the clock), and read the live
detention Meter. The client remembers its active stop_id and ticks the Meter
locally from `arrived_at`; this API is the source of truth for the terms + state.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f04_evidence import public as evidence
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
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
    fac = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, body.facility_name, body.lat, body.lon
    )
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
    load = loads.create_load(
        db,
        account.id,
        counterparty_id=cp.id,
        detention_rate_cents_per_hour=rate,
        free_time_minutes=free_time,
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
    # F14: North Star funnel step 2 — the driver reached the dock (clock started)
    admin.emit(db, "arrived", "m03", datetime.now(UTC), account_id=account.id)
    return {"claim_id": str(claim.id), "arrived": True}


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
    cp = loads.get_counterparty(db, loads.get_load(db, stop.load_id).counterparty_id)
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
