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

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify
from app.modules.m13_vendor import public as m13

router = APIRouter(prefix="/vendors", tags=["vendors"])


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


def _entry_out(entry: m13.VendorEntry) -> dict:
    belief = entry.presence
    return {
        "vendor_id": str(entry.vendor.id),
        "name": entry.vendor.name,
        "vendor_type": entry.vendor.vendor_type.value,
        "verify_status": entry.vendor.verify_status.value,
        "languages": entry.vendor.languages,
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


def _require_active(db: Session) -> None:
    if not m13.is_active(db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor network not enabled")


def _my_vendor(db: Session, account) -> m13.Vendor:
    vendor = db.scalar(select(m13.Vendor).where(m13.Vendor.owner_account_id == account.id))
    resolved = m13.resolve_vendor(db, vendor.id) if vendor is not None else None
    if resolved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no vendor profile")
    return resolved


# --- Driver side ---
@router.get("/appearances")
def appearances(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    _account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    _require_active(db)
    return [_entry_out(e) for e in m13.appearances_in_bbox(db, min_lat, min_lon, max_lat, max_lon)]


@router.get("/corridor")
def corridor(
    lat: float,
    lon: float,
    heading_deg: float = 0,
    max_distance_m: float = 64000,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    _require_active(db)
    return [
        _entry_out(e)
        for e in m13.corridor_vendors(db, account.id, lat, lon, heading_deg, max_distance_m)
    ]


@router.get("/at/{facility_id}")
def at_facility(
    facility_id: uuid.UUID,
    all_vendors: bool = False,
    _account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    # Q-6: two by default (the card); `all_vendors` is the sheet's "all vendors"
    _require_active(db)
    limit = 0 if all_vendors else m13.MAX_VENDORS_PER_CARD
    return [_entry_out(e) for e in m13.vendors_at_facility(db, facility_id, limit=limit)]


@router.get("/{vendor_id}")
def vendor_sheet(
    vendor_id: uuid.UUID,
    _account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    detail = m13.vendor_detail(db, vendor_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    vendor = detail["vendor"]
    score = detail["reliability"]
    return {
        "vendor_id": str(vendor.id),
        "name": vendor.name,
        "vendor_type": vendor.vendor_type.value,
        "verify_status": vendor.verify_status.value,
        "categories": vendor.categories,
        "languages": vendor.languages,
        "halal_disclosure": vendor.halal_disclosure,
        # the raw pair, not a percentage: a fraction carries its own sample size,
        # and "95%" over two appearances would overstate what we actually know
        "shows_up": {"confirmed": score.confirmed, "published": score.published},
        "in_discovery": detail["in_discovery"],
        "appearances": [_entry_out(e) for e in detail["appearances"]],
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


# --- Vendor side (the Session-B portal will sit on these) ---
@router.post("/register", status_code=201)
def register(
    body: VendorIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    try:
        vendor = m13.register_vendor(
            db,
            account.id,
            body.name,
            m13.VendorType(body.vendor_type),
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
    _require_active(db)
    vendor = _my_vendor(db, account)
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
    _require_active(db)
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
    _require_active(db)
    vendor = _my_vendor(db, account)
    m13.vendor_self_report(
        db, vendor, body.facility_id, arrived=body.present, sold_out=body.sold_out
    )
    belief = m13.presence(db, vendor.id, body.facility_id)
    return {
        "source": belief.source if belief else None,
        "present": belief.present if belief else None,
    }
