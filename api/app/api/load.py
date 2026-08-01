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

# which of a route's claim states a single summed figure should report. Declaration
# order, so `escalated` — the only one asking the driver to do something — wins.
_CLAIM_STATE_ORDER = {state: i for i, state in enumerate(m3.ClaimState)}

_GATEWAY = notify.RecordingNotificationGateway()  # F8 seam (dev)


class StopIn(BaseModel):
    """One confirmed stop of the route (§23 entry 68).

    Coordinates are required because the geofence is armed on them — a stop the driver
    could not place is a stop whose arrival can never be detected, so the import screen
    refuses to file it rather than inventing one.
    """

    facility_name: str
    lat: float
    lon: float
    # AI-CONTEXT: the address the driver CONFIRMED, kept (§23 entry 76). The sheet
    # collected it and geocoded it and then threw the string away, so every facility
    # this route created had `address` NULL — the seventh parsed value found reaching
    # no field. It is also why two same-named docks could not be told apart on the
    # very screen that asks "is this the same place?".
    address: str | None = None
    stop_type: str = "delivery"
    appointment: datetime | None = None
    appointment_end: datetime | None = None
    appointment_source: str | None = None
    facility_id: uuid.UUID | None = None
    create_new_facility: bool = False


class CreateLoadIn(BaseModel):
    facility_name: str
    lat: float
    lon: float
    address: str | None = None
    counterparty: str
    appointment: datetime | None = None
    # omit to use the live F13-config detention terms (default 2h free / $75/h)
    free_time_minutes: int | None = None
    rate_cents_per_hour: int | None = None
    # AI-CONTEXT: the sixth and seventh parsed values to reach no field (§23 entry 84).
    #
    # `Load.rate_cents` and `Load.accessorial_terms` are columns that have existed since
    # F5 was written, and `create_load_from_parsed_terms` has mapped both from a parsed
    # dict from the same day — but the only route that creates a load in production is
    # this one, and it never accepted them. So the linehaul rate and every contract term
    # the parse extracted were read off the paper, returned in the draft, rendered
    # nowhere and dropped.
    #
    # `accessorial_terms` arrives as the term->wording MAP the parse normalises to, not
    # the list the structured-output schema is forced to use — the schema's constraint
    # is F5's business and stops at its boundary.
    rate_cents: int | None = None
    accessorial_terms: dict | None = None
    # AI-CONTEXT: set when the driver confirmed a MATCHED facility on the rate-con
    # import screen. Without it this route called create_facility unconditionally, so
    # every load a driver filed added another row for a dock that was already in the
    # registry — and those duplicates are what M2's dwell history aggregates over.
    facility_id: uuid.UUID | None = None
    # what the terms came from, so the load records that it was read off a contract
    # rather than typed, and the wallet keeps the contract itself
    rate_con_document_id: uuid.UUID | None = None
    reference_number: str | None = None
    # where `appointment` came from: "rate_con_parse" when the driver confirmed the
    # parsed time unchanged, "manual" when they typed it. Ignored without an appointment.
    appointment_source: str | None = None
    # AI-CONTEXT: the driver answered "none of these" on the match screen (§23 entry 66).
    # Distinct from simply not choosing: a null `facility_id` means "no opinion", this
    # means "I looked at your candidates and this dock is not one of them."
    create_new_facility: bool = False
    # AI-CONTEXT: the ROUTE, when the driver confirmed more than one stop (§23 entry
    # 68). The flat fields above stay for the single-stop and manual paths — a driver
    # typing one dock into the fallback form should not have to describe a route — and
    # when `stops` is present it wins, in the order given.
    stops: list[StopIn] | None = None


def _resolve_facility(db: Session, body):
    """Reuse before create. `facility_id` is the confirmed match from the import
    screen; without one, fall back to the same name+geohash rule ingest already
    trusts to merge two records unattended — a dock at the same coordinates with
    a matching name is the same dock, however the driver got here.

    AI-CONTEXT: "none of these" is an ANSWER, and this route used to ignore it
    (§23 entry 66). The import screen asks "is this the same place?", and a driver who
    rejects every candidate sent exactly what a driver who never answered sent — no
    facility id — so the fallback below ran anyway and could attach the load to a dock
    they had just looked at and refused. Every load created in the sheet also shares
    one pair of coordinates, which makes the geohash half of that rule match far more
    than it should. A screen that asks a question and then overrides the answer is
    worse than one that never asked.

    The three cases are now distinct: a chosen id wins; an explicit rejection creates;
    silence still falls back to matching, which is right when nothing was ever asked —
    an unreadable rate con offers no candidates at all.
    """
    if body.facility_id is not None:
        existing = facility.get_facility(db, body.facility_id)
        if existing is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "facility not found")
        return existing
    address = getattr(body, "address", None)
    if body.create_new_facility:
        return facility.create_facility(
            db,
            facility.FacilityType.shipper_receiver,
            body.facility_name,
            body.lat,
            body.lon,
            address=address,
        )
    matches = facility.find_duplicate_candidates(db, body.facility_name, body.lat, body.lon)
    if matches:
        return matches[0]
    return facility.create_facility(
        db,
        facility.FacilityType.shipper_receiver,
        body.facility_name,
        body.lat,
        body.lon,
        address=address,
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
        # what the load PAYS, and the contract language a claim is argued from. M4's
        # `check_accessorial_terms` has read `load.accessorial_terms` since M4 shipped
        # and has therefore judged every load in production against an empty dict.
        rate_cents=body.rate_cents,
        accessorial_terms=body.accessorial_terms,
        detention_rate_cents_per_hour=rate,
        free_time_minutes=free_time,
        source=(
            loads.LoadSource.rate_con_parse
            if body.rate_con_document_id is not None
            else loads.LoadSource.manual
        ),
    )
    # AI-CONTEXT: one stop per confirmed row, IN ORDER (§23 entry 68). A rate con is a
    # route and this route used to build a single delivery from it, so a pickup and its
    # detention were discarded and §10.2's next-stop preview had nothing to preview.
    rows = body.stops or [
        StopIn(
            facility_name=body.facility_name,
            lat=body.lat,
            lon=body.lon,
            appointment=body.appointment,
            appointment_source=body.appointment_source,
            facility_id=body.facility_id,
            create_new_facility=body.create_new_facility,
        )
    ]
    stops = []
    for row in rows:
        row_fac = fac if row is rows[0] and body.stops is None else _resolve_facility(db, row)
        try:
            stop_type = loads.StopType(row.stop_type)
        except ValueError:
            stop_type = loads.StopType.delivery
        stop = loads.add_stop(
            db,
            load,
            row_fac.id,
            stop_type,
            appointment_start=row.appointment,
            appointment_end=row.appointment_end,
            free_time_minutes=free_time,
            detention_rate_cents_per_hour=rate,
            # M5-FR1's provenance belongs to the WINDOW. The client says where this one
            # came from, because only it knows whether the driver kept the parsed time
            # or typed their own over it — the load's `source` cannot tell them apart.
            appointment_source=row.appointment_source,
        )
        stops.append(stop)

    # ARM THE FIRST stop, not every one: arming opens an F4 evidence log and a live
    # geofence, and a driver is at one dock at a time. The rest arm as the load
    # advances — `active_stop_for_account` reads the most recent armed stop.
    stop = stops[0]
    loads.arm_stop(db, stop)  # opens the F4 evidence log + arms the F3 geofence
    # the rate con was photographed BEFORE this stop existed, so it was filed against
    # the account. Now that we know which stop it describes, attach it — otherwise the
    # contract and the load built from it have no link in either direction, and the
    # load's history cannot show the paper it came from.
    if body.rate_con_document_id is not None:
        rate_con = db.get(documents.Document, body.rate_con_document_id)
        if rate_con is not None and rate_con.account_id == account.id:
            documents.set_document_subject(db, rate_con, "stop", stop.id)
    # F14: North Star funnel step 1 — a live load exists (feeds /admin/analytics)
    admin.emit(db, "load_added", "m03", datetime.now(UTC), account_id=account.id)
    return {
        "load_id": str(load.id),
        "stop_id": str(stop.id),
        "stop_ids": [str(x.id) for x in stops],
    }


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
            "stops": [],
            "readable": False,
        }
    return {"document_id": str(document.id), **draft}


@router.get("/history")
def load_history(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """AI-CONTEXT: where a finished load goes.

    Nothing has ever asked this. `/load/active` returns the ONE armed stop and there
    was no other read, so a load that ended left no way back to itself — its evidence
    log, condition captures and stop-scoped BOL all still in the database with no route
    reaching them. An evidence pack is worth having precisely because it can be
    produced weeks later when a broker disputes it; unreachable the moment the driver
    taps "End load" is the opposite of that.

    Each row carries only what that load actually PRODUCED. A load that captured
    nothing says so — rendering empty money and evidence rows would read as data we
    lost rather than a quiet week.
    """
    rows = []
    for load in loads.list_loads(db, account.id):
        stops = loads.list_stops(db, load)
        if not stops:
            continue
        # AI-CONTEXT: a load is a ROUTE, and this row reports all of it (§23 entry 74).
        #
        # Every figure here was read off `stops[0]` alone. A pickup-and-delivery load
        # showed its PICKUP's facility name, its PICKUP's claim, its PICKUP's photos and
        # its PICKUP's documents, with no sign that a second stop existed — so a driver
        # who ran a two-stop load and recovered detention at both saw one of the two
        # amounts and had no way to tell it was one of two. Measured on a real load:
        # $83.67 shown against $271.43 actually claimed.
        #
        # Third time the same shape: the import learned routes (entry 68), the advance
        # learned routes (entry 69), and every read built before them still assumed one
        # stop. `stop_count` has been in this response since entry 68 and nothing has
        # ever rendered it, which is how the singular kept looking correct.
        first, last = stops[0], stops[-1]
        origin = facility.get_facility(db, first.facility_id)
        destination = facility.get_facility(db, last.facility_id)
        claims = [c for c in (m3.claim_for_stop(db, s.id) for s in stops) if c is not None]
        earned = [c for c in claims if c.amount_cents]
        docs = [d for s in stops for d in documents.documents_for_subject(db, "stop", s.id)]
        rows.append(
            {
                "load_id": str(load.id),
                "stop_id": str(first.id),
                "facility_name": origin.name if origin else None,
                # the far end of the route, and only when there IS one: a single-stop
                # load has no destination distinct from where it started
                "destination_name": (
                    destination.name if destination and len(stops) > 1 else None
                ),
                "reference_number": load.reference_number,
                "created_at": load.created_at.isoformat(),
                "status": load.status.value,
                "stop_count": len(stops),
                # money only when there is money: a load that ran clean owes nothing,
                # and a $0.00 row would read as a claim that failed
                "detention_cents": sum(c.amount_cents for c in earned) or None,
                # one state for a summed figure. Every stop on a load belongs to one
                # driver in one mode, so these agree in practice; where they do not it
                # is because one was escalated, which is the one a driver needs to see.
                "claim_state": (
                    max(earned, key=lambda c: _CLAIM_STATE_ORDER[c.state]).state.value
                    if earned
                    else None
                ),
                # AI-CONTEXT: what the DRIVER captured (§23 entries 48, 70).
                #
                # `arm_stop` opens a log for every stop, so "does a log exist" always
                # said yes — decoration. Entry 48 changed it to count what the log
                # CONTAINS, and entry 70 then began recording arrival, notice and
                # departure automatically, which made every load contain something and
                # re-broke it in the same direction: an indicator that can only answer
                # one way. It counts PHOTOS — the things a driver chose to capture.
                # The automatic trail is real evidence and lives in the timeline, where
                # it is read; documents are listed beside this on their own.
                #
                # The rule: everything EXCEPT the bare departure. Ending a load happens
                # on every load whatever the driver did, so counting it makes the
                # indicator unfalsifiable again. An arrival does not — it only exists
                # if the driver got there, which is exactly the question this answers.
                "evidence_count": sum(
                    1
                    for s in stops
                    for e in evidence.stop_evidence(db, s.id)["timeline"]
                    if e.get("event") != loads.EVENT_DEPARTED
                ),
                "documents": sorted({d.doc_type.value for d in docs}),
                # AI-CONTEXT: the route, reachable (§23 entry 78). The row links to
                # `stops[0]` and there was no other way in, so a driver who
                # photographed a pickup and a delivery had eight photos in the system
                # and could open four. The rolled-up totals fixed what the row SAYS;
                # this fixes what it can REACH, which was the half left undone.
                "stops": [
                    {
                        "stop_id": str(s.id),
                        "sequence": s.sequence,
                        "stop_type": s.stop_type.value,
                        "facility_name": (
                            f.name if (f := facility.get_facility(db, s.facility_id)) else None
                        ),
                        "detention_cents": (
                            c.amount_cents
                            if (c := m3.claim_for_stop(db, s.id)) and c.amount_cents
                            else None
                        ),
                        "claim_state": c.state.value if c else None,
                        "photo_count": m5.condition_photo_count(db, s.id),
                    }
                    for s in stops
                ],
            }
        )
    return {"loads": rows}


@router.get("/active")
def active_load(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # resume point: the driver's current armed stop (or null). Lets a fresh device
    # re-open The Meter without relying on client-persisted activeStopId.
    #
    # AI-CONTEXT: WHICH DOCK, not just which stop (§23 entry 82).
    #
    # §11.3 gives the map's Work preset as "armed stop + its facility intel" and §10.1
    # gives the facility sheet an "Arm stop" CTA — both of which need to know the
    # facility the armed stop is AT, and this route returned an opaque stop id. So the
    # Map tab could not tell the driver's own dock from any other receiver on the
    # screen, and the two surfaces that are about the same load knew nothing of each
    # other. The stop already carries `facility_id`; nothing had ever asked for it.
    stop = loads.active_stop_for_account(db, account.id)
    if stop is None:
        return {"stop_id": None, "facility_id": None, "facility_name": None}
    fac = facility.get_facility(db, stop.facility_id)
    return {
        "stop_id": str(stop.id),
        "facility_id": str(stop.facility_id),
        "facility_name": fac.name if fac else None,
    }


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
    # the arrival, in the chain: the pack used to say an event occurred and not which
    loads.record_stop_event(db, stop, loads.EVENT_ARRIVED, datetime.now(UTC))
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


class AppointmentIn(BaseModel):
    appointment: datetime
    appointment_end: datetime | None = None


@router.patch("/{stop_id}/appointment")
def correct_appointment(
    stop_id: uuid.UUID,
    body: AppointmentIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """M5-FR1's other half (§23 entry 62).

    FR1 shows the appointment window before arrival, with its provenance, so a driver
    can catch a MIS-PARSED time while they are still approaching and can still act on
    it. The screen showed it and then offered no way to fix it — so a wrong window
    stayed wrong, and the protection FR1 exists to give was a notification that
    something had already gone silently wrong.

    A correction is the driver's own account of the time, so the window's provenance
    becomes `manual`: the parse no longer gets the credit for a value it did not
    supply. F5 owns the field, which is why the write lives behind its public.
    """
    stop = _owned_stop(db, stop_id, account)
    loads.set_stop_appointment(db, stop, body.appointment, body.appointment_end)
    return {
        "stop_id": str(stop.id),
        "appointment": stop.appointment_start.isoformat(),
        "appointment_end": stop.appointment_end.isoformat() if stop.appointment_end else None,
        "appointment_source": stop.appointment_source,
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
    load = loads.get_load(db, stop.load_id)

    # AI-CONTEXT: THE ROUTE ADVANCES (§23 entry 69).
    #
    # Multi-stop loads arm only their first stop, because arming opens an F4 evidence
    # log and a live geofence and a driver is at one dock at a time — and nothing then
    # armed the next one. `active_stop_for_account` reads the most recent ARMED stop,
    # so departing the pickup left zero armed stops and the delivery sat `pending` and
    # unreachable: it existed in the database and no screen could open it. Leaving a
    # stop is not ending a load unless it was the last one.
    next_stop = None
    if load is not None:
        later = [
            s
            for s in loads.list_stops(db, load)
            if s.sequence > stop.sequence and s.status == loads.StopStatus.pending
        ]
        if later:
            next_stop = later[0]
            loads.arm_stop(db, next_stop)

    # ...and the LOAD reaches a terminal state, which nothing ever did before: every
    # load ever created sat in `draft` because `set_load_status` was never called from
    # anywhere, so "completed" could not be listed even by something that wanted to.
    if load is not None:
        loads.complete_load_if_finished(db, load)
    return {
        "stop_id": str(stop.id),
        "status": stop.status.value,
        "load_status": load.status.value if load else None,
        # the client switches to this rather than clearing the tab
        "next_stop_id": str(next_stop.id) if next_stop else None,
    }


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
    proof = m5.on_time_proof_for_stop(db, stop.id)
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
        # AI-CONTEXT: what the profit calculator needs to stop inventing (§23 entry 85).
        #
        # M8's calculator asks a driver to type a Rate the load already knows, and
        # defaults its receiver to the NIL UUID and its origin to a hardcoded Dallas —
        # so every "true profit" computed in production valued detention at a facility
        # that does not exist. The meter already returns this load's free time and
        # detention rate; these two are the rest of the same economics.
        "facility_id": str(stop.facility_id),
        "rate_cents": load.rate_cents if load else None,
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
        # A1 requirement 1: the capture checklist for THIS stop type, from F13 config.
        # `bol_captured` above is the one hardcoded row it replaces on the screen — a
        # DELIVERY needs a POD and has no seal to record, and asking for the wrong
        # artifact is how a checklist teaches a driver to ignore it.
        "checklist": m5.stop_checklist(db, stop),
        # M5-FR1: a driver can only protect themselves from a MIS-PARSED appointment
        # if they can see the window before they arrive AND tell whether a machine
        # read it. A value typed by hand carries different confidence from one an
        # OCR pass produced, and only the driver knows which is right.
        "appointment_end": stop.appointment_end.isoformat() if stop.appointment_end else None,
        "appointment_source": stop.appointment_source,
        # M5-FR1's VERDICT. It has been computed and stored on every arrival since FR1
        # shipped and reached no screen: the only place the API exposed it was the
        # `/arrive` response, which the Load tab discards, so a reload lost it. FR5's
        # protection summary counts four documented items and §10.2's checklist
        # rendered three — this is the fourth. `None` until the driver arrives.
        "on_time": proof.within_window if proof else None,
        "arrived_at": proof.checked_in_at.isoformat() if proof else None,
        # §10.2's anatomy ends with a next-stop preview and this tab has never had one.
        # `list_stops` has been ordered by sequence since F5 was written and nothing
        # asked it what comes after the dock the driver is standing at.
        "next_stop": _next_stop(db, load, stop),
    }


def _next_stop(db: Session, load, stop) -> dict | None:
    """The stop after this one, if the load has one. A driver deciding whether to wait
    out detention or leave is really asking what it costs them later, and the answer is
    the appointment they have to make next."""
    if load is None:
        return None
    later = [
        s
        for s in loads.list_stops(db, load)
        if s.sequence > stop.sequence and s.status != loads.StopStatus.canceled
    ]
    if not later:
        return None
    nxt = later[0]
    fac = facility.get_facility(db, nxt.facility_id)
    return {
        "facility_name": fac.name if fac else None,
        "stop_type": nxt.stop_type.value,
        "appointment": nxt.appointment_start.isoformat() if nxt.appointment_start else None,
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
    # photos (all F4 logs for the stop) + the paperwork attached to THIS STOP.
    #
    # AI-CONTEXT: it used to list the driver's whole WALLET — every CDL, medical card,
    # insurance certificate and rate con on the account — inside a record the next card
    # offers to "share with broker". The shared PDF never carried them (`compose_pack`
    # builds from the log's records and artifacts alone), so nothing leaked; what the
    # screen did was tell the driver their credentials were part of what a broker
    # receives. That is the wrong direction of wrong: it invites a driver to withhold a
    # legitimate claim to protect documents that were never going anywhere.
    stop = _owned_stop(db, stop_id, account)
    fac = facility.get_facility(db, stop.facility_id)
    docs = documents.documents_for_subject(db, "stop", stop.id)
    return {
        "stop_id": str(stop.id),
        "facility": fac.name if fac else None,
        "documents": [
            {"doc_type": d.doc_type.value, "uploaded_at": d.uploaded_at.isoformat()}
            for d in docs
        ],
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
    stop = _owned_stop(db, stop_id, account)
    claim = _claim_or_409(db, stop)
    now = datetime.now(UTC)
    message = m3.send_detention_start_notice(db, claim, _GATEWAY, now)
    # recorded only when one actually went out: "we told them at 10:05" is the fact a
    # dispute turns on, and logging an attempt that no-oped would assert it falsely
    if message is not None:
        loads.record_stop_event(db, stop, loads.EVENT_NOTICE_SENT, now)
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
