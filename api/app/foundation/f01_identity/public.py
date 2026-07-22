"""AI-CONTEXT: Public interface for F1 Identity, Access & Organizations.

The ONLY import surface other packages may use to reach F1 (import-linter
enforced). Launch auth is email/password with no activation step; the auth
method registry is the seam for future OAuth/OTP. Consumed by every module.
"""

from .domain.auth_methods import get_handler, is_implemented
from .domain.enums import AuthorityType, MethodType, OrgType, Role, VerifyStatus
from .domain.models import (
    Account,
    AuthMethod,
    AuthSession,
    DriverProfile,
    Organization,
    OrgMembership,
    RoleAttachment,
)
from .domain.service import (
    AUTHORITY_VERIFICATION_FLAG,
    AuthMethodNotEnabled,
    EmailAlreadyRegistered,
    add_auth_method,
    add_membership,
    attach_role,
    authenticate,
    can_invoice,
    create_organization,
    create_session,
    register_account,
    register_authority_verification,
    resolve_session,
    upsert_driver_profile,
    verify_authority,
)
from .domain.verifier import (
    AuthorityVerifier,
    FakeAuthorityVerifier,
    VerificationResult,
    resolve_verifier,
)

__all__ = [
    "Account",
    "AuthMethod",
    "AuthSession",
    "DriverProfile",
    "Organization",
    "OrgMembership",
    "RoleAttachment",
    "AuthorityType",
    "MethodType",
    "OrgType",
    "Role",
    "VerifyStatus",
    "AuthMethodNotEnabled",
    "EmailAlreadyRegistered",
    "AUTHORITY_VERIFICATION_FLAG",
    "add_auth_method",
    "add_membership",
    "attach_role",
    "authenticate",
    "can_invoice",
    "create_organization",
    "create_session",
    "register_account",
    "register_authority_verification",
    "resolve_session",
    "upsert_driver_profile",
    "verify_authority",
    "AuthorityVerifier",
    "FakeAuthorityVerifier",
    "VerificationResult",
    "resolve_verifier",
    "get_handler",
    "is_implemented",
]
