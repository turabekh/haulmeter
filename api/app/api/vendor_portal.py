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
from app.foundation.f02_facility import public as facility_registry
from app.foundation.f08_notifications import public as notify
from app.foundation.f14_admin import public as admin
from app.modules.m13_vendor import public as m13

router = APIRouter(prefix="/vendor", tags=["vendor-portal"])


class ProfileIn(BaseModel):
    name: str | None = None
    vendor_type: str | None = None
    metro: str | None = None
    categories: list[str] | None = None
    languages: list[str] | None = None
    halal_disclosure: str | None = None
    halal_answered: bool | None = None
    halal_claim: str | None = None
    contact_phone: str | None = None


class MenuItemIn(BaseModel):
    name: str | None = None
    price_cents: int | None = None
    portions: int | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class OfferingIn(BaseModel):
    name: str
    price_cents: int
    portions: int | None = None


class AppearanceIn(BaseModel):
    facility_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    # what to advertise. Either typed in directly, or named from the standing menu —
    # `menu_item_ids: []` means "everything currently on the menu". Whichever route,
    # publishing SNAPSHOTS the values, so a later menu edit cannot reach back into a
    # window a driver already read.
    offerings: list[OfferingIn] = []
    menu_item_ids: list[uuid.UUID] | None = None
    property_approved: bool = False
    weekly: list[int] | None = None


class PromotionEditIn(BaseModel):
    text: str | None = None
    ends_at: datetime | None = None


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
        "halal_claim": vendor.halal_claim.value,
        # what the cook may SELECT right now. `certified` appears only once an
        # approved certificate exists, so the control cannot promise a rung the
        # server will silently take back.
        "halal_claims_available": [
            c.value
            for c in m13.HalalClaim
            if m13.allowed_halal_claim(db, vendor, c) == c
        ],
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
    if body.vendor_type is not None:
        try:
            vendor.vendor_type = m13.VendorType(body.vendor_type)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown vendor type"
            ) from exc
    if body.metro is not None:
        vendor.metro = body.metro.strip()
    if body.categories is not None:
        vendor.categories = body.categories
    if body.languages is not None:
        vendor.languages = body.languages
    if body.halal_disclosure is not None:
        vendor.halal_disclosure = body.halal_disclosure
    if body.halal_answered is not None:
        vendor.halal_answered = body.halal_answered
    if body.halal_claim is not None:
        try:
            wanted = m13.HalalClaim(body.halal_claim)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown halal claim"
            ) from exc
        # `certified` is not self-awardable: it needs an approved halal_cert on file,
        # exactly as `verified` needs reviewed paperwork. An unsupported claim is
        # DOWNGRADED rather than refused, because "vendor says halal" is still true
        # and refusing would leave the cook unable to say anything at all.
        vendor.halal_claim = m13.allowed_halal_claim(db, vendor, wanted)
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
    rows = list(
        db.scalars(
            select(m13.Appearance)
            .where(m13.Appearance.vendor_id == vendor.id)
            .order_by(m13.Appearance.starts_at.desc())
        )
    )
    names = {}
    for a in rows:
        if a.facility_id not in names:
            fac = facility_registry.get_facility(db, a.facility_id)
            names[a.facility_id] = fac.name if fac else None
    return [
        {
            "appearance_id": str(a.id),
            "facility_id": str(a.facility_id),
            # a cook reads a place, not a UUID
            "facility_name": names.get(a.facility_id),
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
    # the menu is a convenience for the cook, not a second source of truth: it is
    # resolved to VALUES here and snapshotted by publish_appearance below, so a price
    # edited tomorrow cannot change what this window advertised.
    offerings = [m13.OfferingIn(o.name, o.price_cents, o.portions) for o in body.offerings]
    if body.menu_item_ids is not None:
        offerings += m13.menu_as_offerings(db, vendor.id, body.menu_item_ids or None)
    try:
        created = m13.publish_appearance(
            db,
            vendor,
            body.facility_id,
            body.starts_at,
            body.ends_at,
            offerings,
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


def _claim_row(db: Session, claim) -> dict:
    facility = facility_registry.get_facility(db, claim.facility_id)
    ingested = m13.facility_services(db, claim.facility_id)
    return {
        "claim_id": str(claim.id),
        "facility_id": str(claim.facility_id),
        # the facility's OWN name and address travel with every claim: a vendor must
        # never be shown an id and asked to recognise their own site from it
        "facility_name": facility.name if facility is not None else claim.claimed_name,
        "facility_address": facility.address if facility is not None else None,
        "claimed_name": claim.claimed_name,
        "status": claim.status.value,
        # both halves of the union, so the portal can SHOW that curation adds to
        # what ingestion already knows rather than replacing it (E3.2)
        "services_ingested": ingested,
        "services_added": claim.services_added or [],
        "services": sorted({*ingested, *(claim.services_added or [])}),
        "has_document": claim.document_id is not None,
        "hours": claim.hours,
        "phone": claim.phone,
    }


# AI-CONTEXT: FR7 discovery. Every other facility lookup in the product is
# geographic; a claimant sits at a desk with a business name and no viewport.
# `already_claimed` is disclosed HERE, before the form is filled, because a rival
# claim becomes a DISPUTE an admin decides (never a silent loss) and a vendor is
# entitled to know that before they submit rather than from the result.
@router.get("/claimable")
def claimable_facilities(
    q: str = "",
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> list[dict]:
    _require_active(db)
    vendor = _my_vendor(db, who)
    if vendor.vendor_type != m13.VendorType.service_center:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "service centers only")
    out = []
    for facility in facility_registry.search_service_facilities(db, q):
        # the picker offers exactly what `submit_claim` will accept — one list
        # answers both questions, so a hit can never be a refusal in waiting
        services = m13.claimable_services(db, facility.id)
        if not services:
            continue
        claimed = m13.approved_claim(db, facility.id)
        out.append(
            {
                "facility_id": str(facility.id),
                "name": facility.name,
                "address": facility.address,
                "services": services,
                "already_claimed": claimed is not None,
                "claimed_by_me": claimed is not None and claimed.vendor_id == vendor.id,
            }
        )
    return out


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
    return _claim_row(db, claim)


@router.get("/claims")
def list_claims(
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = _my_vendor(db, who)
    return {
        "claims": [_claim_row(db, c) for c in m13.claims_for_vendor(db, vendor.id)],
        # the portal offers only what the server will honour, exactly as the
        # verification ladder and the halal rungs do — and it is the SAME list the
        # picker filters by, so what can be claimed and what can be added cannot
        # drift apart (see m13 CLAIMABLE_SERVICES for why `scale` is not on it)
        "service_kinds": list(m13.CLAIMABLE_SERVICES),
    }


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
    # the union is echoed back so a claimant SEES that their edit added to the
    # ingested facts rather than replacing them (E3.2)
    return _claim_row(db, claim)


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
        # scoped to THIS vendor. It was not: every vendor was shown the platform-wide
        # total as their own, which is the §11.7 failure this file's header forbids.
        "sheet_views": admin.count_events(
            db, "vendor_sheet_view", properties_match={"vendor_id": str(vendor.id)}
        ),
        "confirmations": confirmed,
        # the SAME pair a driver sees on the sheet. No vanity variant, no percentage
        # rounded in the vendor's favour — one number, one meaning, both audiences.
        "shows_up": {"confirmed": score.confirmed, "published": score.published},
        "reviews": {"average": summary.average, "reviewers": summary.reviewers},
        "publish_suspended": vendor.publish_suspended,
    }


# --- the standing menu ---
#
# AI-CONTEXT: what the vendor SELLS, kept once instead of retyped per appearance.
# Publishing snapshots these values into per-appearance offerings, so editing a price
# here changes what is advertised NEXT and never what a driver was already shown.
# `price_cents` is information only — Phase A sells nothing (§E1.1).
def _menu_row(item) -> dict:
    return {
        "item_id": str(item.id),
        "name": item.name,
        "price_cents": item.price_cents,
        "portions": item.portions,
        "is_active": item.is_active,
        "sort_order": item.sort_order,
    }


@router.get("/menu")
def list_menu(
    include_inactive: bool = False,
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> list[dict]:
    _require_active(db)
    vendor = _my_vendor(db, who)
    return [_menu_row(i) for i in m13.list_menu(db, vendor.id, include_inactive=include_inactive)]


@router.post("/menu", status_code=201)
def add_menu_item(
    body: MenuItemIn,
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = _my_vendor(db, who)
    try:
        item = m13.add_menu_item(
            db, vendor, body.name or "", body.price_cents, body.portions, body.sort_order
        )
    except m13.InvalidMenuItem as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    _assisted(db, who, vendor, "menu_add", None, _menu_row(item))
    return _menu_row(item)


@router.patch("/menu/{item_id}")
def edit_menu_item(
    item_id: uuid.UUID,
    body: MenuItemIn,
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    _require_active(db)
    vendor = _my_vendor(db, who)
    try:
        before = _menu_row(
            next(
                i
                for i in m13.list_menu(db, vendor.id, include_inactive=True)
                if i.id == item_id
            )
        )
        item = m13.update_menu_item(
            db,
            vendor,
            item_id,
            name=body.name,
            price_cents=body.price_cents,
            portions=body.portions,
            is_active=body.is_active,
            sort_order=body.sort_order,
        )
    except StopIteration as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such menu item") from exc
    except m13.InvalidMenuItem as exc:
        # the domain scopes by vendor in the QUERY, so another tenant's item is
        # indistinguishable from one that does not exist
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    _assisted(db, who, vendor, "menu_edit", before, _menu_row(item))
    return _menu_row(item)


@router.delete("/menu/{item_id}")
def retire_menu_item(
    item_id: uuid.UUID,
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    """Retires rather than deletes. Past appearances hold their own snapshots either
    way, but a seasonal dish comes back and its price should come back with it."""
    _require_active(db)
    vendor = _my_vendor(db, who)
    try:
        item = m13.remove_menu_item(db, vendor, item_id)
    except m13.InvalidMenuItem as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    _assisted(db, who, vendor, "menu_retire", {"is_active": True}, _menu_row(item))
    return _menu_row(item)


# --- verification ---
@router.get("/documents")
def list_documents(
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    """The verification ladder, stated for what it is. `documents_on_file` means
    EXACTLY that paperwork was received — never that anyone inspected a kitchen
    (§23, the tier decision) — and the portal says so rather than implying more."""
    _require_active(db)
    vendor = _my_vendor(db, who)
    return {
        "verify_status": vendor.verify_status.value,
        "documents": [
            {
                "document_id": str(d.id),
                "kind": d.doc_kind.value,
                "review_status": d.review_status.value,
                "at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in sorted(vendor.documents, key=lambda d: d.created_at or datetime.min)
        ],
        "kinds": [k.value for k in m13.DocumentKind],
    }


# --- reputation ---
@router.get("/reputation")
def reputation(
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    """What drivers actually said, in the numbers drivers actually see.

    No vanity variant: the show-up pair is the raw fraction, the rating carries its
    reviewer count, and an unreviewed vendor reads "no reviews yet" rather than 0.0.
    Upheld reports are shown because a vendor who cannot see them cannot fix them —
    and because a suspension that arrives without warning is the failure this portal
    exists to prevent."""
    _require_active(db)
    vendor = _my_vendor(db, who)
    summary = m13.review_summary(db, vendor.id)
    score = m13.reliability(db, vendor.id)
    return {
        "shows_up": {"confirmed": score.confirmed, "published": score.published},
        "rating": {"average": summary.average, "reviewers": summary.reviewers},
        "reviews": [
            {
                "review_id": str(r.id),
                "rating": r.rating,
                "text": r.text,
                "at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in m13.list_reviews(db, vendor.id)
        ],
        # the count that drives suspension, so the number and its consequence are in
        # the same place
        "upheld_reports": m13.upheld_report_count(db, vendor.id),
        "consecutive_no_shows": vendor.consecutive_no_shows,
        "publish_suspended": vendor.publish_suspended,
    }


@router.patch("/promotions/{promotion_id}")
def edit_promotion(
    promotion_id: uuid.UUID,
    body: PromotionEditIn,
    who: PortalActor = Depends(portal_actor),
    db: Session = Depends(get_db),
) -> dict:
    """Text and end date only. A promotion cannot be re-pointed at a different vendor
    or given a longer reach after the fact — the alert budget was already spent on
    the terms it was created with."""
    _require_active(db)
    vendor = _my_vendor(db, who)
    promo = db.get(m13.Promotion, promotion_id)
    if promo is None or promo.vendor_id != vendor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "promotion not found")
    if promo.status != m13.PromotionStatus.active:
        raise HTTPException(status.HTTP_409_CONFLICT, "only an active promotion can be edited")
    before = {"text": promo.text, "ends_at": promo.ends_at.isoformat() if promo.ends_at else None}
    if body.text is not None:
        text = body.text.strip()
        if not text or len(text) > m13.MAX_PROMOTION_CHARS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"between 1 and {m13.MAX_PROMOTION_CHARS} characters",
            )
        promo.text = text
    if body.ends_at is not None:
        if body.ends_at <= promo.starts_at:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "the window must end after it starts"
            )
        promo.ends_at = body.ends_at
    db.flush()
    after = {"text": promo.text, "ends_at": promo.ends_at.isoformat() if promo.ends_at else None}
    _assisted(db, who, vendor, "promotion_edit", before, after)
    # editing does NOT re-send: the vendor_alert budget was spent when it was created,
    # and an edit that pushed again would be a way around the one-per-day cap
    return {"promotion_id": str(promo.id), **after, "alerts_delivered": 0}
