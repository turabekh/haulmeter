"""AI-CONTEXT: M1's lot-status prompt, in six languages (finding N-02).

The one P1 M1 sends. `{name}` is a facility's own name and is NOT translated — a place is
called what it is called, and "Pilot Travel Center" does not become anything else in
Spanish. The fallback when a facility has no name IS translated, because "this stop" is
product copy rather than a name.

PROVENANCE: as in the other N-02 tables — nouns grounded in `ui/src/core/i18n/*`, sentence
forms authored here, phrasing wants a native-speaker pass.
"""

KEY_PREFIX = "m01.alert."
DEFAULT_LOCALE_KEY = "en"

ALERT_MESSAGES: dict[str, dict[str, str]] = {
    "lot_status.title": {
        "en": "How's the lot at {name}?",
        "es": "¿Cómo está el estacionamiento en {name}?",
        "ru": "Как парковка в {name}?",
        "uz": "{name} dagi to'xtash joyi qanday?",
        "so": "Sidee ayay baarkinku ku tahay {name}?",
        "pa": "{name} 'ਤੇ ਪਾਰਕਿੰਗ ਕਿਵੇਂ ਹੈ?",
    },
    "lot_status.body": {
        "en": "One tap helps the next driver find a spot.",
        "es": "Un toque ayuda al siguiente conductor a encontrar lugar.",
        "ru": "Одно нажатие поможет следующему водителю найти место.",
        "uz": "Bitta bosish keyingi haydovchiga joy topishga yordam beradi.",
        "so": "Hal taabasho waxay ka caawinaysaa darawalka xiga inuu meel helo.",
        "pa": "ਇੱਕ ਟੈਪ ਅਗਲੇ ਡਰਾਈਵਰ ਨੂੰ ਥਾਂ ਲੱਭਣ ਵਿੱਚ ਮਦਦ ਕਰਦਾ ਹੈ।",
    },
    "lot_status.this_stop": {
        "en": "this stop",
        "es": "esta parada",
        "ru": "этой остановке",
        "uz": "bu to'xtash",
        "so": "joogsigan",
        "pa": "ਇਸ ਸਟਾਪ",
    },
}
