"""AI-CONTEXT: what the copilot SAYS, in six languages (finding N-01).

M11 was made to understand six launch languages in session 120 (audit F-30) and still
answered every one of them in English — `_dispatch` returned hardcoded strings, and
while the truck is moving `_maybe_tts` speaks them aloud, which is the one moment a
driver cannot fall back to reading the screen. PRD §7.15's coverage rule names voice
explicitly: *"every driver-facing surface — UI, notifications (F8), voice (M11 via F9
STT/TTS), and help content — renders in the user's language."*

THIS IS F15's MESSAGE CATALOGUE'S FIRST PRODUCER. `register_message` existed, was
exported, and its only caller in the tree was F15's own test — the same built-and-inert
shape as F-09's purge and F9's budget cap. The catalogue is the designed home for
server-rendered driver strings (F15's own docstring calls it "the server catalog analog
for F8-rendered strings"), so this registers into it rather than inventing a second
mechanism beside it.

A MISSING ROW FALLS BACK TO THE COMPILED ENGLISH, never to a blank or a raw key. That
is F-17's third option applied again: refusing to answer would turn a translation gap
into an outage on the one surface a driver is using at speed, and `main.py` only warns
if boot registration fails.

WHAT IS DELIBERATELY NOT TRANSLATED. Money stays `$` and imperial units stay imperial in
every locale — F15's UNIT_SYSTEM says so and US trucking is why. `detention` stays the
English word wherever the launch catalogues already keep it (`money.kind.detention`
ships untranslated in all six), because it is F15 glossary jargon and a driver says it
in English.

PROVENANCE, same limitation as `lexicon.py` and stated for the same reason: the domain
nouns are grounded in `ui/src/core/i18n/*` where those catalogues carry them; the
sentence forms were authored here. Correct in MECHANISM and gated per locale by
`test_m11.py`; the PHRASING in es/pa/ru/uz/so wants a native-speaker pass before M11
activates. Editing a string here is the whole cost of that review.
"""

KEY_PREFIX = "m11.voice."
DEFAULT_LOCALE_KEY = "en"

# AI-CONTEXT: one key per thing the copilot can say. The handoff intents get their own
# keys rather than interpolating `intent.replace("_", " ")` — that produced an English
# slug spoken inside a Spanish sentence, which is worse than either language alone.
VOICE_MESSAGES: dict[str, dict[str, str]] = {
    "money_owed": {
        "en": "You're owed {amount} across {count} claims.",
        "es": "Te deben {amount} en {count} reclamos.",
        "ru": "Вам должны {amount} по {count} претензиям.",
        "uz": "Sizga {count} da'vo bo'yicha {amount} qarzdorlar.",
        "so": "Waxaa laguu leeyahay {amount} oo {count} sheegasho ah.",
        "pa": "ਤੁਹਾਨੂੰ {count} ਦਾਅਵਿਆਂ ਵਿੱਚ {amount} ਬਕਾਇਆ ਹੈ।",
    },
    "money_owed_none": {
        "en": "You're all paid up — nothing owed right now.",
        "es": "Estás al día — no te deben nada ahora.",
        "ru": "Всё оплачено — сейчас вам ничего не должны.",
        "uz": "Hammasi to'langan — hozir qarz yo'q.",
        "so": "Wax dhan waa la bixiyay — hadda waxba laguuma leh.",
        "pa": "ਸਭ ਭੁਗਤਾਨ ਹੋ ਗਿਆ — ਹੁਣ ਕੁਝ ਬਕਾਇਆ ਨਹੀਂ।",
    },
    "points_balance": {
        "en": "You have {points} points.",
        "es": "Tienes {points} puntos.",
        "ru": "У вас {points} баллов.",
        "uz": "Sizda {points} ball bor.",
        "so": "Waxaad haysataa {points} dhibcood.",
        "pa": "ਤੁਹਾਡੇ ਕੋਲ {points} ਪੁਆਇੰਟ ਹਨ।",
    },
    "fuel_savings": {
        "en": "You've saved {amount} on fuel so far.",
        "es": "Has ahorrado {amount} en combustible hasta ahora.",
        "ru": "Вы сэкономили {amount} на топливе.",
        "uz": "Siz yoqilg'ida {amount} tejadingiz.",
        "so": "Waxaad ku badbaadisay {amount} shidaalka.",
        "pa": "ਤੁਸੀਂ ਹੁਣ ਤੱਕ ਫਿਊਲ 'ਤੇ {amount} ਬਚਾਏ ਹਨ।",
    },
    "sleep_found": {
        "en": "I found {count} stops within your hours.",
        "es": "Encontré {count} paradas dentro de tus horas.",
        "ru": "Нашёл {count} стоянок в пределах ваших часов.",
        "uz": "Soatlaringiz ichida {count} to'xtash joyi topdim.",
        "so": "Waxaan helay {count} joogsi oo saacadahaaga ku jira.",
        "pa": "ਮੈਨੂੰ ਤੁਹਾਡੇ ਘੰਟਿਆਂ ਵਿੱਚ {count} ਸਟਾਪ ਮਿਲੇ।",
    },
    "sleep_clarify": {
        "en": "How many hours do you have left?",
        "es": "¿Cuántas horas te quedan?",
        "ru": "Сколько часов у вас осталось?",
        "uz": "Necha soatingiz qoldi?",
        "so": "Immisa saacadood ayaa kuu hadhay?",
        "pa": "ਤੁਹਾਡੇ ਕੋਲ ਕਿੰਨੇ ਘੰਟੇ ਬਾਕੀ ਹਨ?",
    },
    "detention_status": {
        "en": "Detention on record: {amount}.",
        "es": "Detention registrada: {amount}.",
        "ru": "Записано detention: {amount}.",
        "uz": "Qayd etilgan detention: {amount}.",
        "so": "Detention la diiwaangeliyay: {amount}.",
        "pa": "ਦਰਜ ਕੀਤਾ detention: {amount}।",
    },
    "detention_none": {
        "en": "No detention on record right now.",
        "es": "No hay detention registrada ahora.",
        "ru": "Сейчас detention не зафиксировано.",
        "uz": "Hozircha detention qayd etilmagan.",
        "so": "Hadda detention lama diiwaangelin.",
        "pa": "ਹੁਣ ਕੋਈ detention ਦਰਜ ਨਹੀਂ ਹੈ।",
    },
    "help": {
        "en": (
            "Ask me about parking, fuel, your detention clock, what you're owed, "
            "or to draft a message."
        ),
        "es": (
            "Pregúntame por estacionamiento, combustible, tu reloj de detention, "
            "lo que te deben, o para redactar un mensaje."
        ),
        "ru": (
            "Спросите меня о парковке, топливе, часах detention, "
            "о том, сколько вам должны, или попросите составить сообщение."
        ),
        "uz": (
            "Mendan to'xtash joyi, yoqilg'i, detention soati, "
            "sizga qancha qarzdorliklari yoki xabar tayyorlash haqida so'rang."
        ),
        "so": (
            "I weydii baarkinka, shidaalka, saacadda detention, "
            "waxa laguu leeyahay, ama inaan farriin qoro."
        ),
        "pa": (
            "ਮੈਨੂੰ ਪਾਰਕਿੰਗ, ਫਿਊਲ, ਆਪਣੀ detention ਘੜੀ, ਤੁਹਾਨੂੰ ਕੀ ਬਕਾਇਆ ਹੈ, "
            "ਜਾਂ ਸੁਨੇਹਾ ਲਿਖਣ ਬਾਰੇ ਪੁੱਛੋ।"
        ),
    },
    "unknown": {
        "en": "I didn't catch that — try 'parking ahead' or 'what am I owed'.",
        "es": "No entendí — prueba 'estacionamiento adelante' o 'cuánto me deben'.",
        "ru": "Не расслышал — попробуйте «парковка впереди» или «сколько мне должны».",
        "uz": "Tushunmadim — 'oldinda to'xtash joyi' yoki 'menga qancha qarz' deb ko'ring.",
        "so": "Ma aan maqlin — isku day 'baarkin hore' ama 'immisa lacag ah ayaa la ii leeyahay'.",
        "pa": "ਮੈਂ ਸਮਝਿਆ ਨਹੀਂ — 'ਅੱਗੇ ਪਾਰਕਿੰਗ' ਜਾਂ 'ਮੈਨੂੰ ਕਿੰਨਾ ਬਕਾਇਆ ਹੈ' ਅਜ਼ਮਾਓ।",
    },
    "deferred": {
        "en": "I'll set that up — confirm on screen when you're stopped.",
        "es": "Lo preparo — confírmalo en pantalla cuando estés detenido.",
        "ru": "Подготовлю — подтвердите на экране, когда остановитесь.",
        "uz": "Tayyorlab qo'yaman — to'xtaganingizda ekranda tasdiqlang.",
        "so": "Waan diyaarin — xaqiiji shaashadda marka aad joogsato.",
        "pa": "ਮੈਂ ਤਿਆਰ ਕਰਦਾ ਹਾਂ — ਰੁਕਣ 'ਤੇ ਸਕ੍ਰੀਨ ਉੱਤੇ ਪੁਸ਼ਟੀ ਕਰੋ।",
    },
    "handoff.start_detention": {
        "en": "Pulling up your detention clock.",
        "es": "Abriendo tu reloj de detention.",
        "ru": "Открываю ваши часы detention.",
        "uz": "Detention soatingizni ochyapman.",
        "so": "Waxaan soo bandhigayaa saacaddaada detention.",
        "pa": "ਤੁਹਾਡੀ detention ਘੜੀ ਖੋਲ੍ਹ ਰਿਹਾ ਹਾਂ।",
    },
    "handoff.detention_risk": {
        "en": "Pulling up the detention risk here.",
        "es": "Abriendo el riesgo de detention aquí.",
        "ru": "Открываю риск detention здесь.",
        "uz": "Bu yerdagi detention xavfini ochyapman.",
        "so": "Waxaan soo bandhigayaa khatarta detention halkan.",
        "pa": "ਇੱਥੇ detention ਜੋਖਮ ਖੋਲ੍ਹ ਰਿਹਾ ਹਾਂ।",
    },
    "handoff.fuel_nearby": {
        "en": "Pulling up fuel nearby.",
        "es": "Abriendo combustible cerca.",
        "ru": "Открываю топливо поблизости.",
        "uz": "Yaqin atrofdagi yoqilg'ini ochyapman.",
        "so": "Waxaan soo bandhigayaa shidaal agagaarka ah.",
        "pa": "ਨੇੜੇ ਫਿਊਲ ਖੋਲ੍ਹ ਰਿਹਾ ਹਾਂ।",
    },
    "handoff.book_parking": {
        "en": "Pulling up bookable parking.",
        "es": "Abriendo estacionamiento reservable.",
        "ru": "Открываю парковку с бронированием.",
        "uz": "Band qilinadigan to'xtash joyini ochyapman.",
        "so": "Waxaan soo bandhigayaa baarkin la ballansan karo.",
        "pa": "ਬੁੱਕ ਹੋਣ ਵਾਲੀ ਪਾਰਕਿੰਗ ਖੋਲ੍ਹ ਰਿਹਾ ਹਾਂ।",
    },
    "handoff.parking_nearby": {
        "en": "Pulling up parking nearby.",
        "es": "Abriendo estacionamiento cerca.",
        "ru": "Открываю парковку поблизости.",
        "uz": "Yaqin atrofdagi to'xtash joyini ochyapman.",
        "so": "Waxaan soo bandhigayaa baarkin agagaarka ah.",
        "pa": "ਨੇੜੇ ਪਾਰਕਿੰਗ ਖੋਲ੍ਹ ਰਿਹਾ ਹਾਂ।",
    },
    "handoff.best_hour": {
        "en": "Pulling up the best time to arrive.",
        "es": "Abriendo la mejor hora para llegar.",
        "ru": "Открываю лучшее время для прибытия.",
        "uz": "Yetib borish uchun eng yaxshi vaqtni ochyapman.",
        "so": "Waxaan soo bandhigayaa waqtiga ugu fiican ee la imaan karo.",
        "pa": "ਪਹੁੰਚਣ ਦਾ ਸਭ ਤੋਂ ਵਧੀਆ ਸਮਾਂ ਖੋਲ੍ਹ ਰਿਹਾ ਹਾਂ।",
    },
    "handoff.dwell_time": {
        "en": "Pulling up how long this stop usually takes.",
        "es": "Abriendo cuánto suele tardar esta parada.",
        "ru": "Открываю, сколько обычно занимает эта остановка.",
        "uz": "Bu to'xtash odatda qancha vaqt olishini ochyapman.",
        "so": "Waxaan soo bandhigayaa inta uu joogsigan badanaa qaato.",
        "pa": "ਇਹ ਸਟਾਪ ਆਮ ਤੌਰ 'ਤੇ ਕਿੰਨਾ ਸਮਾਂ ਲੈਂਦਾ ਹੈ ਖੋਲ੍ਹ ਰਿਹਾ ਹਾਂ।",
    },
    "handoff.facility_info": {
        "en": "Pulling up this facility.",
        "es": "Abriendo esta instalación.",
        "ru": "Открываю этот объект.",
        "uz": "Bu obyektni ochyapman.",
        "so": "Waxaan soo bandhigayaa goobtan.",
        "pa": "ਇਹ ਸਹੂਲਤ ਖੋਲ੍ਹ ਰਿਹਾ ਹਾਂ।",
    },
}
