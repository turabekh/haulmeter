"""AI-CONTEXT: M13-FR8 — the vendor portal's API (design-prd §18, §23 E-D3).

The fourth web-first portal, alongside owner / admin / fleet. Everything here is
scoped to the CALLING vendor: a vendor reaches their own profile, documents,
schedule, promotions and analytics, and nothing else. That scoping is enforced in
`_my_vendor` and re-asserted on every write, because a portal that leaks between
tenants is worse than no portal.

Two honesty rules carried over from the driver side:
· The show-up rate a vendor sees is the SAME pair drivers see. There is no vanity
  variant, no rounded-up percentage, no "your rating is improving!" framing.
· Suspension is reported plainly, with the reason, rather than silently failing
  their next publish.

PHASE A: no billing, no payout, no order endpoint. Promotions are free.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import PortalActor, get_db, portal_actor
from app.foundation.f08_notifications import public as notify
from app.foundation.f14_admin import public as admin
from app.modules.m13_vendor import public as m13

router = APIRouter(prefix="/vendor", tags=["vendor-portal"])


class ProfileIn(BaseModel):
    name: str | None = None
    categories: list[str] | None = None
    languages: list[str] | None = None
    halal_disclosure: str | None = None
    halal_answered: bool | None = None
    contact_phone: str | None = None


class OfferingIn(BaseModel):
    name: str
    price_cents: int
    portions: int | None = None


class AppearanceIn(BaseModel):
    facility_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    offerings: list[OfferingIn]
    property_approved: bool = False
    weekly: list[int] | None = None


class PromotionIn(BaseModel):
    text: str
    starts_at: datetime
    ends_at: datetime
    scope: str = m13.PromotionScope.own_appearances.value


class DocumentIn(BaseModel):
    kind: str
    content_b64: str
    filename: str | None = None


class ClaimIn(BaseModel):
    facility_id: uuid.UUID
    claimed_name: str
    content_b64: str | None = None
    filename: str | None = None


class CurateIn(BaseModel):
    services_added: list[str] | None = None
    hours: str | None = None
    phone: str | None = None


def _require_active(db: Session) -> None:
    if not m13.is_active(db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor network not enabled")


def _my_vendor(db: Session, who: PortalActor) -> m13.Vendor:
    """The single tenancy gate. Every endpoint below goes through it, so there is one
    place to be right about who owns what rather than one per route.

    Scoping uses the SUBJECT, so an impersonating admin sees exactly the vendor's own
    screen — that is the point of "view as vendor". Attribution uses the ACTOR, so
    the writes are still the admin's."""
    membership = db.scalar(
        select(m13.VendorMember).where(m13.VendorMember.account_id == who.subject.id)
    )
    vendor = m13.resolve_vendor(db, membership.vendor_id) if membership is not None else None
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no vendor profile")
    return vendor


def _assisted(
    db: Session, who: PortalActor, vendor: m13.Vendor, action: str, before, after
) -> None:
    """A write made while impersonating is recorded as the ADMIN acting on behalf of
    the vendor. The vendor's own writes record nothing here — an audit entry for
    every ordinary edit would bury the ones that matter."""
    if not who.impersonated:
        return
    admin.record_action(
        db,
        f"assisted_{action}",
        actor_account_id=who.actor.id,
        target_kind="vendor",
        target_ref=vendor.id,
        target_key=vendor.name,
        detail={"on_behalf_of": str(who.subject.id), "impersonated": True},
        before=before,
        after=after,
    )


def _decode(content_b64: str) -> bytes:
    import base64

    try:
        return base64.b64decode(content_b64)
    except Exception as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad document encoding") from exc


@router.get("/profile")
def profile(
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = _my_vendor(db, who)
    return {
        "vendor_id": str(vendor.id),
        "name": vendor.name,
        "vendor_type": vendor.vendor_type.value,
        "metro": vendor.metro,
        "contact_phone": vendor.contact_phone,
        "categories": vendor.categories,
        "languages": vendor.languages,
        "halal_disclosure": vendor.halal_disclosure,
        "halal_answered": vendor.halal_answered,
        "verify_status": vendor.verify_status.value,
        "status": vendor.status.value,
        # said plainly, with the count that caused it — a vendor should never
        # discover a suspension by having a publish fail
        "publish_suspended": vendor.publish_suspended,
        "consecutive_no_shows": vendor.consecutive_no_shows,
        # Q-4: exactly what still blocks publishing, so it can be fixed in one pass
        "profile_gaps": m13.profile_gaps(vendor),
        # E-D5: the vendor SEES when support edited their things. Derived from the
        # audit log via target_ref rather than a column on three tables — one source
        # of truth, and the log is already the record of who did what.
        "assisted": [
            {
                "action": a.action.removeprefix("assisted_"),
                "at": a.created_at.isoformat() if a.created_at else None,
                "detail": a.after,
            }
            for a in admin.list_actions(db, target_ref=vendor.id, limit=10)
            if a.action.startswith("assisted_")
        ],
        "documents": [
            {"kind": d.doc_kind.value, "review_status": d.review_status.value}
            for d in vendor.documents
        ],
    }


@router.patch("/profile")
def update_profile(
    body: ProfileIn,
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = _my_vendor(db, who)
    before = {
        "name": vendor.name,
        "languages": list(vendor.languages or []),
        "halal_disclosure": vendor.halal_disclosure,
    }
    if body.name is not None:
        vendor.name = body.name.strip()
    if body.categories is not None:
        vendor.categories = body.categories
    if body.languages is not None:
        vendor.languages = body.languages
    if body.halal_disclosure is not None:
        vendor.halal_disclosure = body.halal_disclosure
    if body.halal_answered is not None:
        vendor.halal_answered = body.halal_answered
    if body.contact_phone is not None:
        vendor.contact_phone = "".join(ch for ch in body.contact_phone if ch.isdigit())[-10:]
    db.flush()
    after = profile(who=who, db=db)
    _assisted(
        db,
        who,
        vendor,
        "profile_edit",
        before,
        {
            "name": after["name"],
            "languages": after["languages"],
            "halal_disclosure": after["halal_disclosure"],
        },
    )
    return after


@router.post("/documents", status_code=201)
def upload_document(
    body: DocumentIn,
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = _my_vendor(db, who)
    try:
        kind = m13.DocumentKind(body.kind)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown document kind") from exc
    record = m13.attach_document(
        db, vendor, who.actor.id, kind, _decode(body.content_b64), body.filename or "document.pdf"
    )
    return {
        "document_id": str(record.id),
        "review_status": record.review_status.value,
        # uploading moves the ladder to documents_on_file, which means EXACTLY
        # "paperwork is on file" — never that anyone inspected a kitchen (§11.7)
        "verify_status": vendor.verify_status.value,
    }


@router.get("/appearances")
def list_appearances(
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> list[dict]:
    _require_active(db)
    vendor = _my_vendor(db, who)
    rows = db.scalars(
        select(m13.Appearance)
        .where(m13.Appearance.vendor_id == vendor.id)
        .order_by(m13.Appearance.starts_at.desc())
    )
    return [
        {
            "appearance_id": str(a.id),
            "facility_id": str(a.facility_id),
            "starts_at": a.starts_at.isoformat(),
            "ends_at": a.ends_at.isoformat(),
            "status": a.status.value,
            "property_approved": a.property_approved,
            "confirmed": a.confirmed,
            "series_id": str(a.series_id) if a.series_id else None,
            "offerings": [
                {"name": o.name, "price_cents": o.price_cents, "portions": o.portions}
                for o in a.offerings
            ],
        }
        for a in rows
    ]


@router.post("/appearances", status_code=201)
def create_appearance(
    body: AppearanceIn,
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = _my_vendor(db, who)
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
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"error": "listing_incomplete", "missing": exc.missing},
        ) from exc
    except m13.PublishSuspended as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, {"error": "publish_suspended"}) from exc
    # the Q-4 publish floor and every other quality law ran above — an admin
    # publishing on a vendor's behalf gets no bypass, only attribution
    _assisted(
        db,
        who,
        vendor,
        "appearance_publish",
        None,
        {"appearance_ids": [str(a.id) for a in created], "facility_id": str(body.facility_id)},
    )
    return {"appearance_ids": [str(a.id) for a in created]}


@router.delete("/appearances/{appearance_id}")
def cancel_appearance(
    appearance_id: uuid.UUID,
    whole_series: bool = False,
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = _my_vendor(db, who)
    appearance = db.get(m13.Appearance, appearance_id)
    if appearance is None or appearance.vendor_id != vendor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "appearance not found")
    gateway = notify.RecordingNotificationGateway()
    cancelled = m13.cancel_appearance(db, appearance, gateway=gateway, whole_series=whole_series)
    _assisted(
        db,
        who,
        vendor,
        "appearance_cancel",
        {"status": "scheduled"},
        {"cancelled": [str(a.id) for a in cancelled]},
    )
    return {"cancelled": [str(a.id) for a in cancelled], "alerts_sent": len(gateway.sent)}


@router.get("/promotions")
def list_promotions(
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> list[dict]:
    _require_active(db)
    vendor = _my_vendor(db, who)
    rows = db.scalars(
        select(m13.Promotion)
        .where(m13.Promotion.vendor_id == vendor.id)
        .order_by(m13.Promotion.created_at.desc())
    )
    return [
        {
            "promotion_id": str(p.id),
            "text": p.text,
            "starts_at": p.starts_at.isoformat(),
            "ends_at": p.ends_at.isoformat(),
            "scope": p.scope.value,
            "status": p.status.value,
            "pushed_at": p.pushed_at.isoformat() if p.pushed_at else None,
        }
        for p in rows
    ]


@router.post("/promotions", status_code=201)
def create_promotion(
    body: PromotionIn,
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = _my_vendor(db, who)
    try:
        promotion = m13.create_promotion(
            db,
            vendor,
            body.text,
            body.starts_at,
            body.ends_at,
            scope=m13.PromotionScope(body.scope),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown scope") from exc
    except m13.InvalidPromotion as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    # the push goes out under the vendor_alert caps — at most one per driver per
    # day, opt-in, quiet hours, per-vendor mute. The portal cannot override them.
    _assisted(db, who, vendor, "promotion_create", None, {"text": promotion.text})
    gateway = notify.RecordingNotificationGateway()
    sent = m13.notify_promotion(db, promotion, gateway)
    delivered = sum(1 for n in sent if n.status == notify.NotificationStatus.sent)
    return {
        "promotion_id": str(promotion.id),
        # reported honestly: "we told N drivers", not "we reached everyone"
        "alerts_delivered": delivered,
        "alerts_suppressed": len(sent) - delivered,
    }


@router.delete("/promotions/{promotion_id}")
def cancel_promotion(
    promotion_id: uuid.UUID,
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = _my_vendor(db, who)
    promotion = db.get(m13.Promotion, promotion_id)
    if promotion is None or promotion.vendor_id != vendor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "promotion not found")
    m13.cancel_promotion(db, promotion)
    return {"promotion_id": str(promotion.id), "status": promotion.status.value}


@router.post("/claims", status_code=201)
def submit_claim(
    body: ClaimIn,
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = _my_vendor(db, who)
    content = _decode(body.content_b64) if body.content_b64 else None
    try:
        claim = m13.submit_claim(
            db, vendor, body.facility_id, body.claimed_name, who.actor.id, content, body.filename
        )
    except m13.NotAServiceCenter as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "service centers only") from exc
    except m13.NotAServiceFacility as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "that facility has no service listing"
        ) from exc
    except m13.NameMismatch as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"error": "name_mismatch", "score": round(exc.score, 2)},
        ) from exc
    return {"claim_id": str(claim.id), "status": claim.status.value}


@router.get("/claims")
def list_claims(
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> list[dict]:
    _require_active(db)
    vendor = _my_vendor(db, who)
    return [
        {
            "claim_id": str(c.id),
            "facility_id": str(c.facility_id),
            "claimed_name": c.claimed_name,
            "status": c.status.value,
            "services_added": c.services_added,
            "hours": c.hours,
            "phone": c.phone,
        }
        for c in m13.claims_for_vendor(db, vendor.id)
    ]


@router.patch("/claims/{claim_id}")
def curate_claim(
    claim_id: uuid.UUID,
    body: CurateIn,
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = _my_vendor(db, who)
    claim = db.get(m13.FacilityClaim, claim_id)
    if claim is None or claim.vendor_id != vendor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "claim not found")
    if claim.status != m13.ClaimStatus.approved:
        raise HTTPException(status.HTTP_409_CONFLICT, "claim not approved yet")
    m13.curate_claim(db, claim, body.services_added, body.hours, body.phone)
    view = m13.claimed_facility_view(db, claim.facility_id)
    return {
        "claim_id": str(claim.id),
        # the union is echoed back so a claimant SEES that their edit added to the
        # ingested facts rather than replacing them (E3.2)
        "services": view.services if view else claim.services_added,
        "hours": claim.hours,
        "phone": claim.phone,
    }


@router.get("/analytics")
def analytics(
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = _my_vendor(db, who)
    score = m13.reliability(db, vendor.id)
    summary = m13.review_summary(db, vendor.id)
    confirmed = sum(
        1
        for a in db.scalars(
            select(m13.Appearance).where(
                m13.Appearance.vendor_id == vendor.id, m13.Appearance.confirmed.is_(True)
            )
        )
    )
    return {
        "sheet_views": admin.count_events(db, "vendor_sheet_view"),
        "confirmations": confirmed,
        # the SAME pair a driver sees on the sheet. No vanity variant, no percentage
        # rounded in the vendor's favour — one number, one meaning, both audiences.
        "shows_up": {"confirmed": score.confirmed, "published": score.published},
        "reviews": {"average": summary.average, "reviewers": summary.reviewers},
        "publish_suspended": vendor.publish_suspended,
    }
