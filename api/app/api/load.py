"""AI-CONTEXT: Active-load HTTP endpoints — the lifecycle behind The Meter (the
product's signature element, design-prd §9). Composes F2 (facility) + F5 (load/
stop) + F3 (geofence arrival) + M3 (detention clock): create a load and arm its
stop, record arrival (a geofence ENTER that starts the clock), and read the live
detention Meter. The client remembers its active stop_id and ticks the Meter
locally from `arrived_at`; this API is the source of truth for the terms + state.
"""

import math
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api import media
from app.api.deps import current_account, get_db
from app.api.m03_detention import already_filed
from app.api.uploads import read_upload
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

# AI-CONTEXT: the REAL counterparty transport (§23 entry 122). This was a recording
# gateway — an in-memory list — at every one of the seven send sites, so the F8 rows
# said the notice was sent and nothing ever left the box. Resolves SMTP-or-recording
# at send time, so the suite (SMTP_HOST blanked in conftest) and the app differ by
# configuration alone.
_GATEWAY = notify.counterparty_gateway()


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
    # AI-CONTEXT: where the broker's notices go, and until now there was NOWHERE to put it
    # (finding F4, and it is worse than the finding said).
    #
    # `create_counterparty` has accepted `contact_email` since F5 shipped and NOTHING in
    # the product ever passed one — not this route, the only route that creates a broker,
    # and no screen anywhere. So every counterparty a driver has ever created carries
    # NULL, and M3 addressed the literal `counterparty@unknown` instead. Against real SMTP
    # that is `SMTPRecipientsRefused`, which `PERMANENT_FAILURES` correctly never retries,
    # while the driver's screen said "Broker notified". The detention wedge could not
    # deliver to anybody, by construction.
    #
    # Optional, because a driver who does not have the AP address must still be able to
    # file a load and accrue the clock; the claim screen's `no_email` state is what says
    # the notice cannot go. The driver-facing INPUT is a named follow-up.
    counterparty_email: str | None = None
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
    try:
        email = loads.validate_contact_email(body.counterparty_email)
    except loads.InvalidContactEmail as exc:
        # a typo here is not cosmetic: a malformed address becomes SMTPRecipientsRefused,
        # which PERMANENT_FAILURES never retries, so the notice is lost for good
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    cp = loads.create_counterparty(
        db,
        body.counterparty,
        loads.CounterpartyKind.broker,
        contact_email=email,
    )
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
    # optional: multipart carries the bytes beside the fields rather than inside them
    content_b64: str | None = None
    filename: str | None = None
    content_type: str | None = None


@router.post("/import", status_code=201)
async def import_rate_con(
    request: Request,
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

    # AI-CONTEXT: multipart or the legacy base64 JSON (see `api/uploads.py`), and the
    # size ceiling now applies to both — a rate con arrives as a PDF from a desktop
    # scanner as often as a photograph, and neither had any limit.
    body, content = await read_upload(request, ImportRateConIn)
    if not content:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unreadable upload")

    # F9 reads the document as base64 whatever the wire format was, so it is encoded
    # once here rather than being required of the client.
    content_b64 = body.content_b64 or base64.b64encode(content).decode()

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
            document_b64=content_b64,
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


class ArriveIn(BaseModel):
    """The device's OWN fix, and the driver's answer to the too-far question.

    Every field is optional because the fallback must survive a phone with no fix at
    all — that is half of why this route exists — and an absent position is recorded as
    absent rather than substituted.
    """

    lat: float | None = None
    lon: float | None = None
    accuracy_m: float | None = None
    confirmed: bool = False


# AI-CONTEXT: a QUESTION threshold, not a fence. §23 entry 138.
#
# Deliberately far above F3's 150 m geofence radius, and the gap is the whole point: at a
# large DC the gate queue where detention actually begins can be most of a kilometre from
# the dock a pin sits on, and a driver waiting in it is legitimately arriving. A warning
# tuned to the geofence would fire on ordinary days, and a warning that fires on ordinary
# days is one drivers learn to tap through — which is worse than no warning, because the
# record would then show a confirmation that meant nothing.
#
# One kilometre is past any plausible yard or queue and well short of anything a correct
# arrival looks like. It exists to catch a mis-tap, a wrong address on the rate con, or a
# facility whose coordinates are bad — all three of which are real and none of which
# should stop the clock.
ARRIVAL_WARN_DISTANCE_M = 1000.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle metres. Local to this module on purpose: F3 owns geography for
    PostGIS containment, and this is one arithmetic question asked at one seam — routing
    it through the foundation would be a boundary crossing for four lines of trig."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@router.post("/{stop_id}/arrive", status_code=201)
def arrive(
    stop_id: uuid.UUID,
    body: ArriveIn | None = None,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """AI-CONTEXT: the manual arrival, told the truth about (§23 entry 138).

    THE DEFECT THIS REPLACES. This route used to call
    `evaluate_ping(db, account.id, lat, lon)` where `lat, lon` were **the facility's own
    coordinates**. So the position fix a detention claim rests on, on the path a driver
    takes precisely when the background sensor did not fire, was a reading of where the
    warehouse is — written into `location_ping` and counted by the pack's Location basis
    section among the driver's device fixes. That section tells a broker the records are
    "as reported by the driver's device". For this one it was not true.

    WHAT IS RECORDED NOW. The device's own fix, if it has one, with its accuracy and its
    distance from the facility. No fix is recorded as no fix and never filled in from the
    facility. The distance goes into the stop's hash chain either way, so a broker
    arguing about where the driver actually was is arguing with the record rather than
    with a number nobody wrote down.

    THE ARRIVAL STILL COUNTS FROM ANYWHERE, and that is deliberate. Detention frequently
    starts in a gate queue that is half a mile from the dock at a large DC; refusing the
    arrival would strand exactly the driver this button exists for. Past
    `ARRIVAL_WARN_DISTANCE_M` the route returns **409 with the distance** so the client
    can ask "are you sure", and a caller that says `confirmed` proceeds. The warning is a
    question, never a gate.
    """
    stop = _owned_stop(db, stop_id, account)
    fac = facility.get_facility(db, stop.facility_id)
    lat, lon = facility.coordinates(db, fac)
    now = datetime.now(UTC)
    device_lat = body.lat if body is not None else None
    device_lon = body.lon if body is not None else None
    accuracy_m = body.accuracy_m if body is not None else None
    confirmed = bool(body.confirmed) if body is not None else False

    distance_m = None
    if device_lat is not None and device_lon is not None:
        distance_m = _haversine_m(device_lat, device_lon, lat, lon)
        if distance_m > ARRIVAL_WARN_DISTANCE_M and not confirmed:
            # 409 rather than 400: the request is well-formed and the state is the
            # problem. The body carries what the driver needs to answer the question.
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "reason": "too_far",
                    "distance_m": round(distance_m),
                    "facility_name": fac.name if fac is not None else None,
                },
            )

    # the arrival, as the driver's ATTESTATION rather than as a manufactured reading.
    # `assert_presence` opens the visit — which is what `is_present` reads and what starts
    # the clock — and emits a GeofenceEvent only where there is a real position to put in
    # it. Nothing is written to `location_ping`.
    location.assert_presence(db, account.id, stop.facility_id, now, device_lat, device_lon)
    # the arrival, in the chain: the pack used to say an event occurred and not which.
    # The extras ride into the hash-chained record, so where the driver said they were is
    # part of the evidence rather than a fact the product declined to write down.
    loads.record_stop_event(
        db,
        stop,
        loads.EVENT_ARRIVED,
        now,
        presence_basis="device_fix" if distance_m is not None else "no_fix",
        arrival_lat=device_lat,
        arrival_lon=device_lon,
        arrival_accuracy_m=accuracy_m,
        distance_from_facility_m=round(distance_m) if distance_m is not None else None,
        far_from_facility=bool(distance_m is not None and distance_m > ARRIVAL_WARN_DISTANCE_M),
    )
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


class CounterpartyEmailIn(BaseModel):
    # null clears the address on file, which is a legitimate thing to ask for
    email: str | None = None


def _owned_load(db: Session, load_id: uuid.UUID, account: identity.Account):
    load = loads.get_load(db, load_id)
    if load is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "load not found")
    if load.account_id != account.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your load")
    return load


@router.patch("/{load_id}/counterparty-email")
def set_counterparty_email(
    load_id: uuid.UUID,
    body: CounterpartyEmailIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """Where this load's detention notices go.

    AI-CONTEXT: the missing half of the previous session's finding. `contact_email` has
    been on the counterparty since F5 shipped and NOTHING ever wrote it, so every notice
    this product has sent was addressed to an invented literal. Collecting it at load
    creation covers new loads; this covers the one a driver is standing in front of when
    the claim screen tells them the address is missing.

    `copied` is in the response because the caller cannot infer it: under the
    copy-on-write rule the load's counterparty id CHANGES, and a client holding the old
    one would show a stale address. See `set_load_counterparty_email`.
    """
    load = _owned_load(db, load_id, account)
    try:
        email = loads.validate_contact_email(body.email)
        counterparty, copied = loads.set_load_counterparty_email(db, load, email)
    except loads.InvalidContactEmail as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return {
        "load_id": str(load.id),
        "counterparty_id": str(counterparty.id),
        "counterparty": counterparty.name,
        "counterparty_email": counterparty.contact_email,
        "copied": copied,
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
    now = datetime.now(UTC)
    # AI-CONTEXT: A1 — leaving by HAND drafts the packet, exactly as leaving by
    # geofence does (location.py's EXIT carve-out).
    #
    # Only the F3 EXIT drafted it before this. §15.5's rule is "build for auto, degrade
    # to one-tap, never to nothing", and the background sensor this rides on is the one
    # mechanism v2.0 DoD #8 records as UNPROVEN — so the fallback path was the one that
    # had to work, and it produced no paperwork at all. Worse, it could not be recovered
    # afterwards: `depart_stop` below ends the stop's armed life, and
    # `draft_stop_packet_on_exit` finds the driver's stop through
    # `active_stop_for_account`, so a later ping had nothing left to draft against.
    #
    # BEFORE the departure, for that reason. Idempotent either way — one stop is one
    # document, so a driver whose geofence already fired gets no second packet.
    m5.draft_stop_packet_on_exit(db, account.id, stop.facility_id, now)
    loads.depart_stop(db, stop, occurred_at=now)
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
        # AI-CONTEXT: the address, and the load to PATCH it on. The claim screen tells the
        # driver to add a broker email when it is missing; it cannot offer the fix without
        # knowing which load owns the counterparty.
        "load_id": str(load.id) if load else None,
        "counterparty_email": cp.contact_email if cp else None,
        "appointment": stop.appointment_start.isoformat() if stop.appointment_start else None,
        "arrived": arrived,
        "free_time_minutes": free_time,
        "rate_cents_per_hour": rate,
        "phase": phase,
        "free_time_remaining_seconds": free_remaining,
        "detention_seconds": detention_seconds,
        "detention_cents": detention_cents,
        "notice_sent": bool(claim is not None and claim.start_notice_sent_at is not None),
        # finding F5: `notice_sent` is one bit and delivery has five states. A driver whose
        # notice bounced saw exactly what a driver who never tapped Send saw.
        "notice_delivery": m3.notice_delivery(db, claim) if claim else "not_sent",
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
        # AI-CONTEXT: the address, and the load to PATCH it on. The claim screen tells the
        # driver to add a broker email when it is missing; it cannot offer the fix without
        # knowing which load owns the counterparty.
        "load_id": str(load.id) if load else None,
        "counterparty_email": cp.contact_email if cp else None,
        "notice_sent": claim.start_notice_sent_at is not None,
        "notice_delivery": m3.notice_delivery(db, claim),
        # D8: the claim screen lists the links handed out for this log, and needs its id
        "evidence_log_ref": str(claim.evidence_log_ref) if claim.evidence_log_ref else None,
        "filed": claim.state.value != "open",
        "created_at": claim.created_at.isoformat() if claim.created_at else None,
        **m3.claim_evidence(db, claim),
    }


@router.get("/{load_id}/record")
def load_record(
    load_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """AI-CONTEXT: what a finished load's record CONTAINS, before it is downloaded or
    sent (owner request, 2026-08-11).

    Past loads offered exactly two things: open one stop's evidence, or "Export whole
    load" — a PDF download, blind. A driver could send nothing and could only see the
    document by first putting it on their phone. `load_pack` composes every stop's
    photos into one document and `/protection/load/{id}/share` has always accepted
    `kind="load"`, so **the whole-load pack could always be emailed and nothing ever
    called it** — the same built-and-inert shape HANDOFF-122 names, an eighth time.

    THIS IS A READ OF THE SAME SOURCE THE PACK IS BUILT FROM. `load_pack` groups by
    stop over `stop_evidence`; so does this. If the two ever disagree, the screen is
    lying about what the broker will receive, which is the one thing this endpoint
    exists to prevent — so the grouping and the ordering are deliberately identical
    rather than re-derived.

    The counterparty rides along because the send needs a default recipient, and
    HANDOFF-122 §3 means it is very often NULL — the screen has to be able to say so
    before the driver taps Send rather than after.
    """
    load = loads.get_load(db, load_id)
    if load is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "load not found")
    if load.account_id != account.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your load")
    stops = loads.list_stops(db, load)
    cp = (
        loads.get_counterparty(db, load.counterparty_id)
        if load.counterparty_id is not None
        else None
    )
    out_stops = []
    for stop in stops:
        fac = facility.get_facility(db, stop.facility_id)
        ev = evidence.stop_evidence(db, stop.id)
        claim = m3.claim_for_stop(db, stop.id)
        out_stops.append(
            {
                "stop_id": str(stop.id),
                "sequence": stop.sequence,
                "stop_type": stop.stop_type.value,
                "facility_name": fac.name if fac is not None else None,
                "detention_cents": claim.amount_cents if claim and claim.amount_cents else None,
                # the photos THEMSELVES, so the screen can show what was captured
                # rather than a count. `stop_evidence` already serialises these (ids
                # stringified, timestamps isoformatted), so they pass through —
                # re-converting here is how the two views start to disagree about the
                # same artifact. They now carry their own signed URLs, for the same
                # reason and by the same helper as the per-stop evidence screen: a whole
                # route's contact sheet is the worst case this exists for, and it was
                # fetching every full-size photograph of every stop, one at a time.
                "photos": _with_media_urls(ev.get("photos", [])),
                "document_types": sorted(
                    {d.doc_type.value for d in documents.documents_for_subject(db, "stop", stop.id)}
                ),
                # the GPS trail, as a COUNT of what the chain holds for this dock. The
                # events themselves are the per-stop evidence screen's job; here the
                # question is only "is the arrival in this document".
                "gps_events": sum(
                    1 for e in ev.get("timeline", []) if e.get("type") == "GEOFENCE"
                ),
                # §11.7: the integrity of what is about to be sent, stated. A pack that
                # fails its own verification cannot be shared (evidence-integrity
                # session), so a driver must learn that here and not from a refused tap.
                "chain_valid": bool(ev.get("chain_valid", True)),
            }
        )
    claims = [c for c in (m3.claim_for_stop(db, s.id) for s in stops) if c is not None]
    earned = [c for c in claims if c.amount_cents]
    return {
        "load_id": str(load.id),
        "reference_number": load.reference_number,
        "created_at": load.created_at.isoformat(),
        "status": load.status.value,
        "origin_name": (
            f.name if stops and (f := facility.get_facility(db, stops[0].facility_id)) else None
        ),
        "destination_name": (
            f.name
            if len(stops) > 1 and (f := facility.get_facility(db, stops[-1].facility_id))
            else None
        ),
        "stop_count": len(stops),
        "counterparty_name": getattr(cp, "name", None),
        "counterparty_email": getattr(cp, "contact_email", None),
        "detention_cents": sum(c.amount_cents for c in earned) or None,
        "claim_state": (
            max(earned, key=lambda c: _CLAIM_STATE_ORDER[c.state]).state.value if earned else None
        ),
        "photo_count": sum(len(s["photos"]) for s in out_stops),
        "document_types": sorted({d for s in out_stops for d in s["document_types"]}),
        "gps_events": sum(s["gps_events"] for s in out_stops),
        "chain_valid": all(s["chain_valid"] for s in out_stops),
        "stops": out_stops,
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
    detail = evidence.stop_evidence(db, stop.id)
    _attach_media_urls(detail.get("photos", []))
    return {
        "stop_id": str(stop.id),
        "facility": fac.name if fac else None,
        "documents": [
            {"doc_type": d.doc_type.value, "uploaded_at": d.uploaded_at.isoformat()}
            for d in docs
        ],
        **detail,
    }


# AI-CONTEXT: the URLs the contact sheets put straight into an `<img src>`.
#
# Minted HERE rather than in `f04_evidence`, because the foundation must not reach up into
# the API layer to learn how a route is addressed — and minted at all because an `<img>`
# cannot send an Authorization header, which is the single constraint that made the read
# path slow (no lazy-load, no progressive decode, every byte through JS memory).
#
# Ownership is checked by the endpoint that calls this, once, for the whole set; the
# signature then carries that decision to the browser. See `api/media.py`.
def _attach_media_urls(photos: list[dict]) -> None:
    for photo in photos:
        if not photo.get("has_image") or not photo.get("artifact_id"):
            continue
        ref = photo["artifact_id"]
        photo["thumb_url"] = media.media_url(media.KIND_EVIDENCE, ref, media.SIZE_THUMB)
        # AI-CONTEXT: NO `full_url`. It was minted here beside the thumbnail and read by
        # NOTHING — the ninth built-and-inert mechanism in this codebase's tally, created
        # in the same session that quotes HANDOFF-122's warning about them.
        #
        # It is not free to leave: every photo in every contact sheet carried a second
        # signed capability granting full-resolution access, minted on every render, for a
        # reader that does not exist. Opening a photograph full-size is a real feature and
        # a real design question (§8 says nothing about a lightbox), so it comes back with
        # the surface that needs it — `media.SIZE_FULL` already works and is tested.


def _with_media_urls(photos: list[dict]) -> list[dict]:
    _attach_media_urls(photos)
    return photos


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


class NoticeIn(BaseModel):
    # AI-CONTEXT: the driver saying "send it again anyway". A delivered notice is the
    # dispute anchor and the five-case rule refuses to re-send it — correctly — but "the
    # broker says they never got it" is real, and the answer to it was a button that ran
    # and changed nothing. A forced send delivers a copy and leaves the anchor alone.
    force: bool = False


@router.post("/{stop_id}/notice", status_code=201)
def send_notice(
    stop_id: uuid.UUID,
    body: NoticeIn | None = None,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # AI-CONTEXT: PHASE-AWARE (finding F7). `send_pre_detention_notice` — M3-FR3's "free
    # time is nearly up" warning to the broker — was written, exported, unit-tested and
    # called by NOTHING. The driver's own 30-minute warning has been wired since entry 106;
    # the broker's half of the same moment never was, so the one notice that can still
    # change the outcome (a dock that hurries when told the clock is about to start) was
    # never sent by this product.
    #
    # DRIVER-INITIATED, not automatic, and that is the whole reason it lives on this
    # endpoint rather than in the worker beside `dispatch_clock_alerts`. Mail to a third
    # party should not leave without a human act — the shipped start notice already set
    # that precedent, and a warning that fires itself would put us in a broker's inbox for
    # every stop that ran long, which is how a driver gets a reputation they did not choose.
    #
    #   more than 30 min left -> the existing "too early" no-op
    #   30 min or less        -> the WARNING, once
    #   free time exhausted   -> the start notice, exactly as before
    stop = _owned_stop(db, stop_id, account)
    claim = _claim_or_409(db, stop)
    now = datetime.now(UTC)
    message = m3.send_pre_detention_notice(db, claim, _GATEWAY, now)
    warned = message is not None
    # AI-CONTEXT: which message the claim was linked to BEFORE this call is what makes
    # "did we just send one?" answerable. D2 returns the EXISTING message for a notice
    # that has already been delivered or is queued for retry — so `message is not None`
    # no longer means a send happened here, and conditioning the evidence record on it
    # appended a second `notice_sent` for one stop the moment a request was replayed.
    # A fresh send always relinks the claim; nothing else does.
    linked_before = claim.start_notice_message_ref
    force = bool(body and body.force)
    if message is None:
        message = m3.send_detention_start_notice(db, claim, _GATEWAY, now, force=force)
    fresh = message is not None and (warned or message.id != linked_before)
    # AI-CONTEXT: finding F5 — this comment used to describe exactly this behaviour while
    # the line under it did something else. It read `if message is not None`, and
    # `send_counterparty_message` returns a message row for a FAILED send too (that is the
    # F-06 contract: a gateway may never fail its caller, the ref carries the outcome). So
    # every SMTP failure appended `notice_sent` to the hash-chained evidence log and told
    # the driver the broker had been notified.
    #
    # `sent_at` is the only thing that means it went out. A record that goes into a legal
    # pack has to be conditioned on the fact, not on the attempt.
    sent = message is not None and message.sent_at is not None
    # ...and ONLY the start notice is that record. `notice_sent` means "the broker was told
    # the clock had started"; a warning that it is about to start is a different fact, and
    # filing it under this one would put a claim in the pack that nothing supports (F7).
    if sent and fresh and not warned:
        loads.record_stop_event(db, stop, loads.EVENT_NOTICE_SENT, now)
    # the WARNING's delivery is that message's own; the claim's `notice_delivery` tracks
    # the start notice, which this stop has not sent yet
    delivery = m3.delivery_of(message) if warned else m3.notice_delivery(db, claim)
    # AI-CONTEXT: `already_sent` is what stops this being a dead control. Without a force,
    # a notice the broker already has returns the EXISTING message — the route reported the
    # same `delivery` a real send reports, so the driver could not tell a send from a no-op.
    already_sent = (
        not force
        and not warned
        and message is not None
        and message.id == linked_before
    )
    return {
        "sent": sent,
        "delivery": delivery,
        "phase": "warning" if warned else "start",
        "already_sent": already_sent,
        "forced": force,
    }


@router.post("/{stop_id}/claim", status_code=201)
def generate_claim(
    stop_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # close the loop: the running clock -> a GPS-backed, filed detention claim
    claim = _claim_or_409(db, _owned_stop(db, stop_id, account))
    try:
        result = m3.generate_pack(db, claim, now=datetime.now(UTC), gateway=_GATEWAY)
    except m3.EvidenceCheckFailed as exc:
        # finding F4-3: the pack's own verification failed, so F4 refused to pin, link or
        # send it. 409 rather than 500 — the request is fine, the evidence is not — and the
        # claim stays OPEN so the driver's money is still claimable.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "error": "evidence_check_failed",
                "reason": exc.verification.reason if exc.verification else None,
            },
        ) from exc
    except m3.ClaimAlreadyFiled as exc:
        # a retry after a success is not a failure — 409 carries the first filing's
        # receivable so the client reads it as "already filed" (finding F2)
        raise already_filed(exc) from exc
    # F14: North Star funnel step 3 — the loop closes into a filed, GPS-backed claim
    admin.emit(db, "claim_sent", "m03", datetime.now(UTC), account_id=account.id)
    return {
        "claim_id": str(claim.id),
        "amount_cents": claim.amount_cents,
        "state": claim.state.value,
        "chain_valid": result["pack"].verification["chain_valid"],
        "receivable_ref": str(claim.receivable_ref) if claim.receivable_ref else None,
    }
