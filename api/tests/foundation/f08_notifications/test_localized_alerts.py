"""N-02 — driver notifications were English-only, everywhere.

Ten `notify.dispatch` sites across seven modules passed English literal titles and bodies
straight to a driver's push, including M3's detention P0 — the product's most important
driver-facing alert. PRD §7.15's coverage rule names notifications in the same breath as
UI and voice.

The lookup lives in F8 because F8 is what already knows the account: ten call sites
resolving a locale ten times is ten chances to resolve it differently, and the one that
forgot would be invisible.
"""

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify
from app.foundation.f15_localization import public as localization
from app.modules.m01_map.domain import messages as m01_messages
from app.modules.m03_detention.domain import messages as m03_messages
from app.modules.m05_protection.domain import messages as m05_messages
from app.modules.m06_parking.domain import messages as m06_messages
from app.modules.m09_money.domain import messages as m09_messages
from app.modules.m13_vendor.domain import messages as m13_messages

# every module that sends a driver notification, and the table it sends it from
ALERT_TABLES = [
    (m01_messages.KEY_PREFIX, m01_messages.ALERT_MESSAGES),
    (m03_messages.KEY_PREFIX, m03_messages.ALERT_MESSAGES),
    (m05_messages.KEY_PREFIX, m05_messages.ALERT_MESSAGES),
    (m06_messages.KEY_PREFIX, m06_messages.ALERT_MESSAGES),
    (m09_messages.KEY_PREFIX, m09_messages.ALERT_MESSAGES),
    (m13_messages.KEY_PREFIX, m13_messages.ALERT_MESSAGES),
]


def _driver(db, locale=None, email="driver@example.com"):
    account = identity.register_account(db, email, "pw-123456")
    if locale is not None:
        localization.set_user_locale(db, account, locale)
    return account


@pytest.mark.parametrize("prefix,table", ALERT_TABLES, ids=[t[0] for t in ALERT_TABLES])
def test_every_alert_string_exists_in_all_six_launch_locales(db, prefix, table):
    # F15's own rule: "a driver-facing string missing any of them fails CI"
    for key, by_locale in table.items():
        assert set(by_locale) == set(localization.LAUNCH_LOCALES), f"{prefix}{key}"


@pytest.mark.parametrize("prefix,table", ALERT_TABLES, ids=[t[0] for t in ALERT_TABLES])
def test_every_locale_keeps_the_placeholders_english_declares(db, prefix, table):
    """A translated string that dropped `{figure}` would render a P0 about money with no
    money in it, and every other test here would still pass."""
    import re

    for key, by_locale in table.items():
        expected = set(re.findall(r"\{(\w+)\}", by_locale["en"]))
        for locale, text in by_locale.items():
            assert set(re.findall(r"\{(\w+)\}", text)) == expected, f"{prefix}{key} [{locale}]"


def test_localized_text_uses_the_drivers_stored_locale(db):
    driver = _driver(db, "es")
    localization.register_message(db, "probe.key", "es", "Hola {name}")
    localization.register_message(db, "probe.key", "en", "Hello {name}")

    assert notify.localized_text(db, driver.id, "probe.key", "FALLBACK", name="Ana") == "Hola Ana"


def test_localized_text_falls_back_to_the_compiled_default(db):
    # F-17's third option: a notification is the one surface where silence IS the failure
    driver = _driver(db, "es")
    assert (
        notify.localized_text(db, driver.id, "never.registered", "Compiled {n}", n=3)
        == "Compiled 3"
    )


def test_a_driver_with_no_profile_still_gets_a_notification(db):
    # `get_user_locale` reads account.profile, which a fresh account may not have
    driver = _driver(db)
    localization.register_message(db, "probe.key", "en", "English text")
    assert notify.localized_text(db, driver.id, "probe.key", "FALLBACK") == "English text"


def test_a_missing_account_does_not_raise(db):
    import uuid

    assert notify.localized_text(db, uuid.uuid4(), "probe.key", "Fallback") == "Fallback"
