"""AI-CONTEXT: M13's vendor alerts, in six languages (finding N-02).

Two of M13's three dispatch sites are here. THE THIRD IS DELIBERATELY ABSENT and that is
the point worth recording: `promotions.py` sends the vendor's own `promotion.text` as the
body and the vendor's own name as the title. Both are DATA — a person's words — not product
copy, and machine-translating what a cook wrote about their own food would be inventing
speech on their behalf. It stays as written, in whatever language the vendor wrote it.

`{name}` (vendor) and `{place}` (facility) are names for the same reason. `{when}` is a
weekday and time rendered by the caller with `%a`/`%H:%M`, so the weekday abbreviation is
still English — recorded in N-02's row rather than hidden, because localizing it needs a
month/day table or a dependency, and that is a decision rather than a fix.

M13's food half has been dark in dev and production since session 114, so these are latent
today. Fixed anyway: a flag that gets switched on should not switch on a defect with it.

PROVENANCE: as in the other N-02 tables; phrasing wants a native-speaker pass.
"""

KEY_PREFIX = "m13.alert."
DEFAULT_LOCALE_KEY = "en"

ALERT_MESSAGES: dict[str, dict[str, str]] = {
    "vendor_cancelled.title": {
        "en": "{name} cancelled",
        "es": "{name} canceló",
        "ru": "{name} отменил",
        "uz": "{name} bekor qildi",
        "so": "{name} waa la joojiyay",
        "pa": "{name} ਨੇ ਰੱਦ ਕੀਤਾ",
    },
    "vendor_cancelled.body": {
        "en": "Not at {place} tonight",
        "es": "No está en {place} esta noche",
        "ru": "Сегодня вечером не в {place}",
        "uz": "Bugun kechqurun {place} da emas",
        "so": "Caawa kuma joogo {place}",
        "pa": "ਅੱਜ ਰਾਤ {place} 'ਤੇ ਨਹੀਂ",
    },
    "vendor_published.title": {
        "en": "{name} published",
        "es": "{name} publicó",
        "ru": "{name} опубликовал",
        "uz": "{name} e'lon qildi",
        "so": "{name} wuu daabacay",
        "pa": "{name} ਨੇ ਪ੍ਰਕਾਸ਼ਿਤ ਕੀਤਾ",
    },
    "vendor_published.body": {
        "en": "{place} · {when}",
        "es": "{place} · {when}",
        "ru": "{place} · {when}",
        "uz": "{place} · {when}",
        "so": "{place} · {when}",
        "pa": "{place} · {when}",
    },
    "vendor.the_stop": {
        "en": "the stop",
        "es": "la parada",
        "ru": "остановке",
        "uz": "to'xtash joyi",
        "so": "joogsiga",
        "pa": "ਸਟਾਪ",
    },
    "vendor.a_stop": {
        "en": "A stop",
        "es": "Una parada",
        "ru": "Остановка",
        "uz": "Bir to'xtash joyi",
        "so": "Joogsi",
        "pa": "ਇੱਕ ਸਟਾਪ",
    },
}
