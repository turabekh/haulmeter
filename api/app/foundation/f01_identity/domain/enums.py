import enum


class MethodType(enum.Enum):
    password = "password"
    oauth = "oauth"
    otp_email = "otp_email"
    otp_sms = "otp_sms"


class Role(enum.Enum):
    driver = "driver"
    fleet_admin = "fleet_admin"
    property_owner = "property_owner"
    platform_admin = "platform_admin"
    vendor = "vendor"


class OrgType(enum.Enum):
    fleet = "fleet"
    property_business = "property_business"


class AuthorityType(enum.Enum):
    own_mc = "own_mc"
    leased = "leased"
    company = "company"


class VerifyStatus(enum.Enum):
    unverified = "unverified"  # never attempted
    verified = "verified"  # FMCSA confirms an active carrier
    failed = "failed"  # not found / not authorized to operate
