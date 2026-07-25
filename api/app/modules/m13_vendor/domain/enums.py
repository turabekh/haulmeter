import enum


class VendorType(enum.Enum):
    food_mobile = "food_mobile"  # the founding case: a cook working truck stops
    service_center = "service_center"  # a fixed repair / tire / wash business


class VendorVerifyStatus(enum.Enum):
    """The ladder is displayed to drivers verbatim, so each rung must mean exactly
    what it says (§11.7). `documents_on_file` means paperwork was uploaded and an
    admin looked at it — never that anyone inspected a kitchen."""

    unverified = "unverified"
    documents_on_file = "documents_on_file"
    verified = "verified"


class VendorStatus(enum.Enum):
    active = "active"
    suspended = "suspended"  # admin action; leaves discovery entirely
    merged = "merged"  # Q-5: a duplicate folded into the canonical vendor


class MemberRole(enum.Enum):
    owner = "owner"
    helper = "helper"


class HalalClaim(enum.Enum):
    """AI-CONTEXT: what the VENDOR claims about halal, structured so it can be
    filtered on — and nothing more.

    The free-text `halal_disclosure` stays and is still shown verbatim; §23 already
    settled that the platform makes no halal claim of its own, and parsing a cook's
    sentence to decide who counts would be exactly that. This field is the cook's own
    answer to a closed question, which is a different act from us interpreting them.

    Each rung means precisely what it says, like the verification ladder:
    · not_claimed   — the vendor does not claim halal. A complete, honest answer.
    · self_declared — the VENDOR says halal. Nobody has checked. The driver-facing
                      label carries "vendor says", never a bare "Halal".
    · certified     — a halal certificate is on file AND approved. Reachable only
                      when an approved halal_cert document exists, so it cannot be
                      self-awarded (see `allowed_halal_claim`).
    """

    not_claimed = "not_claimed"
    self_declared = "self_declared"
    certified = "certified"


class DocumentKind(enum.Enum):
    license = "license"
    insurance = "insurance"
    halal_cert = "halal_cert"


class DocumentReviewStatus(enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class AppearanceStatus(enum.Enum):
    """Q-1: every terminal state removes the appearance from discovery, so the map
    can never show a driver a meal they cannot actually buy."""

    scheduled = "scheduled"
    live = "live"
    done = "done"  # the window ended
    cancelled = "cancelled"  # the vendor called it off
    lapsed = "lapsed"  # drivers reported "not here" and the belief held


class ReviewStatus(enum.Enum):
    """FR5: a vendor review publishes immediately and is hidden only when reported
    (Q-8). That differs from the M2 facility review, which is queued BEFORE
    publication — a facility scorecard carries defamation exposure (PRD §13) that a
    driver's note about a meal does not."""

    visible = "visible"
    hidden_pending = "hidden_pending"  # reported, awaiting F14 review
    removed = "removed"  # report upheld


class PromotionStatus(enum.Enum):
    active = "active"
    expired = "expired"  # Q-1 spirit: a promotion past its window vanishes
    cancelled = "cancelled"
    hidden_pending = "hidden_pending"
    removed = "removed"


class PromotionScope(enum.Enum):
    own_appearances = "own_appearances"  # wherever this vendor is scheduled
    claimed_facility = "claimed_facility"  # the service centre they claimed (FR7)


class ClaimStatus(enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    disputed = "disputed"  # a second claimant appeared — F14 decides


class ModerationReason(enum.Enum):
    """Why something was reported. `false_property_attestation` exists because PRD
    §17 Q11 resolved that a vendor's self-attestation of property permission is
    sufficient for ranked placement — which is only defensible if a demonstrated
    false attestation is actionable."""

    spam = "spam"
    offensive = "offensive"
    false_information = "false_information"
    false_property_attestation = "false_property_attestation"
    impersonation = "impersonation"
    other = "other"
