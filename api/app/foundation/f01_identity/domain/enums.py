import enum


class MethodType(enum.Enum):
    password = "password"
    oauth = "oauth"
    otp_email = "otp_email"
    otp_sms = "otp_sms"
    # AI-CONTEXT: E3 §E3.2 (D14). The registry's own header predicted this — "social OAuth
    # and email/SMS OTP slot in later with ZERO account/session-model rework" — and
    # Telegram is the first method to take it up. One account has many AuthMethod rows, so
    # a driver who starts in Telegram and adds a password later merges nothing, because
    # nothing was ever separate.
    telegram = "telegram"


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
