"""AI-CONTEXT: F15 Localization & Language Services (PRD §7.15).

Full multilingual operation is an acquisition wedge, not a compliance checkbox.
Launch locales all ship together; a driver-facing string missing any of them
fails CI (design-prd §12.5 — the client vitest enforces the app-shell bundle;
this is the server catalog analog for F8-rendered strings). Two hard rules live
here: counterparty-facing artifacts are ALWAYS English (US legal/commercial
documents), and units are ALWAYS imperial in every language (US trucking).
Recognized trucking jargon (detention, lumper, rate con, BOL, TONU) stays in
English via the glossary. Per-user locale lives on the F1 profile (PRD §7.15).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f01_identity import public as identity

from .enums import LocaleAudience
from .models import GlossaryTerm, MessageCatalog

LAUNCH_LOCALES = ["en", "es", "pa", "ru", "uz", "so"]
NEXT_CANDIDATE_LOCALE = "am"  # Amharic — designated next, not shipped at launch
DEFAULT_LOCALE = "en"
UNIT_SYSTEM = "imperial"  # miles / gallons / feet-inches, every locale — NEVER localized

DEFAULT_GLOSSARY = ["detention", "lumper", "rate con", "BOL", "TONU", "POD", "HOS", "IFTA"]


class UnsupportedLocale(Exception):
    pass


def is_launch_locale(locale: str) -> bool:
    return locale in LAUNCH_LOCALES


def resolve_locale(audience: LocaleAudience, user_locale: str) -> str:
    if audience == LocaleAudience.counterparty:
        return "en"
    return user_locale if is_launch_locale(user_locale) else DEFAULT_LOCALE


# --- Per-user locale (stored on the F1 profile) ---
def set_user_locale(db: Session, account, locale: str):
    if not is_launch_locale(locale):
        raise UnsupportedLocale(locale)
    return identity.upsert_driver_profile(db, account, locale=locale)


def get_user_locale(db: Session, account) -> str:
    profile = account.profile
    return profile.locale if profile is not None else DEFAULT_LOCALE


# --- Message catalog registry ---
def register_message(db: Session, key: str, locale: str, text: str) -> MessageCatalog:
    existing = db.scalar(
        select(MessageCatalog).where(MessageCatalog.key == key, MessageCatalog.locale == locale)
    )
    if existing is not None:
        existing.text = text
        db.flush()
        return existing
    entry = MessageCatalog(key=key, locale=locale, text=text)
    db.add(entry)
    db.flush()
    return entry


def get_message(db: Session, key: str, locale: str, fallback_to_default: bool = True) -> str | None:
    entry = db.scalar(
        select(MessageCatalog).where(MessageCatalog.key == key, MessageCatalog.locale == locale)
    )
    if entry is not None:
        return entry.text
    if fallback_to_default and locale != DEFAULT_LOCALE:
        return get_message(db, key, DEFAULT_LOCALE, fallback_to_default=False)
    return None


def present_locales(db: Session, key: str) -> list[str]:
    return sorted(db.scalars(select(MessageCatalog.locale).where(MessageCatalog.key == key)))


def missing_locales(db: Session, key: str) -> list[str]:
    present = set(present_locales(db, key))
    return [loc for loc in LAUNCH_LOCALES if loc not in present]


def is_complete(db: Session, key: str) -> bool:
    return not missing_locales(db, key)


# --- Trucking glossary (jargon stays English) ---
def register_glossary_term(
    db: Session, term: str, keep_english: bool = True, definition: str | None = None
) -> GlossaryTerm:
    entry = db.get(GlossaryTerm, term)
    if entry is None:
        entry = GlossaryTerm(term=term, keep_english=keep_english, definition=definition)
        db.add(entry)
    else:
        entry.keep_english = keep_english
        entry.definition = definition
    db.flush()
    return entry


def seed_default_glossary(db: Session) -> int:
    for term in DEFAULT_GLOSSARY:
        register_glossary_term(db, term)
    return len(DEFAULT_GLOSSARY)


def is_glossary_term(db: Session, term: str) -> bool:
    entry = db.get(GlossaryTerm, term)
    return entry is not None and entry.keep_english


def list_glossary(db: Session) -> list[GlossaryTerm]:
    return list(db.scalars(select(GlossaryTerm).order_by(GlossaryTerm.term)))
