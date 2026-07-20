"""AI-CONTEXT: Public interface for F15 Localization & Language Services.

The ONLY import surface other packages may use to reach F15 (import-linter
enforced). Six launch locales ship together; counterparty artifacts are always
English; units are always imperial; trucking jargon stays English via the
glossary. Hard dependency for F8 templates, F9 prompts, M11. Consumed by every
module.
"""

from .domain.enums import LocaleAudience
from .domain.models import GlossaryTerm, MessageCatalog
from .domain.service import (
    DEFAULT_GLOSSARY,
    DEFAULT_LOCALE,
    LAUNCH_LOCALES,
    NEXT_CANDIDATE_LOCALE,
    UNIT_SYSTEM,
    UnsupportedLocale,
    get_message,
    get_user_locale,
    is_complete,
    is_glossary_term,
    is_launch_locale,
    list_glossary,
    missing_locales,
    present_locales,
    register_glossary_term,
    register_message,
    resolve_locale,
    seed_default_glossary,
    set_user_locale,
)

__all__ = [
    "LocaleAudience",
    "GlossaryTerm",
    "MessageCatalog",
    "DEFAULT_GLOSSARY",
    "DEFAULT_LOCALE",
    "LAUNCH_LOCALES",
    "NEXT_CANDIDATE_LOCALE",
    "UNIT_SYSTEM",
    "UnsupportedLocale",
    "get_message",
    "get_user_locale",
    "is_complete",
    "is_glossary_term",
    "is_launch_locale",
    "list_glossary",
    "missing_locales",
    "present_locales",
    "register_glossary_term",
    "register_message",
    "resolve_locale",
    "seed_default_glossary",
    "set_user_locale",
]
