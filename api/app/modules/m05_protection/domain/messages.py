"""AI-CONTEXT: M5's driver alerts, in six languages (finding N-02).

Two notifications, and the LABELS THEY INTERPOLATE, which is the part worth noticing.
`Missing: {labels}` and `{label} expires in {offset} days` both splice an enumerable
English noun into the sentence, so translating only the sentence would produce
"Falta: pickup photos" — an English fragment inside a Spanish alert, which is exactly the
defect N-01 fixed in the voice handoffs. The labels are enumerable, so they are translated
too.

`BOL` stays English in every locale: F15's DEFAULT_GLOSSARY rules it trucking jargon, and
the launch catalogues already keep it. So do `CDL`, `rate con` and `POD` for the same
reason. The credential nouns that are not jargon — insurance, permit — are translated.

The document-expiry date is rendered by the caller with `%d %b`, which is English month
abbreviations. That is NOT fixed here and is recorded in N-02's row rather than silently
left: a localized month name needs either babel or a per-locale month table, and adding a
dependency for it is a decision rather than a fix.

PROVENANCE: as in `m03_detention/domain/messages.py` — nouns grounded in
`ui/src/core/i18n/*`, sentence forms authored here, phrasing wants a native-speaker pass.
"""

KEY_PREFIX = "m05.alert."
DEFAULT_LOCALE_KEY = "en"

ALERT_MESSAGES: dict[str, dict[str, str]] = {
    # §12.2: lead with the fact, name the consequence, one action. Never scold — the
    # driver did not forget on purpose, and most of the time they were rushed off.
    "protection_gap.title": {
        "en": "Missing: {labels}",
        "es": "Falta: {labels}",
        "ru": "Не хватает: {labels}",
        "uz": "Yetishmayapti: {labels}",
        "so": "Waa maqan: {labels}",
        "pa": "ਗੁੰਮ: {labels}",
    },
    "protection_gap.body": {
        "en": "You've left{where}. This can't be captured there now — check the record.",
        "es": "Has salido de{where}. Esto ya no se puede capturar allí — revisa el registro.",
        "ru": "Вы уехали из{where}. Это уже нельзя снять там — проверьте запись.",
        "uz": "Siz{where} tark etdingiz. Buni endi u yerda olib bo'lmaydi — yozuvni tekshiring.",
        "so": "Waad ka baxday{where}. Tan hadda halkaas laguma qaadi karo — hubi diiwaanka.",
        "pa": "ਤੁਸੀਂ{where} ਛੱਡ ਦਿੱਤਾ ਹੈ। ਇਹ ਹੁਣ ਉੱਥੇ ਨਹੀਂ ਲਿਆ ਜਾ ਸਕਦਾ — ਰਿਕਾਰਡ ਦੇਖੋ।",
    },
    "protection_gap.the_facility": {
        "en": " the facility",
        "es": " la instalación",
        "ru": " объекта",
        "uz": " obyektni",
        "so": " goobta",
        "pa": " ਸਹੂਲਤ",
    },
    "gap.bol": {
        "en": "BOL", "es": "BOL", "ru": "BOL", "uz": "BOL", "so": "BOL", "pa": "BOL",
    },
    "gap.pickup_photos": {
        "en": "pickup photos",
        "es": "fotos de recogida",
        "ru": "фото при погрузке",
        "uz": "yuklash suratlari",
        "so": "sawirrada qaadista",
        "pa": "ਪਿਕਅੱਪ ਫੋਟੋਆਂ",
    },
    "gap.delivery_photos": {
        "en": "delivery photos",
        "es": "fotos de entrega",
        "ru": "фото при выгрузке",
        "uz": "yetkazib berish suratlari",
        "so": "sawirrada gaarsiinta",
        "pa": "ਡਿਲੀਵਰੀ ਫੋਟੋਆਂ",
    },
    "document_expiry.title": {
        "en": "{label} expires in {offset} days",
        "es": "{label} vence en {offset} días",
        "ru": "{label} истекает через {offset} дней",
        "uz": "{label} {offset} kundan keyin tugaydi",
        "so": "{label} wuxuu dhacayaa {offset} maalmood",
        "pa": "{label} {offset} ਦਿਨਾਂ ਵਿੱਚ ਸਮਾਪਤ ਹੁੰਦਾ ਹੈ",
    },
    "document_expiry.body": {
        "en": "Renew it before {date} to stay road-legal.",
        "es": "Renuévalo antes del {date} para seguir en regla.",
        "ru": "Обновите до {date}, чтобы оставаться в законе.",
        "uz": "Yo'lda qonuniy qolish uchun {date} dan oldin yangilang.",
        "so": "Cusboonaysii ka hor {date} si aad sharciga waddada ugu sii jirto.",
        "pa": "ਸੜਕ 'ਤੇ ਕਾਨੂੰਨੀ ਰਹਿਣ ਲਈ {date} ਤੋਂ ਪਹਿਲਾਂ ਨਵਿਆਓ।",
    },
    # doc-type nouns. CDL / BOL / POD / rate con stay English (F15 glossary).
    "doc.cdl": {"en": "CDL", "es": "CDL", "ru": "CDL", "uz": "CDL", "so": "CDL", "pa": "CDL"},
    "doc.bol": {"en": "BOL", "es": "BOL", "ru": "BOL", "uz": "BOL", "so": "BOL", "pa": "BOL"},
    "doc.pod": {"en": "POD", "es": "POD", "ru": "POD", "uz": "POD", "so": "POD", "pa": "POD"},
    "doc.rate_con": {
        "en": "rate con", "es": "rate con", "ru": "rate con",
        "uz": "rate con", "so": "rate con", "pa": "rate con",
    },
    "doc.med_card": {
        "en": "med card",
        "es": "tarjeta médica",
        "ru": "медицинская карта",
        "uz": "tibbiy karta",
        "so": "kaarka caafimaadka",
        "pa": "ਮੈਡੀਕਲ ਕਾਰਡ",
    },
    "doc.insurance": {
        "en": "insurance",
        "es": "seguro",
        "ru": "страховка",
        "uz": "sug'urta",
        "so": "caymiska",
        "pa": "ਬੀਮਾ",
    },
    "doc.permit": {
        "en": "permit",
        "es": "permiso",
        "ru": "разрешение",
        "uz": "ruxsatnoma",
        "so": "ogolaanshaha",
        "pa": "ਪਰਮਿਟ",
    },
    "doc.lumper_receipt": {
        "en": "lumper receipt",
        "es": "recibo de lumper",
        "ru": "квитанция lumper",
        "uz": "lumper kvitansiyasi",
        "so": "rasiidka lumper",
        "pa": "lumper ਰਸੀਦ",
    },
    "doc.settlement": {
        "en": "settlement",
        "es": "liquidación",
        "ru": "расчёт",
        "uz": "hisob-kitob",
        "so": "xisaabinta",
        "pa": "ਸੈਟਲਮੈਂਟ",
    },
    "doc.seal": {
        "en": "seal", "es": "sello", "ru": "пломба",
        "uz": "plomba", "so": "shaabadda", "pa": "ਸੀਲ",
    },
    "doc.damage": {
        "en": "damage", "es": "daño", "ru": "повреждение",
        "uz": "shikast", "so": "waxyeello", "pa": "ਨੁਕਸਾਨ",
    },
    "doc.other": {
        "en": "document", "es": "documento", "ru": "документ",
        "uz": "hujjat", "so": "dukumeenti", "pa": "ਦਸਤਾਵੇਜ਼",
    },
}
