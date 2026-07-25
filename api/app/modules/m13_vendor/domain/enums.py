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
