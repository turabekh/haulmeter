"""AI-CONTEXT: M3's driver alerts, in six languages (finding N-02).

These two are the product's most important driver-facing notifications — the P0 that says
detention has started and the P1 that says free time is nearly gone — and both were English
literals passed straight to `notify.dispatch`. PRD §7.15's coverage rule names notifications
in the same breath as UI and voice.

`{rate}` and `{minutes}` arrive already formatted and are NOT translated: money stays `$`
and imperial stays imperial in every locale (F15's UNIT_SYSTEM), because this is a US
trucking product and a driver reading about a different currency is reading about a
different country's money.

`detention` stays the English word wherever the launch catalogues already keep it —
`money.kind.detention` ships untranslated in all six, and F15's DEFAULT_GLOSSARY rules it
jargon. §12.6's phrasing is preserved in each locale: lead with the fact, name the
consequence, never scold.

PROVENANCE: the same limitation as `m11_voice/domain/messages.py`. Domain nouns are
grounded in `ui/src/core/i18n/*`; the sentence forms were authored here. Correct in
mechanism and gated per locale by the tests; the PHRASING in es/pa/ru/uz/so wants a
native-speaker pass. Editing a string here is the whole cost of that review.
"""

KEY_PREFIX = "m03.alert."
DEFAULT_LOCALE_KEY = "en"

ALERT_MESSAGES: dict[str, dict[str, str]] = {
    "detention_started.title": {
        "en": "Detention started · {rate}",
        "es": "Detention iniciada · {rate}",
        "ru": "Detention начался · {rate}",
        "uz": "Detention boshlandi · {rate}",
        "so": "Detention wuu bilaabmay · {rate}",
        "pa": "Detention ਸ਼ੁਰੂ ਹੋਇਆ · {rate}",
    },
    "detention_started.title_no_rate": {
        "en": "Detention started",
        "es": "Detention iniciada",
        "ru": "Detention начался",
        "uz": "Detention boshlandi",
        "so": "Detention wuu bilaabmay",
        "pa": "Detention ਸ਼ੁਰੂ ਹੋਇਆ",
    },
    "detention_started.body": {
        "en": "Free time is used up at this stop. {action}",
        "es": "El tiempo libre se agotó en esta parada. {action}",
        "ru": "Свободное время на этой остановке закончилось. {action}",
        "uz": "Bu to'xtashda bepul vaqt tugadi. {action}",
        "so": "Waqtiga bilaashka ah ee joogsigan wuu dhammaaday. {action}",
        "pa": "ਇਸ ਸਟਾਪ 'ਤੇ ਮੁਫ਼ਤ ਸਮਾਂ ਖਤਮ ਹੋ ਗਿਆ। {action}",
    },
    # §12.6: an invoicing driver is promised a notice; a company driver is not, because
    # they cannot bill anyone and naming an action their mode does not have is a lie.
    "detention_started.action_invoice": {
        "en": "Notice ready to send.",
        "es": "Aviso listo para enviar.",
        "ru": "Уведомление готово к отправке.",
        "uz": "Xabarnoma yuborishga tayyor.",
        "so": "Ogeysiiska diyaar u ah in la diro.",
        "pa": "ਨੋਟਿਸ ਭੇਜਣ ਲਈ ਤਿਆਰ ਹੈ।",
    },
    "detention_started.action_record": {
        "en": "Your evidence pack is recording.",
        "es": "Tu paquete de evidencia se está grabando.",
        "ru": "Ваш пакет доказательств записывается.",
        "uz": "Dalil to'plamingiz yozib olinmoqda.",
        "so": "Xirmadaada caddaynta waa la duubayaa.",
        "pa": "ਤੁਹਾਡਾ ਸਬੂਤ ਪੈਕ ਰਿਕਾਰਡ ਹੋ ਰਿਹਾ ਹੈ।",
    },
    "free_time_warning.title": {
        "en": "{minutes} min free time left",
        "es": "Quedan {minutes} min de tiempo libre",
        "ru": "Осталось {minutes} мин свободного времени",
        "uz": "{minutes} daqiqa bepul vaqt qoldi",
        "so": "Waxaa hadhay {minutes} daqiiqo oo waqti bilaash ah",
        "pa": "{minutes} ਮਿੰਟ ਮੁਫ਼ਤ ਸਮਾਂ ਬਾਕੀ",
    },
    "free_time_warning.body": {
        "en": "Detention starts after that at {rate}.",
        "es": "Detention empieza después de eso a {rate}.",
        "ru": "После этого начнётся detention по ставке {rate}.",
        "uz": "Shundan keyin detention {rate} bo'yicha boshlanadi.",
        "so": "Intaas ka dib detention wuxuu bilaabmayaa {rate}.",
        "pa": "ਉਸ ਤੋਂ ਬਾਅਦ detention {rate} 'ਤੇ ਸ਼ੁਰੂ ਹੁੰਦਾ ਹੈ।",
    },
    "free_time_warning.body_no_rate": {
        "en": "Detention starts after that.",
        "es": "Detention empieza después de eso.",
        "ru": "После этого начнётся detention.",
        "uz": "Shundan keyin detention boshlanadi.",
        "so": "Intaas ka dib detention wuu bilaabmayaa.",
        "pa": "ਉਸ ਤੋਂ ਬਾਅਦ detention ਸ਼ੁਰੂ ਹੁੰਦਾ ਹੈ।",
    },
}
