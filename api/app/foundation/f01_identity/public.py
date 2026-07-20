"""AI-CONTEXT: Public interface for F1 Identity, Access & Organizations.

The ONLY import surface other packages may use to reach F1 (import-linter
enforced). Launch auth is email/password with no activation step; the auth
method registry is the seam for future OAuth/OTP. Consumed by every module.
"""
from .domain.auth_methods import get_handler, is_implemented
from .domain.enums import AuthorityType, MethodType, OrgType, Role
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
    resolve_session,
    upsert_driver_profile,
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
    "AuthMethodNotEnabled",
    "EmailAlreadyRegistered",
    "add_auth_method",
    "add_membership",
    "attach_role",
    "authenticate",
    "can_invoice",
    "create_organization",
    "create_session",
    "register_account",
    "resolve_session",
    "upsert_driver_profile",
    "get_handler",
    "is_implemented",
]
