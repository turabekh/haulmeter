"""AI-CONTEXT: Pluggable auth-method registry (F1, PRD 7.1 / HANDOFF 6).

Launch auth is email/password ONLY, with no activation/verification step
(owner-LOCKED). This registry is the seam that lets social OAuth and email/SMS
OTP slot in later with ZERO account/session-model rework: one account has many
AuthMethod rows, each dispatched to a handler here. Only PasswordHandler is
implemented now; the other method types are registered as NotImplemented seams
so the shape is fixed and callers fail cleanly rather than silently.
"""

from typing import Protocol

from .enums import MethodType
from .security import hash_password, verify_password


class AuthHandler(Protocol):
    def build_secret_ref(self, credential: str) -> str | None: ...

    def verify(self, secret_ref: str | None, credential: str) -> bool: ...


class PasswordHandler:
    def build_secret_ref(self, credential: str) -> str | None:
        return hash_password(credential)

    def verify(self, secret_ref: str | None, credential: str) -> bool:
        if secret_ref is None:
            return False
        return verify_password(secret_ref, credential)


class _NotImplementedHandler:
    def __init__(self, method_type: MethodType) -> None:
        self._method_type = method_type

    def build_secret_ref(self, credential: str) -> str | None:
        raise NotImplementedError(
            f"{self._method_type.value} auth is a reserved seam; not enabled at launch"
        )

    def verify(self, secret_ref: str | None, credential: str) -> bool:
        raise NotImplementedError(
            f"{self._method_type.value} auth is a reserved seam; not enabled at launch"
        )


_REGISTRY: dict[MethodType, AuthHandler] = {
    MethodType.password: PasswordHandler(),
    MethodType.oauth: _NotImplementedHandler(MethodType.oauth),
    MethodType.otp_email: _NotImplementedHandler(MethodType.otp_email),
    MethodType.otp_sms: _NotImplementedHandler(MethodType.otp_sms),
}


def get_handler(method_type: MethodType) -> AuthHandler:
    return _REGISTRY[method_type]


def is_implemented(method_type: MethodType) -> bool:
    return not isinstance(_REGISTRY[method_type], _NotImplementedHandler)
