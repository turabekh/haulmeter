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
    "claim_paid.body": {
        "en": "The claim was recorded as paid. Open it to see the record.",
        "es": "El reclamo se registró como pagado. Ábrelo para ver el registro.",
        "ru": "Претензия отмечена как оплаченная. Откройте, чтобы увидеть запись.",
        "uz": "Da'vo to'langan deb qayd etildi. Yozuvni ko'rish uchun oching.",
        "so": "Sheegashada waxaa loo diiwaangeliyay mid la bixiyay. Fur si aad u aragto diiwaanka.",
        "pa": "ਦਾਅਵਾ ਭੁਗਤਾਨ ਵਜੋਂ ਦਰਜ ਕੀਤਾ ਗਿਆ। ਰਿਕਾਰਡ ਦੇਖਣ ਲਈ ਖੋਲ੍ਹੋ।",
    },
}
