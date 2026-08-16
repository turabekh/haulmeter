"""AI-CONTEXT: Telegram payload verification (E3 §E3.2). No live bot required.

THE VECTORS ARE BUILT INDEPENDENTLY IN THIS FILE rather than by calling the production
helper, because a test that signs with the code under test agrees with that code whatever
it does — including a wrong sort order, a wrong separator, or the wrong secret derivation.
`_sign_independently` below spells the algorithm out from Telegram's documentation.

The sharpest assertion here is `test_a_login_widget_vector_is_rejected_by_the_mini_app_path`.
The two entry points derive their secret DIFFERENTLY — SHA256(bot_token) versus
HMAC(key="WebAppData", msg=bot_token) — and mixing them is the classic implementation bug.
Every other test in this file would pass with both paths wired to the same derivation.
"""

import hashlib
import hmac
import time
from urllib.parse import urlencode

import pytest

from app.core.config import get_settings
from app.foundation.f01_identity.domain import telegram

BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"


@pytest.fixture(autouse=True)
def _bot_token_set(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_TOKEN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _sign_independently(fields: dict, secret: bytes) -> str:
    """Telegram's algorithm, written out here rather than imported from the code."""
    parts = []
    for key in sorted(fields):
        if key != "hash":
            parts.append(f"{key}={fields[key]}")
    check_string = "\n".join(parts)
    return hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()


def _widget_secret(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _mini_app_secret(token: str) -> bytes:
    return hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()


def _widget_payload(**over):
    fields = {
        "id": "77777777",
        "first_name": "Aziz",
        "username": "aziz_driver",
        "auth_date": str(int(time.time())),
    }
    fields.update(over)
    fields["hash"] = _sign_independently(fields, _widget_secret(BOT_TOKEN))
    return fields


def _mini_app_init_data(**over):
    fields = {
        "user": '{"id":77777777,"first_name":"Aziz"}',
        "auth_date": str(int(time.time())),
        "query_id": "AAABBBCCC",
    }
    fields.update(over)
    fields["hash"] = _sign_independently(fields, _mini_app_secret(BOT_TOKEN))
    return urlencode(fields)


# --- the happy paths ---------------------------------------------------------------


def test_a_valid_login_widget_payload_verifies():
    fields = _widget_payload()
    assert telegram.check_login_widget(fields)["id"] == "77777777"
    assert telegram.telegram_user_id(fields) == "77777777"


def test_a_valid_mini_app_payload_verifies():
    init_data = _mini_app_init_data()
    fields = telegram.check_mini_app_init_data(init_data)
    assert telegram.telegram_user_id(fields) == "77777777"


# --- the assertion that actually distinguishes the two paths -----------------------


def test_a_login_widget_vector_is_rejected_by_the_mini_app_path():
    """The two secret derivations are different, and this is what proves it.

    If both paths were wired to the same derivation — the classic bug — every other test
    in this file would still pass and this one would fail.
    """
    fields = _widget_payload()
    with pytest.raises(telegram.TelegramAuthInvalid):
        telegram.check_mini_app_init_data(urlencode(fields))


def test_a_mini_app_vector_is_rejected_by_the_login_widget_path():
    init_data = _mini_app_init_data()
    fields = dict(pair.split("=", 1) for pair in init_data.split("&"))
    with pytest.raises(telegram.TelegramAuthInvalid):
        telegram.check_login_widget(fields)


# --- refusals ----------------------------------------------------------------------


def test_a_tampered_field_is_rejected():
    fields = _widget_payload()
    fields["id"] = "88888888"  # someone else's account, same signature
    with pytest.raises(telegram.TelegramAuthInvalid):
        telegram.check_login_widget(fields)


def test_a_payload_signed_with_another_bot_token_is_rejected():
    fields = {
        "id": "77777777",
        "first_name": "Aziz",
        "auth_date": str(int(time.time())),
    }
    fields["hash"] = _sign_independently(fields, _widget_secret("999999:SOME-OTHER-TOKEN"))
    with pytest.raises(telegram.TelegramAuthInvalid):
        telegram.check_login_widget(fields)


def test_a_stale_payload_is_rejected():
    old = int(time.time()) - telegram.MAX_AUTH_AGE_SECONDS - 60
    fields = _widget_payload(auth_date=str(old))
    with pytest.raises(telegram.TelegramAuthInvalid):
        telegram.check_login_widget(fields)


def test_a_payload_with_no_hash_is_rejected():
    fields = _widget_payload()
    del fields["hash"]
    with pytest.raises(telegram.TelegramAuthInvalid):
        telegram.check_login_widget(fields)


# --- the loud refusal (E3 §E3.4.5) -------------------------------------------------


def test_an_unset_bot_token_REFUSES_rather_than_returning_false(monkeypatch):
    """The distinction is the whole point of this test.

    A `False` return would reach an operator as "that driver typed something wrong". The
    truth is "this deployment cannot authenticate anyone", and those need different
    answers — one is a support ticket, the other is a missing environment variable. A
    silent fallback is how a scoring control becomes decorative.
    """
    fields = _widget_payload()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    get_settings.cache_clear()

    with pytest.raises(telegram.TelegramAuthUnavailable):
        telegram.check_login_widget(fields)
    with pytest.raises(telegram.TelegramAuthUnavailable):
        telegram.check_mini_app_init_data(_mini_app_init_data())
    assert telegram.is_configured() is False


def test_an_unset_bot_token_never_accepts_an_unsigned_payload(monkeypatch):
    """The failure mode worth naming: refusing must not become accepting.

    An implementation that skipped verification when no token is configured would let a
    forged payload through, which is worse than any error message.
    """
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    get_settings.cache_clear()

    forged = {"id": "1", "auth_date": str(int(time.time())), "hash": "0" * 64}
    with pytest.raises(telegram.TelegramAuthUnavailable):
        telegram.check_login_widget(forged)
