"""AI-CONTEXT: M13 Vendor Network HTTP endpoints — thin over m13_vendor.public.

Driver side: the bbox feed behind the map's food badge, the vendor sheet, and
presence/sold-out confirmation into the F10 belief pipeline. Vendor side: profile
and appearance management (the vendor PORTAL is Session B; these are the API it
will sit on). Admin vendor moderation lives on the F14 console router.

Every response separates a CROWD reading from the VENDOR's own claim (`source`),
because the UI must never render "N drivers" for something a vendor said (§11.7).

PHASE A: no order, payment, or checkout endpoint exists here.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import canonical_facility_id, current_account, get_db, require_any_module
from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility_registry
from app.foundation.f08_notifications import public as notify
from app.foundation.f14_admin import public as admin
from app.modules.m13_vendor import public as m13

router = APIRouter(prefix="/vendors", tags=["vendors"],
    # PRD §6 / A6 req 1: the module's flags, plural. The router admits if EITHER half
    # is live and every route below names the half it belongs to (§23 entry 105).
    dependencies=[Depends(require_any_module(m13.FLAG_KEY, m13.SERVICE_CENTER_FLAG_KEY))],
)

# how many reviews ride on the sheet payload; the rest are a paging concern for a
# later session. A phone at 360 dp cannot usefully render more in one sheet anyway.
REVIEW_PAGE = 10


class OfferingIn(BaseModel):
    name: str
    price_cents: int
    portions: int | None = None


class VendorIn(BaseModel):
    name: str
    vendor_type: str = m13.VendorType.food_mobile.value
    metro: str = ""
    contact_phone: str | None = None
    categories: list[str] = []
    languages: list[str] = []
    halal_disclosure: str | None = None
    halal_answered: bool = False


class AppearanceIn(BaseModel):
    facility_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    offerings: list[OfferingIn]
    property_approved: bool = False
    weekly: list[int] | None = None


class ConfirmIn(BaseModel):
    facility_id: uuid.UUID
    present: bool = True
    sold_out: bool = False


class AlertPrefIn(BaseModel):
    opted_in: bool


class SuggestIn(BaseModel):
    lat: float
    lon: float


def _entries_out(entries: list, db: Session) -> list[dict]:
    """AI-CONTEXT: every entry carries the LOT it is at — name and coordinates.

    Without them the vendor sheet can only say "Today · until 9pm" with no place
    attached, which is ambiguous the moment a cook works more than one lot, and
    leaves the sheet unable to offer the one action the whole flow exists to
    produce (M1-FR8 navigate). Resolved in one pass rather than per row."""
    facilities = {}
    for entry in entries:
        fid = entry.appearance.facility_id
        if fid not in facilities:
            facilities[fid] = facility_registry.get_facility(db, fid)
    coords = {}
    for fid, facility in facilities.items():
        coords[fid] = facility_registry.coordinates(db, facility) if facility else None
    return [_entry_out(e, facilities.get(e.appearance.facility_id), coords) for e in entries]


def _entry_out(entry: m13.VendorEntry, facility=None, coords=None) -> dict:
    belief = entry.presence
    fid = entry.appearance.facility_id
    where = (coords or {}).get(fid)
    return {
        "facility_name": facility.name if facility is not None else None,
        "lat": where[0] if where else None,
        "lon": where[1] if where else None,
        "vendor_id": str(entry.vendor.id),
        "name": entry.vendor.name,
        "vendor_type": entry.vendor.vendor_type.value,
        "verify_status": entry.vendor.verify_status.value,
        "languages": entry.vendor.languages,
        # the RUNG, so the label can say "vendor says halal" rather than "halal"
        "halal_claim": entry.vendor.halal_claim.value,
        "facility_id": str(entry.appearance.facility_id),
        "starts_at": entry.appearance.starts_at.isoformat(),
        "ends_at": entry.appearance.ends_at.isoformat(),
        "property_approved": entry.appearance.property_approved,
        "bucket": entry.bucket,
        "distance_m": entry.distance_m,
        "sold_out": entry.sold_out,
        "offerings": [
            {"name": o.name, "price_cents": o.price_cents, "portions": o.portions}
            for o in entry.offerings
        ],
        # §11.7: `source` is what stops the client printing a driver count for a
        # vendor's own claim. "crowd" -> "N drivers"; "vendor" -> "vendor says".
        "presence": None
        if belief is None
        else {
            "present": belief.present,
            "source": belief.source,
            "sample_size": belief.sample_size,
            "reported_at": belief.reported_at.isoformat() if belief.reported_at else None,
        },
    }


# AI-CONTEXT: A6 req 1 — three gates, and the reason there is more than one.
#
# `_require_food` / `_require_service` are for routes whose SHAPE names a half: an
# appearance is a food mechanism, a facility claim is a service one. `_require_half`
# is for the shared routes (a sheet, a review, a report) where the half is a property
# of the vendor being acted on, not of the endpoint.
#
# The shared case is the one that matters. With food off, a food vendor's sheet must
# 404 exactly as it would with the whole module off — otherwise the deferred half
# stays readable through every endpoint that happens to take a `vendor_id`, and the
# split would be a label rather than a gate.
def _require_active(db: Session) -> None:
    if not m13.is_active(db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor network not enabled")


def _require_type(db: Session, vendor_type: m13.VendorType) -> None:
    if not m13.is_active_for(db, vendor_type):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor network not enabled")


def _require_food(db: Session) -> None:
    _require_type(db, m13.VendorType.food_mobile)


def _require_service(db: Session) -> None:
    _require_type(db, m13.VendorType.service_center)


def _require_half(db: Session, vendor: m13.Vendor) -> None:
    """Gate on the half the VENDOR belongs to."""
    _require_type(db, vendor.vendor_type)


def _require_reportable(db: Session, vendor_id) -> None:
    """A review or promotion belongs to the half its VENDOR is in. Resolved through
    the vendor rather than assumed, so a merged vendor answers about the surviving
    row (§23 entry 73's scoping lesson) instead of about a tombstone."""
    vendor = m13.resolve_vendor(db, vendor_id)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    _require_half(db, vendor)


def _my_vendor(db: Session, account) -> m13.Vendor:
    vendor = db.scalar(select(m13.Vendor).where(m13.Vendor.owner_account_id == account.id))
    resolved = m13.resolve_vendor(db, vendor.id) if vendor is not None else None
    if resolved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no vendor profile")
    _require_half(db, resolved)
    return resolved


# --- Driver side ---
@router.get("/appearances")
def appearances(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    # §11.3 "More filters". These NARROW what is already discoverable and can never
    # widen it — the quality laws run first, the filter runs on their output.
    q: str | None = None,
    language: str | None = None,
    halal: str | None = None,
    # the driver's own position, when they have shared one. Optional on purpose: no
    # location means no distance, never a distance measured from a default.
    lat: float | None = None,
    lon: float | None = None,
    _account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    _require_food(db)
    entries = m13.appearances_in_bbox(
        db,
        min_lat,
        min_lon,
        max_lat,
        max_lon,
        q=q,
        language=language,
        halal=halal,
        origin_lat=lat,
        origin_lon=lon,
    )
    return _entries_out(entries, db)


@router.get("/corridor")
def corridor(
    lat: float,
    lon: float,
    heading_deg: float = 0,
    max_distance_m: float = 64000,
    # filters chosen while STOPPED keep applying while moving — that is what makes
    # them worth persisting, since no keyboard is available at speed (§11.4)
    q: str | None = None,
    language: str | None = None,
    halal: str | None = None,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    _require_food(db)
    ahead = m13.corridor_vendors(
        db, account.id, lat, lon, heading_deg, max_distance_m, q=q, language=language, halal=halal
    )
    return _entries_out(ahead, db)


@router.get("/at/{facility_id}")
def at_facility(
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    all_vendors: bool = False,
    _account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    # Q-6: two by default (the card); `all_vendors` is the sheet's "all vendors"
    _require_food(db)
    limit = 0 if all_vendors else m13.MAX_VENDORS_PER_CARD
    return _entries_out(m13.vendors_at_facility(db, facility_id, limit=limit), db)


@router.get("/{vendor_id}")
def vendor_sheet(
    vendor_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    detail = m13.vendor_detail(db, vendor_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    vendor = detail["vendor"]
    # the sheet is shared, so the half is the VENDOR's. Checked before the analytics
    # emit below: a view of a dark half is not a view anyone should be credited with.
    _require_half(db, vendor)
    score = detail["reliability"]
    summary = m13.review_summary(db, vendor.id)
    # FR8 analytics: a sheet view is the vendor's "someone looked at me" number
    admin.emit(
        db,
        "vendor_sheet_view",
        module=m13.MODULE,
        occurred_at=datetime.now(UTC),
        account_id=account.id,
        properties={"vendor_id": str(vendor.id)},
    )
    return {
        "vendor_id": str(vendor.id),
        "name": vendor.name,
        "vendor_type": vendor.vendor_type.value,
        "verify_status": vendor.verify_status.value,
        "categories": vendor.categories,
        "languages": vendor.languages,
        "halal_disclosure": vendor.halal_disclosure,
        # the rung names WHO is claiming; the sentence above is the vendor's words
        "halal_claim": vendor.halal_claim.value,
        # the raw pair, not a percentage: a fraction carries its own sample size,
        # and "95%" over two appearances would overstate what we actually know
        "shows_up": {"confirmed": score.confirmed, "published": score.published},
        "in_discovery": detail["in_discovery"],
        # so the sheet can render "Following" rather than offering to follow again
        "following": m13.is_following_vendor(db, account.id, vendor.id),
        "alerts_on": notify.is_opted_in(db, account.id, m13.VENDOR_ALERT),
        "appearances": _entries_out(detail["appearances"], db),
        # FR5: the raw pair again — `reviewers` is the honest denominator, and an
        # average without it invites overreading a handful of opinions (§11.7)
        "reviews": {
            "average": summary.average,
            "reviewers": summary.reviewers,
            "items": [
                {
                    "rating": r.rating,
                    "text": r.text,
                    "created_at": r.created_at.isoformat(),
                }
                for r in m13.list_reviews(db, vendor.id)[:REVIEW_PAGE]
            ],
        },
        # FR6: promotions ride in their own key, never mixed into `appearances` —
        # the client renders them in a LABELLED slot (Q-3 / §21.3)
        "promotions": [
            {"promotion_id": str(p.id), "text": p.text, "promoted": True}
            for p in m13.active_promotions(db, vendor.id)
        ],
        "can_review": m13.can_review(db, vendor.id, account.id),
    }


@router.post("/{vendor_id}/confirm")
def confirm(
    vendor_id: uuid.UUID,
    body: ConfirmIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # geofence presence proof, distinct-driver counting and the anti-farming
    # cooldown are all enforced inside F10 — this endpoint adds no trust of its own
    _require_active(db)
    vendor = m13.resolve_vendor(db, vendor_id)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    _require_half(db, vendor)
    now = datetime.now(UTC)
    if body.sold_out:
        m13.report_sold_out(db, account.id, vendor_id, body.facility_id, now=now)
    else:
        m13.confirm_presence(db, account.id, vendor_id, body.facility_id, body.present, now=now)
    belief = m13.presence(db, vendor_id, body.facility_id)
    return {
        "vendor_id": str(vendor_id),
        "present": belief.present if belief else None,
        "source": belief.source if belief else None,
        "sample_size": belief.sample_size if belief else 0,
        "sold_out": m13.is_sold_out(db, vendor_id, body.facility_id),
    }


@router.post("/suggest")
def suggest_a_cook(
    body: SuggestIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # Q-7: the empty state's affordance has to GO somewhere or it is a dead control.
    # It records where drivers want food, which is the demand half of the vendor
    # recruitment loop — the F14 console reads it to target outreach. No vendor is
    # created and nothing is promised to the driver beyond "noted".
    _require_food(db)
    admin.emit(
        db,
        "vendor_suggested",
        module=m13.MODULE,
        occurred_at=datetime.now(UTC),
        account_id=account.id,
        properties={"lat": body.lat, "lon": body.lon},
    )
    return {"recorded": True}


@router.put("/alerts/opt-in")
def set_alert_opt_in(
    body: AlertPrefIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # E-D1: the class is OFF until the driver turns it on, here and nowhere else
    pref = notify.set_class_opt_in(db, account.id, m13.VENDOR_ALERT, body.opted_in)
    return {"class": m13.VENDOR_ALERT, "opted_in": pref.opted_in}


@router.post("/{vendor_id}/mute")
def mute_vendor(
    vendor_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    pref = notify.mute_subject(db, account.id, m13.VENDOR_ALERT, str(vendor_id))
    return {"muted": pref.muted_subjects}


# AI-CONTEXT: following. One tap does three things (see F8 `follow_subject`): records
# the vendor, opts the class in, and clears any older mute on it. The response
# reports the class state back so the UI can SAY that alerts are now on rather than
# leaving the driver to discover it.
@router.post("/{vendor_id}/follow")
def follow_vendor(
    vendor_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = m13.resolve_vendor(db, vendor_id)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    _require_half(db, vendor)
    m13.follow_vendor(db, account.id, vendor_id)
    return {"following": True, "alerts_on": True}


@router.delete("/{vendor_id}/follow")
def unfollow_vendor(
    vendor_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # deliberately NOT gated on the vendor's half: a driver who followed a cook before
    # the food half was deferred must still be able to stop following. §21.8 makes off
    # exactly as easy as on, and a flag is not a reason to lock someone into a
    # subscription — the same reasoning that leaves `mute` open above.
    _require_active(db)
    m13.unfollow_vendor(db, account.id, vendor_id)
    # unfollowing one cook never switches the whole class off — that is a separate,
    # louder choice and making it for someone would take away alerts they still want
    return {
        "following": False,
        "alerts_on": notify.is_opted_in(db, account.id, m13.VENDOR_ALERT),
    }


# --- Vendor side (the Session-B portal will sit on these) ---
@router.post("/register", status_code=201)
def register(
    body: VendorIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    try:
        vendor_type = m13.VendorType(body.vendor_type)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown vendor type") from exc
    # registration is where a half acquires new members, so it is gated on the half
    # being ASKED FOR rather than on the module: with food deferred, no new cook signs
    # up, while a repair shop still can.
    _require_type(db, vendor_type)
    try:
        vendor = m13.register_vendor(
            db,
            account.id,
            body.name,
            vendor_type,
            metro=body.metro,
            contact_phone=body.contact_phone,
            categories=body.categories,
            languages=body.languages,
            halal_disclosure=body.halal_disclosure,
            halal_answered=body.halal_answered,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown vendor type") from exc
    except m13.DuplicateVendor as exc:
        # Q-5: never silently create a second profile for the same cook
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"error": "duplicate_vendor", "existing_vendor_id": str(exc.existing.id)},
        ) from exc
    return {"vendor_id": str(vendor.id), "verify_status": vendor.verify_status.value}


@router.post("/appearances", status_code=201)
def publish(
    body: AppearanceIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_food(db)
    vendor = _my_vendor(db, account)
    gateway = notify.RecordingNotificationGateway()
    try:
        created = m13.publish_appearance(
            db,
            vendor,
            body.facility_id,
            body.starts_at,
            body.ends_at,
            [m13.OfferingIn(o.name, o.price_cents, o.portions) for o in body.offerings],
            property_approved=body.property_approved,
            weekly=body.weekly,
            gateway=gateway,
        )
    except m13.ListingIncomplete as exc:
        # Q-4: name exactly what is missing so the vendor can fix it in one pass
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"error": "listing_incomplete", "missing": exc.missing},
        ) from exc
    except m13.PublishSuspended as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, {"error": "publish_suspended"}) from exc
    return {"appearance_ids": [str(a.id) for a in created]}


@router.delete("/appearances/{appearance_id}")
def cancel(
    appearance_id: uuid.UUID,
    whole_series: bool = False,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_food(db)
    appearance = db.get(m13.Appearance, appearance_id)
    if appearance is None or not m13.is_member(db, appearance.vendor_id, account.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "appearance not found")
    gateway = notify.RecordingNotificationGateway()
    cancelled = m13.cancel_appearance(db, appearance, gateway=gateway, whole_series=whole_series)
    return {"cancelled": [str(a.id) for a in cancelled], "alerts_sent": len(gateway.sent)}


@router.post("/self-report")
def self_report(
    body: ConfirmIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    # the vendor's own "I've arrived" / "sold out" — recorded as an authoritative
    # submission attributed to the vendor, never counted as a driver (§11.7)
    _require_food(db)
    vendor = _my_vendor(db, account)
    m13.vendor_self_report(
        db, vendor, body.facility_id, arrived=body.present, sold_out=body.sold_out
    )
    belief = m13.presence(db, vendor.id, body.facility_id)
    return {
        "source": belief.source if belief else None,
        "present": belief.present if belief else None,
    }


# --- FR5: reviews (driver side) ---
class ReviewIn(BaseModel):
    rating: int
    text: str | None = None


class ReportIn(BaseModel):
    reason: str
    note: str | None = None


@router.post("/{vendor_id}/review", status_code=201)
def review_vendor(
    vendor_id: uuid.UUID,
    body: ReviewIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = m13.resolve_vendor(db, vendor_id)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    _require_half(db, vendor)
    try:
        review = m13.submit_review(db, vendor, account.id, body.rating, body.text)
    except m13.InvalidRating as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except m13.ReviewTooSoon as exc:
        # §12.4: say WHEN they can come back, not just "no"
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"error": "review_too_soon", "next_allowed_at": exc.next_allowed_at.isoformat()},
        ) from exc
    summary = m13.review_summary(db, vendor.id)
    return {
        "review_id": str(review.id),
        "rating": review.rating,
        "average": summary.average,
        "reviewers": summary.reviewers,
    }


# --- Q-8: the driver-facing report affordance ---
def _report(db: Session, kind: str, ref, vendor_id, account_id, body: ReportIn) -> dict:
    try:
        reason = m13.ModerationReason(body.reason)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown reason") from exc
    try:
        outcome = m13.report_content(db, kind, ref, vendor_id, account_id, reason, body.note)
    except m13.AlreadyReported as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "already reported") from exc
    except m13.NotReportable as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "not reportable") from exc
    # `hidden` is deliberately reported back: a driver who reports something is owed
    # an honest answer about whether anything happened yet (§12.4)
    return {"reported": True, "hidden": outcome.hidden, "reports": outcome.distinct_reports}


@router.post("/{vendor_id}/report")
def report_vendor(
    vendor_id: uuid.UUID,
    body: ReportIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = m13.resolve_vendor(db, vendor_id)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    _require_half(db, vendor)
    return _report(db, m13.CONTENT_VENDOR, vendor_id, vendor_id, account.id, body)


@router.post("/reviews/{review_id}/report")
def report_review(
    review_id: uuid.UUID,
    body: ReportIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    review = db.get(m13.VendorReview, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "review not found")
    _require_reportable(db, review.vendor_id)
    return _report(db, m13.CONTENT_REVIEW, review.id, review.vendor_id, account.id, body)


@router.post("/promotions/{promotion_id}/report")
def report_promotion(
    promotion_id: uuid.UUID,
    body: ReportIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    promotion = db.get(m13.Promotion, promotion_id)
    if promotion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "promotion not found")
    _require_reportable(db, promotion.vendor_id)
    return _report(db, m13.CONTENT_PROMOTION, promotion.id, promotion.vendor_id, account.id, body)


# --- FR6: the labelled slot's contents for a facility (driver side) ---
@router.get("/promotions/at/{facility_id}")
def facility_promotions(
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    _account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    # a SEPARATE endpoint from /vendors/at/{id} on purpose: the ranked list and the
    # promoted slot never travel together, so a client cannot blend them by accident
    _require_active(db)
    return [
        {
            "promotion_id": str(p["promotion_id"]),
            "vendor_id": str(p["vendor_id"]),
            "vendor_name": p["vendor_name"],
            "text": p["text"],
            "ends_at": p["ends_at"].isoformat(),
            "promoted": True,
        }
        for p in m13.promotions_for_facility(
            db, facility_id, vendor_types=m13.enabled_vendor_types(db)
        )
    ]


# --- FR7: what a driver sees for a claimed service centre ---
@router.get("/service-center/{facility_id}")
def service_center(
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    _account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_service(db)
    view = m13.claimed_facility_view(db, facility_id)
    if view is None:
        # unclaimed facilities stay plain POIs — there is nothing extra to say
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not a claimed service center")
    return {
        "facility_id": str(view.facility_id),
        "name": view.name,
        "vendor_id": str(view.vendor_id),
        "vendor_name": view.vendor_name,
        "verify_status": view.verify_status,
        "services": view.services,
        "hours": view.hours,
        "phone": view.phone,
    }
