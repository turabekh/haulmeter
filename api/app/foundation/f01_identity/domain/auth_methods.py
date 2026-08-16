"""AI-CONTEXT: Pluggable auth-method registry (F1, PRD 7.1 / HANDOFF 6).

Launch auth is email/password ONLY, with no activation/verification step
(owner-LOCKED). This registry is the seam that lets social OAuth and email/SMS
OTP slot in later with ZERO account/session-model rework: one account has many
AuthMethod rows, each dispatched to a handler here. Only PasswordHandler is
implemented now; the other method types are registered as NotImplemented seams
so the shape is fixed and callers fail cleanly rather than silently.
"""

from typing import Protocol

from . import security, telegram
from .enums import MethodType


class AuthHandler(Protocol):
    def build_secret_ref(self, credential: str) -> str | None: ...

    def verify(self, secret_ref: str | None, credential: str) -> bool: ...


class PasswordHandler:
    """AI-CONTEXT: the concurrency bound is acquired HERE, not by the caller (F1-6).

    `authenticate` used to acquire it around its own `verify` call, which protected exactly
    one call site — and `build_secret_ref`, reached unauthenticated from registration at a
    cost per request at least equal to a verify, had no bound at all. Putting it on the
    operation instead of the caller is what makes that class of omission impossible.

    Creation and verification draw on SEPARATE pools so a registration flood sheds only
    registrations; see `security.py` for why that matters more than it sounds.
    """

    def build_secret_ref(self, credential: str) -> str | None:
        # resolved through the module, not bound at import: the pool is a live object a
        # test (or a future config path) must be able to substitute
        with security.slot(security.HASH_SLOTS):
            return security.hash_password(credential)

    def verify(self, secret_ref: str | None, credential: str) -> bool:
        if secret_ref is None:
            return False
        with security.slot(security.VERIFY_SLOTS):
            return security.verify_password(secret_ref, credential)


class TelegramHandler:
    """AI-CONTEXT: E3 §E3.2 — the first method to take up this registry's own promise.

    It does not fit the password shape and does not pretend to. There is NO per-account
    secret: identity is proven by a payload Telegram signed with the bot token, so
    `build_secret_ref` returns None and the AuthMethod row's `identifier` (the Telegram
    user id) is the whole record.

    `verify` RAISES rather than returning False when the bot token is unset, which departs
    from a bool-returning protocol on purpose — `_NotImplementedHandler` below establishes
    that raising from here is how this registry says "not possible" as opposed to "not
    correct". False means "that is not the right credential", and an operator reading it
    would go looking for a driver's mistake instead of a missing environment variable.
    """

    def build_secret_ref(self, credential: str) -> str | None:
        return None

    def verify(self, secret_ref: str | None, credential: str) -> bool:
        # `credential` is a Mini App initData query string. The Login Widget path carries
        # a field dict and is verified through `telegram.check_login_widget` directly by
        # the route, because the two payloads are not the same shape and flattening them
        # into one string here is how the two secret derivations get confused.
        telegram.check_mini_app_init_data(credential)
        return True


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
    MethodType.telegram: TelegramHandler(),
}


def get_handler(method_type: MethodType) -> AuthHandler:
    return _REGISTRY[method_type]


def is_implemented(method_type: MethodType) -> bool:
    return not isinstance(_REGISTRY[method_type], _NotImplementedHandler)
