import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f15_localization import public as loc


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def test_six_launch_locales_ship_together(db):
    assert loc.LAUNCH_LOCALES == ["en", "es", "pa", "ru", "uz", "so"]
    assert loc.NEXT_CANDIDATE_LOCALE == "am"
    assert loc.UNIT_SYSTEM == "imperial"


def test_counterparty_is_always_english(db):
    assert loc.resolve_locale(loc.LocaleAudience.counterparty, "es") == "en"
    assert loc.resolve_locale(loc.LocaleAudience.counterparty, "uz") == "en"


def test_driver_gets_own_locale_else_default(db):
    assert loc.resolve_locale(loc.LocaleAudience.driver, "ru") == "ru"
    assert loc.resolve_locale(loc.LocaleAudience.driver, "fr") == "en"  # not a launch locale


def test_user_locale_persists_on_profile(db):
    account = _account(db)
    loc.set_user_locale(db, account, "uz")
    db.refresh(account)
    assert loc.get_user_locale(db, account) == "uz"


def test_unsupported_user_locale_rejected(db):
    account = _account(db)
    with pytest.raises(loc.UnsupportedLocale):
        loc.set_user_locale(db, account, "fr")


def test_catalog_completeness_across_six_locales(db):
    key = "notification.detention_started"
    for locale in loc.LAUNCH_LOCALES[:-1]:
        loc.register_message(db, key, locale, f"[{locale}] Detention started")
    assert loc.is_complete(db, key) is False
    assert loc.missing_locales(db, key) == ["so"]
    loc.register_message(db, key, "so", "[so] Detention started")
    assert loc.is_complete(db, key) is True


def test_get_message_falls_back_to_default(db):
    key = "system.offline"
    loc.register_message(db, key, "en", "Offline — everything saves to your phone")
    assert loc.get_message(db, key, "en").startswith("Offline")
    # missing locale falls back to default (en)
    assert loc.get_message(db, key, "so").startswith("Offline")
    assert loc.get_message(db, "unknown.key", "en") is None


def test_glossary_keeps_trucking_jargon_english(db):
    count = loc.seed_default_glossary(db)
    assert count == len(loc.DEFAULT_GLOSSARY)
    assert loc.is_glossary_term(db, "detention") is True
    assert loc.is_glossary_term(db, "lumper") is True
    assert loc.is_glossary_term(db, "hello") is False
    assert len(loc.list_glossary(db)) == count
