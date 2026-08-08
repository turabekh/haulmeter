"""AI-CONTEXT: M6's booking-cancellation alert, in six languages (finding N-02).

`{figure}` and `{name}` are not translated — a refund is USD in every locale (F15's
UNIT_SYSTEM) and a lot is called what its owner calls it.

§12.2/§12.6: lead with the figure when there is one. The no-figure title is a separate key
rather than an empty interpolation, because "Booking canceled · " with nothing after it is
what an empty `{figure}` would produce.

PROVENANCE: as in the other N-02 tables; phrasing wants a native-speaker pass.
"""

KEY_PREFIX = "m06.alert."
DEFAULT_LOCALE_KEY = "en"

ALERT_MESSAGES: dict[str, dict[str, str]] = {
    "booking_canceled.title": {
        "en": "Booking canceled · {figure} refunded",
        "es": "Reserva cancelada · {figure} reembolsado",
        "ru": "Бронирование отменено · возврат {figure}",
        "uz": "Bron bekor qilindi · {figure} qaytarildi",
        "so": "Ballanta waa la joojiyay · {figure} ayaa la celiyay",
        "pa": "ਬੁਕਿੰਗ ਰੱਦ · {figure} ਵਾਪਸ",
    },
    "booking_canceled.title_no_refund": {
        "en": "Booking canceled",
        "es": "Reserva cancelada",
        "ru": "Бронирование отменено",
        "uz": "Bron bekor qilindi",
        "so": "Ballanta waa la joojiyay",
        "pa": "ਬੁਕਿੰਗ ਰੱਦ",
    },
    "booking_canceled.body": {
        "en": "{name} canceled your spot. Book another nearby.",
        "es": "{name} canceló tu lugar. Reserva otro cerca.",
        "ru": "{name} отменил ваше место. Забронируйте другое рядом.",
        "uz": "{name} joyingizni bekor qildi. Yaqin atrofdan boshqasini band qiling.",
        "so": "{name} ayaa joojiyay goobtaada. Mid kale oo dhow ballanso.",
        "pa": "{name} ਨੇ ਤੁਹਾਡੀ ਥਾਂ ਰੱਦ ਕੀਤੀ। ਨੇੜੇ ਹੋਰ ਬੁੱਕ ਕਰੋ।",
    },
}
