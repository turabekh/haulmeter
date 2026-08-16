"""AI-CONTEXT: M9's claim-paid alert, in six languages (finding N-02).

`{figure}` is USD in every locale (F15's UNIT_SYSTEM). This is a P0 about a driver's money
arriving, which is the notification they most want to be able to read.

PROVENANCE: as in the other N-02 tables; phrasing wants a native-speaker pass.
"""

KEY_PREFIX = "m09.alert."
DEFAULT_LOCALE_KEY = "en"

ALERT_MESSAGES: dict[str, dict[str, str]] = {
    "claim_paid.title": {
        "en": "Claim paid · {figure}",
        "es": "Reclamo pagado · {figure}",
        "ru": "Претензия оплачена · {figure}",
        "uz": "Da'vo to'landi · {figure}",
        "so": "Sheegashada waa la bixiyay · {figure}",
        "pa": "ਦਾਅਵਾ ਭੁਗਤਾਨ · {figure}",
    },
    # J1 part 3 — the fee disclosed in the same breath as the money. §12.6's two-line
    # law: the body is two lines, and the figures lead each one.
    # `Haulmeter` is the brand and stays; the rest translates, because this is our own
    # charge rather than trucking jargon (§12.3).
    "claim_paid.body_fee": {
        "en": (
            "Broker paid {gross} · Haulmeter fee {fee} · yours {net}.\n"
            "Open it to see the record."
        ),
        "es": (
            "El bróker pagó {gross} · comisión de Haulmeter {fee} · tuyo {net}.\n"
            "Ábrelo para ver el registro."
        ),
        "ru": (
            "Брокер заплатил {gross} · комиссия Haulmeter {fee} · вам {net}.\n"
            "Откройте, чтобы увидеть запись."
        ),
        "uz": (
            "Broker {gross} to'ladi · Haulmeter komissiyasi {fee} · sizga {net}.\n"
            "Yozuvni ko'rish uchun oching."
        ),
        "so": (
            "Dilaalku wuxuu bixiyay {gross} · lacagta adeegga Haulmeter {fee} · "
            "adiga {net}.\nFur si aad u aragto diiwaanka."
        ),
        "pa": (
            "ਬ੍ਰੋਕਰ ਨੇ {gross} ਦਿੱਤੇ · Haulmeter ਫ਼ੀਸ {fee} · ਤੁਹਾਡੇ {net}।\n"
            "ਰਿਕਾਰਡ ਦੇਖਣ ਲਈ ਖੋਲ੍ਹੋ।"
        ),
    },
    "claim_paid.body": {
        "en": "The claim was recorded as paid. Open it to see the record.",
        "es": "El reclamo se registró como pagado. Ábrelo para ver el registro.",
        "ru": "Претензия отмечена как оплаченная. Откройте, чтобы увидеть запись.",
        "uz": "Da'vo to'langan deb qayd etildi. Yozuvni ko'rish uchun oching.",
        "so": "Sheegashada waxaa loo diiwaangeliyay mid la bixiyay. Fur si aad u aragto diiwaanka.",
        "pa": "ਦਾਅਵਾ ਭੁਗਤਾਨ ਵਜੋਂ ਦਰਜ ਕੀਤਾ ਗਿਆ। ਰਿਕਾਰਡ ਦੇਖਣ ਲਈ ਖੋਲ੍ਹੋ।",
    },
}
