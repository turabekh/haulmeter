"""AI-CONTEXT: Telegram identity verification (PRD Extension E3 §E3.2, D14).

TWO ENTRY POINTS, TWO DIFFERENT SECRET DERIVATIONS, AND CONFUSING THEM IS THE BUG THIS
FILE EXISTS TO PREVENT. Telegram documents them separately and they are not
interchangeable:

· **Login Widget** (the browser PWA):  secret = SHA256(bot_token)
· **Mini App `initData`** (opened inside Telegram):
      secret = HMAC_SHA256(key="WebAppData", msg=bot_token)

Both then compare HMAC_SHA256(data_check_string, secret) against the supplied `hash`,
where data_check_string is every field except `hash`, as `key=value`, sorted by key,
joined with newlines. A implementation that derives the secret one way and validates the
other accepts NOTHING — or, if the two are ever made to agree, accepts anything. The test
suite asserts a vector valid for one path is REJECTED by the other, which is the only
assertion that actually distinguishes them.

AN UNSET BOT TOKEN REFUSES LOUDLY. It does not return False, and it does not fall back to
anything. This inverts the platform's own habit on purpose — F9's model provider and F1's
authority verifier both degrade to a deterministic Fake when their key is absent, which is
right for those because a fake parse is visibly a fake parse. Here the key IS the
verification: with no bot token there is no way to tell a real Telegram user from a
forged payload, and a silent `False` would read to an operator as "that driver typed
something wrong" while the real answer is "this deployment cannot authenticate anyone."
E3 §E3.4.5 states the rule; audit F-02's shape is the precedent.
"""

import hashlib
import hmac
import time
from urllib.parse import parse_qsl

from app.core.config import get_settings

# a Telegram auth payload older than this is refused. Telegram's own guidance is to check
# `auth_date`; a day is generous for a driver who opened the widget and got interrupted,
# and short enough that a leaked payload is not a permanent credential.
MAX_AUTH_AGE_SECONDS = 86_400


class TelegramAuthUnavailable(RuntimeError):
    """No bot token is configured — this deployment cannot verify anyone."""


class TelegramAuthInvalid(ValueError):
    """The payload did not verify: wrong hash, tampered field, or too old."""


def is_configured() -> bool:
    return bool(get_settings().telegram_bot_token)


def _bot_token() -> str:
    token = get_settings().telegram_bot_token
    if not token:
        raise TelegramAuthUnavailable(
            "TELEGRAM_BOT_TOKEN is not set: Telegram sign-in cannot be verified in this "
            "deployment. This refuses rather than degrading — an unverified Telegram "
            "payload is an unauthenticated one (E3 §E3.4.5)."
        )
    return token


def data_check_string(fields: dict[str, str]) -> str:
    """Every field except `hash`, as `key=value`, sorted by key, newline-joined."""
    return "\n".join(f"{k}={fields[k]}" for k in sorted(fields) if k != "hash")


def _login_widget_secret(bot_token: str) -> bytes:
    return hashlib.sha256(bot_token.encode()).digest()


def _mini_app_secret(bot_token: str) -> bytes:
    # NOTE THE ARGUMENT ORDER: the KEY is the literal "WebAppData" and the MESSAGE is the
    # bot token. Reversed, this produces a stable-looking digest that never matches.
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def _verify(fields: dict[str, str], secret: bytes, *, now: float | None = None) -> dict[str, str]:
    supplied = fields.get("hash")
    if not supplied:
        raise TelegramAuthInvalid("payload carries no hash")

    expected = hmac.new(
        secret, data_check_string(fields).encode(), hashlib.sha256
    ).hexdigest()
    # constant-time: a comparison that leaks its position leaks the hash a byte at a time
    if not hmac.compare_digest(supplied, expected):
        raise TelegramAuthInvalid("hash does not match the payload")

    auth_date = fields.get("auth_date")
    if auth_date is None:
        raise TelegramAuthInvalid("payload carries no auth_date")
    try:
        issued = int(auth_date)
    except ValueError as exc:
        raise TelegramAuthInvalid("auth_date is not an integer") from exc

    current = time.time() if now is None else now
    if current - issued > MAX_AUTH_AGE_SECONDS:
        raise TelegramAuthInvalid("payload is too old")

    return fields


def check_login_widget(fields: dict[str, str], *, now: float | None = None) -> dict[str, str]:
    """Validate a Telegram Login Widget payload from the browser PWA."""
    return _verify(dict(fields), _login_widget_secret(_bot_token()), now=now)


def check_mini_app_init_data(init_data: str, *, now: float | None = None) -> dict[str, str]:
    """Validate a Telegram Mini App `initData` query string.

    Parsed with `keep_blank_values=True`: a blank field is part of the signed payload, and
    dropping it changes the data_check_string and fails a legitimate user.
    """
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    return _verify(fields, _mini_app_secret(_bot_token()), now=now)


def telegram_user_id(fields: dict[str, str]) -> str:
    """The stable identifier a Telegram account is keyed by.

    Login Widget delivers `id` at the top level; a Mini App delivers a JSON `user` object
    whose `id` is the same number. Callers get one shape.
    """
    if "id" in fields:
        return str(fields["id"])
    user = fields.get("user")
    if user:
        import json

        try:
            return str(json.loads(user)["id"])
        except (ValueError, KeyError) as exc:
            raise TelegramAuthInvalid("user field is not a JSON object with an id") from exc
    raise TelegramAuthInvalid("payload identifies no user")
