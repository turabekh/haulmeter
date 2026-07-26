"""AI-CONTEXT: M13-FR7 — service-center facility claiming.

A `service_center` vendor claims an existing F2 facility that ingestion already
knows offers repair / tire / wash work, proves the business name matches, uploads a
document, and an admin decides.

**The E3.2 union discipline holds by construction, not by care.** Curated facts —
extra services, hours, phone — live on the CLAIM row. Nothing here writes back to
`f02.facility`, so a claim edit is physically incapable of erasing what OSM or an
admin ingest recorded; `claimed_facility_view` unions the two on read. That is why
the curation fields are on this table and not on the facility, and it is the whole
reason the E3.2 decision (attributes, one source of truth) still pays off here.

One approved claim per facility. A second claimant becomes a dispute for F14 rather
than silently losing, because "who owns this business" is not a question code
should answer.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility_registry
from app.foundation.f06_documents import public as documents
from app.foundation.f13_flags import public as flags
from app.foundation.f14_admin import public as admin

from .enums import ClaimStatus, VendorType
from .models import FacilityClaim, Vendor

# how close the claimed business name must be to the facility's known name
CONFIG_CLAIM_NAME_MATCH = "m13_claim_name_match"
DEFAULT_CLAIM_NAME_MATCH = 0.55

# AI-CONTEXT: which of F2's service vocabulary a VENDOR may claim and curate. This
# is M13's policy, not F2's — F2 records what is there, M13 decides who may speak
# for it. `scale` is excluded on both counts: a weighbridge is public infrastructure
# feeding the M1 weigh-station layer (E3.1), so a service a claimant could simply
# tick would put an unverified scale in front of a driver deciding whether to pull
# in. A facility whose ONLY service is a scale therefore has no service business to
# claim, and the same list answers both "may I claim this?" and "may I add this?" —
# so the picker and the guard cannot drift apart.
CLAIMABLE_SERVICES = tuple(s for s in facility_registry.SERVICE_KINDS if s != "scale")


def claimable_services(db: Session, facility_id) -> list[str]:
    return [s for s in facility_services(db, facility_id) if s in CLAIMABLE_SERVICES]


class NotAServiceCenter(Exception):
    pass


class NotAServiceFacility(Exception):
    """The facility has no ingested service a vendor could claim, so there is nothing
    to claim. Reads the E3.2 `services` list — the one source of truth (PRD §17 Q12)
    — through `CLAIMABLE_SERVICES`, so a scale-only weighbridge is not a business."""


class NameMismatch(Exception):
    def __init__(self, score: float, required: float):
        super().__init__(f"{score:.2f} < {required:.2f}")
        self.score = score
        self.required = required


class AlreadyClaimed(Exception):
    def __init__(self, claim: FacilityClaim):
        super().__init__(str(claim.id))
        self.claim = claim


def _normalize(name: str) -> str:
    return " ".join((name or "").strip().lower().split())


def name_match_score(claimed: str, facility_name: str) -> float:
    return SequenceMatcher(None, _normalize(claimed), _normalize(facility_name)).ratio()


def facility_services(db: Session, facility_id) -> list[str]:
    facility = facility_registry.get_facility(db, facility_id)
    if facility is None:
        return []
    return list((facility.attributes or {}).get("services") or [])


def approved_claim(db: Session, facility_id) -> FacilityClaim | None:
    return db.scalar(
        select(FacilityClaim).where(
            FacilityClaim.facility_id == facility_id,
            FacilityClaim.status == ClaimStatus.approved,
        )
    )


def submit_claim(
    db: Session,
    vendor: Vendor,
    facility_id,
    claimed_name: str,
    account_id,
    document_content: bytes | None = None,
    filename: str | None = None,
    now: datetime | None = None,
) -> FacilityClaim:
    now = now or datetime.now(UTC)
    if vendor.vendor_type != VendorType.service_center:
        raise NotAServiceCenter(str(vendor.id))

    facility = facility_registry.get_facility(db, facility_id)
    if facility is None or not claimable_services(db, facility_id):
        raise NotAServiceFacility(str(facility_id))

    required = float(flags.get_config(db, CONFIG_CLAIM_NAME_MATCH, DEFAULT_CLAIM_NAME_MATCH))
    score = name_match_score(claimed_name, facility.name)
    if score < required:
        raise NameMismatch(score, required)

    document_id = None
    if document_content:
        document = documents.store_document(
            db,
            account_id,
            documents.DocType.permit,
            document_content,
            filename or "claim.pdf",
            subject_kind="facility_claim",
            subject_ref=facility_id,
        )
        document_id = document.id

    existing = approved_claim(db, facility_id)
    claim = FacilityClaim(
        vendor_id=vendor.id,
        facility_id=facility_id,
        claimed_name=claimed_name.strip(),
        name_match_score=round(score, 3),
        document_id=document_id,
        # a rival claim on an already-claimed facility is a DISPUTE, not a rejection:
        # ownership is a fact about the world that an admin has to establish
        status=ClaimStatus.disputed if existing is not None else ClaimStatus.pending,
    )
    db.add(claim)
    db.flush()

    kind = "facility_claim_dispute" if existing is not None else "facility_claim"
    item = admin.enqueue_moderation(db, kind, claim.id, submitted_by=account_id)
    claim.moderation_ref = item.id
    db.flush()
    return claim


def decide_claim(
    db: Session,
    claim: FacilityClaim,
    approve: bool,
    moderator_account_id=None,
    reason: str | None = None,
    now: datetime | None = None,
) -> FacilityClaim:
    now = now or datetime.now(UTC)
    if approve:
        other = approved_claim(db, claim.facility_id)
        if other is not None and other.id != claim.id:
            raise AlreadyClaimed(other)
    claim.status = ClaimStatus.approved if approve else ClaimStatus.rejected
    claim.decided_at = now
    if claim.moderation_ref is not None:
        item = db.get(admin.ModerationItem, claim.moderation_ref)
        if item is not None and item.status == admin.ModerationStatus.pending:
            admin.decide_moderation(
                db,
                item,
                admin.ModerationStatus.approved if approve else admin.ModerationStatus.rejected,
                moderator_account_id=moderator_account_id,
                reason=reason,
            )
    admin.record_action(
        db,
        "facility_claim_decide",
        actor_account_id=moderator_account_id,
        target_kind="facility_claim",
        detail={"claim_id": str(claim.id), "approved": approve},
    )
    db.flush()
    return claim


def curate_claim(
    db: Session,
    claim: FacilityClaim,
    services_added: list[str] | None = None,
    hours: str | None = None,
    phone: str | None = None,
) -> FacilityClaim:
    """Curation is ADDITIVE for services by construction: the list is stored
    separately from the ingested one and unioned on read, so nothing a claimant does
    can drop a fact ingestion established (E3.2)."""
    if services_added is not None:
        claim.services_added = sorted({*(claim.services_added or []), *services_added})
    if hours is not None:
        claim.hours = hours
    if phone is not None:
        claim.phone = phone
    db.flush()
    return claim


@dataclass
class ClaimedFacility:
    facility_id: object
    name: str
    vendor_id: object
    vendor_name: str
    verify_status: str
    services: list[str]
    hours: str | None
    phone: str | None


def claimed_facility_view(db: Session, facility_id) -> ClaimedFacility | None:
    """What a driver sees for a claimed service centre. An UNCLAIMED facility returns
    None and stays a plain POI — claiming adds contact detail and curation, it never
    changes what the facility fundamentally is."""
    claim = approved_claim(db, facility_id)
    if claim is None:
        return None
    from .service import is_presentable

    vendor = db.get(Vendor, claim.vendor_id)
    if vendor is None or not is_presentable(vendor):
        return None
    facility = facility_registry.get_facility(db, facility_id)
    ingested = facility_services(db, facility_id)
    return ClaimedFacility(
        facility_id=facility_id,
        name=facility.name if facility is not None else claim.claimed_name,
        vendor_id=vendor.id,
        vendor_name=vendor.name,
        verify_status=vendor.verify_status.value,
        # union: ingested facts first, curated additions folded in — never replaced
        services=sorted({*ingested, *(claim.services_added or [])}),
        hours=claim.hours,
        phone=claim.phone,
    )


def claims_for_vendor(db: Session, vendor_id) -> list[FacilityClaim]:
    return list(
        db.scalars(
            select(FacilityClaim)
            .where(FacilityClaim.vendor_id == vendor_id)
            .order_by(FacilityClaim.created_at.desc())
        )
    )


__all__ = [
    "CLAIMABLE_SERVICES",
    "CONFIG_CLAIM_NAME_MATCH",
    "DEFAULT_CLAIM_NAME_MATCH",
    "AlreadyClaimed",
    "ClaimedFacility",
    "NameMismatch",
    "NotAServiceCenter",
    "NotAServiceFacility",
    "approved_claim",
    "claimed_facility_view",
    "claimable_services",
    "claims_for_vendor",
    "curate_claim",
    "decide_claim",
    "facility_services",
    "name_match_score",
    "submit_claim",
]
