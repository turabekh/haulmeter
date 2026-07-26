"""AI-CONTEXT: M13 Vendor Network (PRD extension §E1) — discovery of the people who
feed and service drivers at F2 facilities.

PHASE A LAW: this module processes ZERO payments. It publishes information; the
platform sells nothing and takes no cut, which is what keeps it legally a directory
while informal vendors formalize. `Offering.price_cents` is display-only. There is
no order model, no ledger import, no charge path — a test enforces that.

A thin module composing Common Ground via public interfaces only (import-linter
enforced): F1 identity/roles, F2 facilities, F6 documents, F8 the `vendor_alert`
class, F10 crowd beliefs (subject-scoped to the vendor), F13 flags, F14 moderation
+ admin views; corridor geometry comes from M1's public interface. Runs behind the
F13 flag `m13_vendor` (default OFF).

The §E1.9 marketplace quality laws (Q-1..Q-7) are implemented here and each carries
its own test — they are what make the section read as a professional marketplace
rather than a classifieds board.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility_registry
from app.foundation.f03_location import public as location
from app.foundation.f06_documents import public as documents
from app.foundation.f08_notifications import public as notify
from app.foundation.f10_crowd import public as crowd
from app.foundation.f13_flags import public as flags
from app.foundation.f14_admin import public as admin
from app.modules.m01_map import public as m1

from .enums import (
    AppearanceStatus,
    DocumentKind,
    DocumentReviewStatus,
    HalalClaim,
    MemberRole,
    VendorStatus,
    VendorType,
    VendorVerifyStatus,
)
from .models import Appearance, Offering, Vendor, VendorDocument, VendorMember

FLAG_KEY = "m13_vendor"
MODULE = "m13"

# --- §E1.9 quality-law constants (F13-tunable where the number is a judgement call) ---
# Q-6 driver-side noise budget: food enriches pins, it never decorates the canvas
MAX_VENDORS_PER_CARD = 2
MAX_CORRIDOR_VENDORS = 3
# Q-1 no dead content
CONFIG_INACTIVE_DAYS = "m13_inactive_days"
DEFAULT_INACTIVE_DAYS = 28
CONFIG_RECURRENCE_HORIZON_DAYS = "m13_recurrence_horizon_days"
DEFAULT_RECURRENCE_HORIZON_DAYS = 28
# a "not here" belief lapses a live appearance only when the crowd is actually
# confident — one driver who couldn't find the truck must not erase a real vendor
LAPSE_CONFIDENCE = 0.6
LAPSE_MIN_REPORTS = 2
# Q-2 three consecutive unconfirmed appearances suspend publishing pending review
NO_SHOW_STRIKES = 3
# Q-5 dedupe: same blocking + similarity discipline as the F2 facility pipeline
DEDUP_NAME_SIMILARITY = 0.55

VENDOR_ALERT = notify.VENDOR_ALERT_CLASS

# AI-CONTEXT: what makes `route_relevant_only` TRUE rather than merely declared.
#
# The class has always claimed route relevance while nothing enforced it — the code
# said so plainly, because no per-driver route feed exists and prior-confirmation was
# standing in for both consent AND geography. A follow supplies real consent, which
# removes that stand-in: following a cook in Dallas must not push to a driver in
# Ohio. So relevance becomes an explicit gate on the driver's own last known
# position, and its two numbers are F13 config rather than constants.
#
# 240 km: a day's driving is 800+, so a cook this side of that is plausibly reachable
# and one beyond it is not. 6 hours: a driver mid-shift can be 400 km from a ping
# older than that, which would make the gate measure a place they have left.
CONFIG_FOLLOW_RADIUS_M = "m13_follow_radius_m"
DEFAULT_FOLLOW_RADIUS_M = 240_000
CONFIG_FOLLOW_PING_MAX_AGE_S = "m13_follow_ping_max_age_s"
DEFAULT_FOLLOW_PING_MAX_AGE_S = 6 * 3600


class VendorNotFound(Exception):
    pass


class DuplicateVendor(Exception):
    """Q-5: one canonical vendor. A driver never sees the same cook twice."""

    def __init__(self, existing: Vendor):
        super().__init__(str(existing.id))
        self.existing = existing


class ListingIncomplete(Exception):
    """Q-4: the publish floor. Carries the missing fields so the UI can name them."""

    def __init__(self, missing: list[str]):
        super().__init__(", ".join(missing))
        self.missing = missing


class PublishSuspended(Exception):
    """Q-2: repeated no-shows suspended this vendor pending F14 review."""


def register_module(db: Session) -> None:
    flags.register_flag(db, FLAG_KEY, description="M13 Vendor Network (discovery only, Phase A)")
    admin.register_admin_view(db, "m13.vendors", MODULE, "Vendors", "/admin/m13/vendors")


def is_active(db: Session) -> bool:
    return flags.is_enabled(db, FLAG_KEY)


# --- Q-5: one canonical vendor ---
def _normalize_vendor_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _normalize_phone(phone: str | None) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())[-10:]


def find_vendor_duplicates(
    db: Session, name: str, metro: str, contact_phone: str | None, owner_account_id=None
) -> list[Vendor]:
    """Blocking + fuzzy match, mirroring the F2 facility pipeline: an exact phone or
    owner-account hit is decisive; otherwise a similar name inside the same metro
    block is the candidate. Merged and suspended vendors are never merge targets."""
    normalized = _normalize_vendor_name(name)
    phone = _normalize_phone(contact_phone)
    live = (Vendor.status == VendorStatus.active,)

    if phone:
        by_phone = list(db.scalars(select(Vendor).where(Vendor.contact_phone == phone, *live)))
        if by_phone:
            return by_phone
    if owner_account_id is not None:
        by_owner = list(
            db.scalars(select(Vendor).where(Vendor.owner_account_id == owner_account_id, *live))
        )
        if by_owner:
            return by_owner
    return list(
        db.scalars(
            select(Vendor)
            .where(
                Vendor.metro == metro,
                func.similarity(Vendor.name_normalized, normalized) >= DEDUP_NAME_SIMILARITY,
                *live,
            )
            .order_by(func.similarity(Vendor.name_normalized, normalized).desc())
        )
    )


def register_vendor(
    db: Session,
    owner_account_id,
    name: str,
    vendor_type: VendorType,
    metro: str = "",
    contact_phone: str | None = None,
    categories: list[str] | None = None,
    languages: list[str] | None = None,
    halal_disclosure: str | None = None,
    halal_answered: bool = False,
    is_dev: bool = False,
    allow_duplicate: bool = False,
) -> Vendor:
    if not allow_duplicate:
        existing = find_vendor_duplicates(db, name, metro, contact_phone, owner_account_id)
        if existing:
            raise DuplicateVendor(existing[0])

    vendor = Vendor(
        owner_account_id=owner_account_id,
        vendor_type=vendor_type,
        name=name.strip(),
        name_normalized=_normalize_vendor_name(name),
        metro=metro,
        contact_phone=_normalize_phone(contact_phone),
        categories=categories or [],
        languages=languages or [],
        halal_disclosure=halal_disclosure,
        halal_answered=halal_answered,
        is_dev=is_dev,
    )
    db.add(vendor)
    db.flush()

    db.add(
        VendorMember(vendor_id=vendor.id, account_id=owner_account_id, member_role=MemberRole.owner)
    )
    _ensure_vendor_role(db, owner_account_id)
    db.flush()
    return vendor


def _ensure_vendor_role(db: Session, account_id) -> None:
    # attach the F1 `vendor` role once, and expire the account's loaded role
    # collection so a caller holding the object sees the new attachment
    account = db.get(identity.Account, account_id)
    if account is None or any(r.role == identity.Role.vendor for r in account.roles):
        return
    identity.attach_role(db, account, identity.Role.vendor)
    db.expire(account, ["roles"])


def merge_vendors(db: Session, canonical: Vendor, duplicate: Vendor) -> Vendor:
    # Q-5: duplicates merge, never coexist. Appearances and members follow the
    # canonical record so nothing the duplicate published is lost.
    for appearance in db.scalars(select(Appearance).where(Appearance.vendor_id == duplicate.id)):
        appearance.vendor_id = canonical.id
    for member in db.scalars(select(VendorMember).where(VendorMember.vendor_id == duplicate.id)):
        already = db.scalar(
            select(VendorMember).where(
                VendorMember.vendor_id == canonical.id,
                VendorMember.account_id == member.account_id,
            )
        )
        if already is None:
            member.vendor_id = canonical.id
        else:
            db.delete(member)
    duplicate.status = VendorStatus.merged
    duplicate.merged_into_id = canonical.id
    db.flush()
    return canonical


def resolve_vendor(db: Session, vendor_id) -> Vendor | None:
    vendor = db.get(Vendor, vendor_id)
    seen: set = set()
    while vendor is not None and vendor.merged_into_id is not None and vendor.id not in seen:
        seen.add(vendor.id)
        vendor = db.get(Vendor, vendor.merged_into_id)
    return vendor


def add_member(db: Session, vendor: Vendor, account_id, member_role=MemberRole.helper):
    member = VendorMember(vendor_id=vendor.id, account_id=account_id, member_role=member_role)
    db.add(member)
    _ensure_vendor_role(db, account_id)
    db.flush()
    return member


def is_member(db: Session, vendor_id, account_id) -> bool:
    return (
        db.scalar(
            select(VendorMember.id).where(
                VendorMember.vendor_id == vendor_id, VendorMember.account_id == account_id
            )
        )
        is not None
    )


# --- FR1: verification ladder (documents via F6, review queue in F14) ---
def attach_document(
    db: Session, vendor: Vendor, account_id, doc_kind: DocumentKind, content: bytes, filename: str
) -> VendorDocument:
    doc_type = {
        DocumentKind.insurance: documents.DocType.insurance,
        DocumentKind.license: documents.DocType.permit,
        DocumentKind.halal_cert: documents.DocType.other,
    }[doc_kind]
    document = documents.store_document(db, account_id, doc_type, content, filename)
    record = VendorDocument(vendor_id=vendor.id, document_id=document.id, doc_kind=doc_kind)
    db.add(record)
    db.flush()

    item = admin.enqueue_moderation(db, "vendor_document", record.id, submitted_by=account_id)
    record.moderation_ref = item.id
    # the ladder's middle rung means EXACTLY "paperwork is on file and an admin
    # looked at it" — never that anyone inspected a kitchen (§11.7)
    if vendor.verify_status == VendorVerifyStatus.unverified:
        vendor.verify_status = VendorVerifyStatus.documents_on_file
    db.flush()
    return record


def decide_document(
    db: Session, record: VendorDocument, approve: bool, moderator_account_id=None, reason=None
) -> VendorDocument:
    record.review_status = (
        DocumentReviewStatus.approved if approve else DocumentReviewStatus.rejected
    )
    if record.moderation_ref is not None:
        item = db.get(admin.ModerationItem, record.moderation_ref)
        if item is not None:
            admin.decide_moderation(
                db,
                item,
                admin.ModerationStatus.approved if approve else admin.ModerationStatus.rejected,
                moderator_account_id=moderator_account_id,
                reason=reason,
            )
    db.flush()
    return record


def set_verification(
    db: Session, vendor: Vendor, status: VendorVerifyStatus, moderator_account_id=None
) -> Vendor:
    vendor.verify_status = status
    admin.record_action(
        db,
        "vendor_verify",
        actor_account_id=moderator_account_id,
        target_kind="vendor",
        detail={"vendor_id": str(vendor.id), "status": status.value},
    )
    db.flush()
    return vendor


def suspend_vendor(db: Session, vendor: Vendor, suspended: bool, moderator_account_id=None):
    vendor.status = VendorStatus.suspended if suspended else VendorStatus.active
    if not suspended:
        vendor.publish_suspended = False
        vendor.consecutive_no_shows = 0
    admin.record_action(
        db,
        "vendor_suspend" if suspended else "vendor_reinstate",
        actor_account_id=moderator_account_id,
        target_kind="vendor",
        detail={"vendor_id": str(vendor.id)},
    )
    db.flush()
    return vendor


# --- Q-4: the listing completeness floor ---
def profile_gaps(vendor: Vendor) -> list[str]:
    gaps = []
    if not vendor.languages:
        gaps.append("languages")
    # "no halal claim" is a complete answer; a blank is not
    if not vendor.halal_answered:
        gaps.append("halal_disclosure")
    return gaps


def profile_complete(vendor: Vendor) -> bool:
    return not profile_gaps(vendor)


# --- FR2: appearances & schedules ---
@dataclass
class OfferingIn:
    name: str
    price_cents: int
    portions: int | None = None


def _config_int(db: Session, key: str, default: int) -> int:
    return int(flags.get_config(db, key, default))


def publish_appearance(
    db: Session,
    vendor: Vendor,
    facility_id,
    starts_at: datetime,
    ends_at: datetime,
    offerings: list[OfferingIn],
    property_approved: bool = False,
    weekly: list[int] | None = None,
    now: datetime | None = None,
    gateway=None,
) -> list[Appearance]:
    """Q-4 publish floor + Q-2 suspension gate. A weekly schedule materializes
    concrete occurrences over the horizon; a one-off returns a single row."""
    now = now or datetime.now(UTC)
    if vendor.publish_suspended:
        raise PublishSuspended(str(vendor.id))

    missing = profile_gaps(vendor)
    if facility_id is None:
        missing.append("facility")
    if starts_at is None or ends_at is None or ends_at <= starts_at:
        missing.append("time_window")
    priced = [o for o in (offerings or []) if o.name and o.price_cents is not None]
    if not priced:
        # a menu without a price is the classifieds-board failure mode Q-4 exists
        # to prevent — a driver cannot decide to detour on "food available"
        missing.append("offering_with_price")
    if facility_id is not None and facility_registry.get_facility(db, facility_id) is None:
        missing.append("facility")
    if missing:
        raise ListingIncomplete(sorted(set(missing)))

    series_id = uuid.uuid4() if weekly else None
    recurrence = {"weekly": sorted(set(weekly))} if weekly else None
    created: list[Appearance] = []
    for window_start, window_end in _occurrences(db, starts_at, ends_at, weekly):
        appearance = Appearance(
            vendor_id=vendor.id,
            facility_id=facility_id,
            starts_at=window_start,
            ends_at=window_end,
            recurrence=recurrence,
            series_id=series_id,
            property_approved=property_approved,
        )
        db.add(appearance)
        db.flush()
        for offering in priced:
            db.add(
                Offering(
                    appearance_id=appearance.id,
                    name=offering.name,
                    price_cents=offering.price_cents,
                    portions=offering.portions,
                )
            )
        created.append(appearance)

    vendor.last_published_at = now
    db.flush()
    # only the FIRST occurrence of a series is announced. A weekly schedule creates
    # many rows and the driver asked about a cook, not about a calendar — one push
    # per publish, not one per Tuesday between now and the horizon.
    if created and gateway is not None:
        notify_published(db, created[0], gateway, now=now)
    return created


def _occurrences(db: Session, starts_at, ends_at, weekly: list[int] | None):
    if not weekly:
        return [(starts_at, ends_at)]
    # materialize real rows across the horizon rather than expanding a rule at read
    # time: Q-1 marks occurrences lapsed and Q-2 scores them, and neither can act on
    # a rule. The horizon also bounds "how far ahead can dead content live".
    horizon_days = _config_int(db, CONFIG_RECURRENCE_HORIZON_DAYS, DEFAULT_RECURRENCE_HORIZON_DAYS)
    duration = ends_at - starts_at
    wanted = set(weekly)
    out = []
    for offset in range(horizon_days):
        day = starts_at + timedelta(days=offset)
        if day.weekday() in wanted:
            out.append((day, day + duration))
    return out


def cancel_appearance(
    db: Session,
    appearance: Appearance,
    gateway=None,
    now: datetime | None = None,
    whole_series: bool = False,
) -> list[Appearance]:
    """Cancelling notifies subscribed drivers — the only `vendor_alert` event that
    exists in Session A. A driver who planned a detour deserves to hear it."""
    now = now or datetime.now(UTC)
    targets = [appearance]
    if whole_series and appearance.series_id is not None:
        targets = list(
            db.scalars(
                select(Appearance).where(
                    Appearance.series_id == appearance.series_id,
                    Appearance.starts_at >= now,
                    Appearance.status.in_((AppearanceStatus.scheduled, AppearanceStatus.live)),
                )
            )
        )
    for target in targets:
        target.status = AppearanceStatus.cancelled
    db.flush()
    if gateway is not None:
        for target in targets:
            notify_cancelled(db, target, gateway, now=now)
    return targets


def notify_cancelled(db: Session, appearance: Appearance, gateway, now=None) -> list:
    """Fan the cancellation out to drivers who confirmed this vendor recently — they
    are the ones who might drive to it. The `vendor_alert` class does the rest of the
    gating (opt-in, one a day, quiet hours, per-vendor mute); we never bypass it."""
    now = now or datetime.now(UTC)
    vendor = db.get(Vendor, appearance.vendor_id)
    facility = facility_registry.get_facility(db, appearance.facility_id)
    # followers FIRST: someone who asked to hear about this cook has a stronger claim
    # on the one daily slot than someone who once tapped "here now" and moved on.
    audience = _relevant_audience(db, appearance, followers_first=True, now=now)
    sent = []
    for account_id in audience:
        sent.append(
            notify.dispatch(
                db,
                account_id,
                notify.NotificationTier.P1,
                VENDOR_ALERT,
                f"{vendor.name} cancelled",
                f"Not at {facility.name if facility else 'the stop'} tonight",
                f"/vendor/{vendor.id}",
                gateway,
                now=now,
                subject_ref=str(vendor.id),
            )
        )
    return sent


def follow_vendor(db: Session, account_id, vendor_id) -> None:
    """Following is consent to be told, never permission to be told more. Every cap
    the class declares still applies — see F8's `follow_subject` for what one tap
    changes and why it changes all three things at once."""
    notify.follow_subject(db, account_id, VENDOR_ALERT, str(vendor_id))


def unfollow_vendor(db: Session, account_id, vendor_id) -> None:
    notify.unfollow_subject(db, account_id, VENDOR_ALERT, str(vendor_id))


def is_following_vendor(db: Session, account_id, vendor_id) -> bool:
    return notify.is_following(db, account_id, VENDOR_ALERT, str(vendor_id))


def _past_confirmers(db: Session, vendor_id) -> list:
    return list(
        db.scalars(
            select(crowd.Submission.account_id)
            .where(
                crowd.Submission.subject_ref == str(vendor_id),
                crowd.Submission.signal_type == crowd.SignalType.vendor_present,
                crowd.Submission.account_id.is_not(None),
            )
            .distinct()
        )
    )


def _relevant_audience(
    db: Session, appearance: Appearance, followers_first: bool = False, now=None
) -> list:
    """Who is close enough for this to be worth an interruption, nearest first.

    Two rules do the work. **A stale ping is not a location**, so a driver F3 cannot
    currently place is dropped rather than guessed at — the notification simply is
    not relevant enough to spend a scarce budget on. And the survivors are ordered by
    distance, because the class allows ONE push per driver per day: when several
    followed cooks publish on the same day, the one that gets through should be the
    nearest rather than whichever the loop happened to reach first.
    """
    now = now or datetime.now(UTC)
    radius = float(_config_int(db, CONFIG_FOLLOW_RADIUS_M, DEFAULT_FOLLOW_RADIUS_M))
    max_age = timedelta(
        seconds=_config_int(db, CONFIG_FOLLOW_PING_MAX_AGE_S, DEFAULT_FOLLOW_PING_MAX_AGE_S)
    )
    followers = notify.followers_of(db, VENDOR_ALERT, str(appearance.vendor_id))
    candidates = list(followers)
    if not followers_first:
        candidates = list(dict.fromkeys(candidates))
    else:
        for account_id in _past_confirmers(db, appearance.vendor_id):
            if account_id not in candidates:
                candidates.append(account_id)

    scored = []
    for account_id in candidates:
        where = location.last_known_position(db, account_id, max_age, now=now)
        if where is None:
            continue  # cannot place them: stay quiet rather than guess
        distances = facility_registry.facility_distances(
            db, [appearance.facility_id], where[0], where[1]
        )
        metres = distances.get(appearance.facility_id)
        if metres is None or metres > radius:
            continue
        scored.append((metres, account_id))
    scored.sort(key=lambda pair: pair[0])
    return [account_id for _, account_id in scored]


def notify_published(db: Session, appearance: Appearance, gateway, now=None) -> list:
    """A followed cook published somewhere a driver can actually reach. This is the
    event the food loop was missing: everything before it could only tell a driver
    about a cook they had already found for themselves."""
    now = now or datetime.now(UTC)
    if gateway is None:
        return []
    vendor = db.get(Vendor, appearance.vendor_id)
    if vendor is None or not is_presentable(vendor):
        return []
    facility = facility_registry.get_facility(db, appearance.facility_id)
    when = appearance.starts_at
    sent = []
    for account_id in _relevant_audience(db, appearance, now=now):
        sent.append(
            notify.dispatch(
                db,
                account_id,
                notify.NotificationTier.P1,
                VENDOR_ALERT,
                f"{vendor.name} published",
                f"{facility.name if facility else 'A stop'} · {when:%a} from {when:%H:%M}",
                f"/vendor/{vendor.id}",
                gateway,
                now=now,
                subject_ref=str(vendor.id),
            )
        )
    return sent


# --- FR4: crowd confirmation (the standard F10 belief pipeline, subject-scoped) ---
def confirm_presence(
    db: Session, account_id, vendor_id, facility_id, present: bool, now: datetime | None = None
):
    """A driver's "he's here" / "not here". Ordinary F10 submission: geofence
    presence proof, distinct-driver counting, decay and the anti-farming cooldown all
    apply unchanged. Scoped to this vendor so two cooks at one lot never collide."""
    now = now or datetime.now(UTC)
    submission = crowd.submit(
        db,
        account_id,
        facility_id,
        crowd.SignalType.vendor_present,
        {"present": present},
        submitted_at=now,
        subject_ref=str(vendor_id),
    )
    crowd.update_belief(
        db, facility_id, crowd.SignalType.vendor_present, as_of=now, subject_ref=str(vendor_id)
    )
    return submission


def report_sold_out(db: Session, account_id, vendor_id, facility_id, now: datetime | None = None):
    now = now or datetime.now(UTC)
    submission = crowd.submit(
        db,
        account_id,
        facility_id,
        crowd.SignalType.vendor_sold_out,
        {"sold_out": True},
        submitted_at=now,
        subject_ref=str(vendor_id),
    )
    crowd.update_belief(
        db, facility_id, crowd.SignalType.vendor_sold_out, as_of=now, subject_ref=str(vendor_id)
    )
    return submission


def vendor_self_report(
    db: Session, vendor: Vendor, facility_id, arrived: bool = True, sold_out: bool = False, now=None
):
    """The vendor's own "I've arrived" / "sold out". Recorded as an AUTHORITATIVE
    submission attributed to the vendor — it is a real source with a real timestamp,
    but it is not a driver, so it must never be rendered as "N drivers" (§11.7). The
    UI reads the belief's source to say "vendor says" instead."""
    now = now or datetime.now(UTC)
    signal = crowd.SignalType.vendor_sold_out if sold_out else crowd.SignalType.vendor_present
    value = {"sold_out": True} if sold_out else {"present": arrived}
    submission = crowd.submit_authoritative(
        db,
        facility_id,
        signal,
        value,
        submitted_at=now,
        source=f"vendor:{vendor.id}",
        subject_ref=str(vendor.id),
    )
    crowd.update_belief(db, facility_id, signal, as_of=now, subject_ref=str(vendor.id))
    return submission


@dataclass
class PresenceBelief:
    present: bool | None
    confidence: float
    sample_size: int
    reported_at: datetime | None
    # "vendor" when the vendor's own report is the winning reading, else "crowd".
    # The UI must never print a driver count for a vendor-sourced belief (§11.7).
    source: str


def presence(db: Session, vendor_id, facility_id) -> PresenceBelief | None:
    belief = crowd.get_belief(
        db, facility_id, crowd.SignalType.vendor_present, subject_ref=str(vendor_id)
    )
    if belief is None:
        return None
    is_vendor_sourced = _belief_is_vendor_sourced(db, vendor_id, facility_id, belief)
    return PresenceBelief(
        present=(belief.value or {}).get("present"),
        confidence=belief.confidence,
        sample_size=belief.sample_size,
        reported_at=belief.freshest_at,
        source="vendor" if is_vendor_sourced else "crowd",
    )


def _belief_is_vendor_sourced(db: Session, vendor_id, facility_id, belief) -> bool:
    # the winning reading is the freshest one in scope; if that is the vendor's own
    # authoritative row, the belief is not a driver count
    freshest = db.scalar(
        select(crowd.Submission)
        .where(
            crowd.Submission.facility_id == facility_id,
            crowd.Submission.signal_type == crowd.SignalType.vendor_present,
            crowd.Submission.subject_ref == str(vendor_id),
        )
        .order_by(crowd.Submission.submitted_at.desc())
        .limit(1)
    )
    return bool(freshest is not None and freshest.authoritative)


def is_sold_out(db: Session, vendor_id, facility_id) -> bool:
    belief = crowd.get_belief(
        db, facility_id, crowd.SignalType.vendor_sold_out, subject_ref=str(vendor_id)
    )
    return bool(belief and (belief.value or {}).get("sold_out"))


# --- Q-2: reliability is public and load-bearing ---
@dataclass
class Reliability:
    confirmed: int
    published: int

    @property
    def rate(self) -> float:
        # an unproven vendor is neither trusted nor punished: no history reads as
        # 1.0 so a first-timer ranks on verification and distance, not on a zero
        return 1.0 if self.published == 0 else self.confirmed / self.published


def reliability(db: Session, vendor_id) -> Reliability:
    rows = list(
        db.scalars(
            select(Appearance).where(
                Appearance.vendor_id == vendor_id,
                Appearance.status.in_((AppearanceStatus.done, AppearanceStatus.lapsed)),
            )
        )
    )
    return Reliability(confirmed=sum(1 for r in rows if r.confirmed), published=len(rows))


def _window_reports(
    db: Session, appearance: Appearance, until: datetime | None = None
) -> tuple[int, int]:
    """Distinct DRIVERS who reported this vendor present / absent DURING this
    appearance's window. Window-scoped on purpose: a belief row is shared by every
    appearance the vendor ever made at that facility, so reading it directly would
    let yesterday's confirmation credit tonight's no-show.

    The vendor's own authoritative report is excluded — Q-2 accountability is a
    CROWD measure, and a vendor confirming itself would defeat the whole point.
    """
    starts, ends = _aware(appearance.starts_at), _aware(appearance.ends_at)
    upper = min(ends, _aware(until)) if until is not None else ends
    rows = db.scalars(
        select(crowd.Submission).where(
            crowd.Submission.facility_id == appearance.facility_id,
            crowd.Submission.signal_type == crowd.SignalType.vendor_present,
            crowd.Submission.subject_ref == str(appearance.vendor_id),
            crowd.Submission.account_id.is_not(None),
            crowd.Submission.authoritative.is_(False),
            crowd.Submission.submitted_at >= starts,
            crowd.Submission.submitted_at <= upper,
        )
    )
    latest: dict = {}
    for row in rows:
        current = latest.get(row.account_id)
        if current is None or row.submitted_at > current.submitted_at:
            latest[row.account_id] = row
    present = sum(1 for r in latest.values() if (r.value or {}).get("present") is True)
    absent = sum(1 for r in latest.values() if (r.value or {}).get("present") is False)
    return present, absent


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# --- Q-1: no dead content, ever ---
def sweep_appearances(db: Session, now: datetime | None = None) -> dict:
    """The map must never show a vendor a driver cannot actually buy from tonight.
    Three rules run here: a window that ended is done, a live appearance the crowd
    says isn't happening lapses, and a vendor silent for 28 days leaves discovery."""
    now = now or datetime.now(UTC)
    stats = {"opened": 0, "closed": 0, "lapsed": 0, "deactivated": 0}

    for appearance in db.scalars(
        select(Appearance).where(Appearance.status == AppearanceStatus.scheduled)
    ):
        if appearance.starts_at <= now < appearance.ends_at:
            appearance.status = AppearanceStatus.live
            stats["opened"] += 1

    # a sustained "not here" belief removes a LIVE appearance from the map. Gated on
    # confidence AND a second reporter so one driver who couldn't find the truck
    # can't erase a vendor who is really there.
    for appearance in db.scalars(
        select(Appearance).where(Appearance.status == AppearanceStatus.live)
    ):
        present, absent = _window_reports(db, appearance, until=now)
        total = present + absent
        if absent >= LAPSE_MIN_REPORTS and total > 0 and (absent / total) >= LAPSE_CONFIDENCE:
            appearance.status = AppearanceStatus.lapsed
            _score_appearance(db, appearance)
            stats["lapsed"] += 1

    for appearance in db.scalars(
        select(Appearance).where(
            Appearance.status.in_((AppearanceStatus.scheduled, AppearanceStatus.live)),
            Appearance.ends_at <= now,
        )
    ):
        appearance.status = AppearanceStatus.done
        _score_appearance(db, appearance)
        stats["closed"] += 1

    stats["deactivated"] = len(deactivate_inactive_vendors(db, now))
    db.flush()
    return stats


def _score_appearance(db: Session, appearance: Appearance) -> None:
    """Q-2: when a window closes, did the crowd confirm the vendor showed up? The
    answer feeds the public show-up rate, the ranking weight, and the strike count."""
    present, absent = _window_reports(db, appearance)
    confirmed = present > absent and present > 0
    appearance.confirmed = confirmed

    vendor = db.get(Vendor, appearance.vendor_id)
    if vendor is None:
        return
    if confirmed:
        vendor.consecutive_no_shows = 0
    else:
        vendor.consecutive_no_shows += 1
        if vendor.consecutive_no_shows >= NO_SHOW_STRIKES and not vendor.publish_suspended:
            # publishing stops pending F14 review — no-show accountability is what
            # makes a pre-driving detour trustworthy in the first place
            vendor.publish_suspended = True
            admin.enqueue_moderation(db, "vendor_no_shows", vendor.id)
    db.flush()


def deactivate_inactive_vendors(db: Session, now: datetime | None = None) -> list[Vendor]:
    """A vendor with no publish in 28 days leaves discovery. The profile persists and
    reactivates on the next publish — this is dormancy, not deletion."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=_config_int(db, CONFIG_INACTIVE_DAYS, DEFAULT_INACTIVE_DAYS))
    return [v for v in db.scalars(select(Vendor)) if _is_dormant(v, cutoff)]


def _is_dormant(vendor: Vendor, cutoff: datetime) -> bool:
    if vendor.status != VendorStatus.active:
        return True
    last = vendor.last_published_at
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    return last < cutoff


def is_presentable(vendor: Vendor) -> bool:
    """May this vendor appear in front of a driver at all? Suspension arrives by two
    different routes — an admin action (`status`) and the automatic no-show/report
    gate (`publish_suspended`) — and every surface must honour BOTH. Keeping the
    question in one function is what stops a new surface honouring only one.
    """
    return vendor.status == VendorStatus.active and not vendor.publish_suspended


def in_discovery(db: Session, vendor: Vendor, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=_config_int(db, CONFIG_INACTIVE_DAYS, DEFAULT_INACTIVE_DAYS))
    return not _is_dormant(vendor, cutoff)


# --- FR3: discovery (ranking Q-3, caps Q-6, empty states Q-7) ---
# Q-3: the ONLY inputs to discovery order. There is deliberately no promotion or
# payment term anywhere in this tuple — pay-to-rank is constitutionally out (§E1.9,
# same spirit as the §11.7 fuel-label honesty pass). Promotions land in Session B as
# a separate LABELLED slot; they will never be blended into this ordering.
BUCKET_LIVE_CONFIRMED = 0
BUCKET_LIVE = 1
BUCKET_UPCOMING_TODAY = 2
BUCKET_THIS_WEEK = 3

_VERIFY_RANK = {
    VendorVerifyStatus.verified: 0,
    VendorVerifyStatus.documents_on_file: 1,
    VendorVerifyStatus.unverified: 2,
}


@dataclass
class VendorEntry:
    vendor: Vendor
    appearance: Appearance
    bucket: int
    distance_m: float | None = None
    reliability_rate: float = 1.0
    presence: PresenceBelief | None = None
    sold_out: bool = False
    offerings: list = field(default_factory=list)


def _bucket(appearance: Appearance, now: datetime, confirmed_live: bool) -> int | None:
    starts, ends = appearance.starts_at, appearance.ends_at
    if starts.tzinfo is None:
        starts = starts.replace(tzinfo=UTC)
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=UTC)
    if starts <= now < ends:
        return BUCKET_LIVE_CONFIRMED if confirmed_live else BUCKET_LIVE
    if now < starts:
        if starts.date() == now.date():
            return BUCKET_UPCOMING_TODAY
        if starts - now <= timedelta(days=7):
            return BUCKET_THIS_WEEK
    return None


def rank_entries(entries: list[VendorEntry]) -> list[VendorEntry]:
    """Q-3: deterministic and incorruptible. live-and-confirmed > live >
    upcoming-today > this-week, ties broken by verification tier, then property
    approval, then reliability, then distance. Pure — same input, same order."""
    return sorted(
        entries,
        key=lambda e: (
            e.bucket,
            _VERIFY_RANK[e.vendor.verify_status],
            0 if e.appearance.property_approved else 1,
            -e.reliability_rate,
            e.distance_m if e.distance_m is not None else float("inf"),
            str(e.vendor.id),  # final tiebreak so the order is total, never arbitrary
        ),
    )


def _entry_for(db: Session, appearance: Appearance, now: datetime, distance_m=None):
    vendor = db.get(Vendor, appearance.vendor_id)
    if vendor is None or vendor.status != VendorStatus.active or not in_discovery(db, vendor, now):
        return None
    belief = presence(db, vendor.id, appearance.facility_id)
    confirmed_live = bool(belief and belief.present is True)
    bucket = _bucket(appearance, now, confirmed_live)
    if bucket is None:
        return None
    return VendorEntry(
        vendor=vendor,
        appearance=appearance,
        bucket=bucket,
        distance_m=distance_m,
        reliability_rate=reliability(db, vendor.id).rate,
        presence=belief,
        sold_out=is_sold_out(db, vendor.id, appearance.facility_id),
        offerings=list(appearance.offerings),
    )


def _discoverable(now: datetime):
    return (
        Appearance.status.in_((AppearanceStatus.scheduled, AppearanceStatus.live)),
        Appearance.ends_at > now,
    )


def vendors_at_facility(
    db: Session, facility_id, now: datetime | None = None, limit: int = MAX_VENDORS_PER_CARD
) -> list[VendorEntry]:
    """Q-6: the facility card shows at most two vendors; the rest live behind "all
    vendors" in the sheet. Q-7: an empty list means the section does not render at
    all — no "nothing here yet!" filler on the card."""
    now = now or datetime.now(UTC)
    rows = db.scalars(
        select(Appearance).where(Appearance.facility_id == facility_id, *_discoverable(now))
    )
    entries = [e for a in rows if (e := _entry_for(db, a, now)) is not None]
    ranked = rank_entries(entries)
    return ranked[:limit] if limit else ranked


# AI-CONTEXT: §11.3 "presets over filters, one More-filters sheet". These narrow
# what is ALREADY discoverable; none of them can widen it. A filter is applied to the
# output of `_discoverable` + `rank_entries`, never in place of either, so no filter
# can surface a lapsed appearance, a suspended vendor, or anything the §E1.9 quality
# laws exclude — the worst a filter can do is show a driver less.
#
# `q` matches the vendor's name and their DISH names, because "tamales" is what a
# driver types, not the name of the cook. It is bounded by the caller's viewport or
# corridor exactly as the unfiltered query is: an unbounded food search would be
# expensive and useless at 3am, and an empty result must mean "none in this view".
def _matches_query(entry: "VendorEntry", needle: str) -> bool:
    haystack = " ".join(
        [entry.vendor.name, *(o.name for o in entry.offerings)]
    ).casefold()
    return needle.casefold() in haystack


def _matches_language(entry: "VendorEntry", language: str) -> bool:
    return language.casefold() in {str(x).casefold() for x in (entry.vendor.languages or [])}


def _matches_halal(entry: "VendorEntry", halal: str) -> bool:
    """`self_declared` includes `certified`, because a driver asking for halal wants
    both rungs — the label is what distinguishes them, not the filter."""
    claim = entry.vendor.halal_claim
    if halal == HalalClaim.certified.value:
        return claim == HalalClaim.certified
    return claim in (HalalClaim.self_declared, HalalClaim.certified)


def apply_filters(
    entries: list["VendorEntry"],
    q: str | None = None,
    language: str | None = None,
    halal: str | None = None,
) -> list["VendorEntry"]:
    out = entries
    if q and q.strip():
        out = [e for e in out if _matches_query(e, q.strip())]
    if language:
        out = [e for e in out if _matches_language(e, language)]
    if halal:
        out = [e for e in out if _matches_halal(e, halal)]
    return out


def allowed_halal_claim(db: Session, vendor: Vendor, wanted: HalalClaim) -> HalalClaim:
    """`certified` cannot be self-awarded. It requires an APPROVED halal_cert document,
    exactly as `verified` requires reviewed paperwork — a rung a vendor could simply
    select would mean nothing to the driver reading it (§23 tiers)."""
    if wanted != HalalClaim.certified:
        return wanted
    approved = any(
        d.doc_kind == DocumentKind.halal_cert
        and d.review_status == DocumentReviewStatus.approved
        for d in vendor.documents
    )
    return HalalClaim.certified if approved else HalalClaim.self_declared


def appearances_in_bbox(
    db: Session,
    min_lat,
    min_lon,
    max_lat,
    max_lon,
    now: datetime | None = None,
    q: str | None = None,
    language: str | None = None,
    halal: str | None = None,
    origin_lat: float | None = None,
    origin_lon: float | None = None,
) -> list[VendorEntry]:
    """Feeds the map's food badge. Bounded by the viewport, so a continental pan
    returns the facilities in view and nothing more.

    The ORIGIN is optional and the distance is null without it. A driver who has not
    shared a location must see no distance rather than one measured from a guess —
    and until this argument existed the map's entries carried no distance at all,
    which left Q-3's last tie-breaker permanently unreachable (see rank_entries)."""
    now = now or datetime.now(UTC)
    facilities = {
        f.id: f for f in facility_registry.in_bbox(db, min_lat, min_lon, max_lat, max_lon)
    }
    if not facilities:
        return []
    distances = (
        facility_registry.facility_distances(db, list(facilities), origin_lat, origin_lon)
        if origin_lat is not None and origin_lon is not None
        else {}
    )
    rows = db.scalars(
        select(Appearance).where(Appearance.facility_id.in_(list(facilities)), *_discoverable(now))
    )
    entries = [
        e
        for a in rows
        if (e := _entry_for(db, a, now, distance_m=distances.get(a.facility_id))) is not None
    ]
    # ranked FIRST, then narrowed: a filter must not be able to reorder anything (Q-3)
    return apply_filters(rank_entries(entries), q=q, language=language, halal=halal)


def corridor_vendors(
    db: Session,
    account_id,
    origin_lat: float,
    origin_lon: float,
    heading_deg: float,
    max_distance_m: float = 64000,
    now: datetime | None = None,
    limit: int = MAX_CORRIDOR_VENDORS,
    q: str | None = None,
    language: str | None = None,
    halal: str | None = None,
) -> list[VendorEntry]:
    """Appearances ahead on the driver's heading. The corridor geometry itself comes
    from M1's public interface (M8 exposes no corridor primitive), so M13 adds the
    vendor layer without duplicating any geo maths. Q-6 caps this at three."""
    now = now or datetime.now(UTC)
    ahead = m1.corridor_view(db, account_id, origin_lat, origin_lon, heading_deg, max_distance_m)
    distances = {c.facility_id: c.distance_m for c in ahead}
    if not distances:
        return []
    rows = db.scalars(
        select(Appearance).where(Appearance.facility_id.in_(list(distances)), *_discoverable(now))
    )
    entries = [
        e
        for a in rows
        if (e := _entry_for(db, a, now, distance_m=distances.get(a.facility_id))) is not None
    ]
    # filters set while STOPPED still shape what the corridor shows while moving —
    # that is the whole point of them persisting (§11.4: no keyboard while driving)
    narrowed = apply_filters(rank_entries(entries), q=q, language=language, halal=halal)
    return narrowed[:limit]


def vendor_detail(db: Session, vendor_id, now: datetime | None = None) -> dict | None:
    """Everything the vendor sheet renders. Reliability is shown as the raw pair
    ("shows up 19 of 20") rather than a percentage — a fraction carries its own
    sample size, and a lone "95%" over 2 appearances would overstate what we know."""
    now = now or datetime.now(UTC)
    vendor = resolve_vendor(db, vendor_id)
    if vendor is None:
        return None
    upcoming = rank_entries(
        [
            e
            for a in db.scalars(
                select(Appearance).where(Appearance.vendor_id == vendor.id, *_discoverable(now))
            )
            if (e := _entry_for(db, a, now)) is not None
        ]
    )
    score = reliability(db, vendor.id)
    return {
        "vendor": vendor,
        "appearances": upcoming,
        "reliability": score,
        "in_discovery": in_discovery(db, vendor, now),
    }
