"""AI-CONTEXT: M11 intent lexicon — the six-locale half of M11-FR1/FR6 (audit F-30).

Three things here are load-bearing and were each a defect before it:

1. MATCHING IS TOKEN-BASED, NOT SUBSTRING. The predecessor asked `term in
   utterance`, so "I am in Las Vegas" routed to fuel ("gas" inside "Vegas") and
   "my sleeper berth heater is broken" routed to sleep. A term is a PHRASE of
   whole tokens; a token ending in `*` is an explicit prefix, which is how
   Russian and Uzbek morphology is handled without re-opening the substring
   hole. Prefixes are used deliberately and never by default — Russian
   `простой` (idle time) must NOT be written `просто*`, because `просто` is the
   everyday word "simply".

2. ENGLISH IS ACTIVE IN EVERY LOCALE. Not a fallback — M11-FR6 specifies
   "mixed-language utterances with embedded English trucking terms", and F15's
   DEFAULT_GLOSSARY already rules that detention/lumper/BOL/TONU stay English in
   all six. The catalogues agree: `money.kind.detention` ships as "Detention"
   untranslated in all six locales while `admin.ov.detention` is translated, so
   a driver may say either and both must route.

3. RULES SCORE, THEY DO NOT RANK. The predecessor was first-match-wins over an
   ordered list, so "where can I park near a gas station" routed to fuel purely
   because the fuel rule sat higher. Specificity decides now: the 4-token phrase
   "where can i park" outscores the 2-token "gas station". Required groups weigh
   double because they carry the ACTION ("start" the clock, "book" the spot) and
   an action is what separates a command from a query.

VOCABULARY PROVENANCE, stated because it is a real limitation and belongs in
the code rather than in a handoff: terms are grounded in `ui/src/core/i18n/*`
wherever those catalogues carry the domain noun (parking, fuel, detention,
owed, points, spots, book). Verb and question forms are not in the catalogues
and were authored here. This file is correct in ARCHITECTURE and measured per
language by `test_m11.py`; its BREADTH in es/pa/ru/uz/so wants a native-speaker
pass before M11 activates. Adding a phrase to a group is the whole cost of that
review — no code changes with it.
"""

import re
import unicodedata

DEFAULT_LOCALE = "en"

_APOSTROPHES = re.compile(r"[‘’ʻʼ`´']")


def _is_word_char(ch: str) -> bool:
    # AI-CONTEXT: NOT `\w`. Python's re excludes combining marks (category M*),
    # which silently shreds every script that writes vowels as marks — Gurmukhi
    # "ਮੇਰਾ" tokenized to "ਮ","ਰ" and pa matched nothing at all.
    return ch.isalnum() or unicodedata.category(ch).startswith("M") or ch == "'"


def _fold(token: str) -> str:
    token = _APOSTROPHES.sub("'", token)
    decomposed = unicodedata.normalize("NFD", token)
    bases = [c for c in decomposed if not unicodedata.combining(c)]
    is_latin = any("LATIN" in unicodedata.name(c, "") for c in bases)
    if is_latin:
        decomposed = "".join(c for c in decomposed if not unicodedata.combining(c))
    folded = unicodedata.normalize("NFC", decomposed).casefold()
    return folded.replace("ё", "е").strip("'")


def _split(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    for ch in _APOSTROPHES.sub("'", text):
        if _is_word_char(ch):
            current.append(ch)
        elif current:
            parts.append("".join(current))
            current = []
    if current:
        parts.append("".join(current))
    return parts


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(t for t in (_fold(p) for p in _split(text)) if t)


def _token_matches(actual: str, term: str) -> bool:
    if term.endswith("*"):
        return actual.startswith(term[:-1])
    return actual == term


def _phrase_score(tokens: tuple[str, ...], phrase: tuple[str, ...]) -> int:
    n = len(phrase)
    if n == 0 or n > len(tokens):
        return 0
    for i in range(len(tokens) - n + 1):
        if all(_token_matches(tokens[i + j], phrase[j]) for j in range(n)):
            return n
    return 0


# AI-CONTEXT: groups are vocabulary; _RULES below compose group NAMES, so a term
# added once is available to every rule that references its group.
_TERMS: dict[str, dict[str, tuple[str, ...]]] = {
    "ACT_START": {
        "en": ("start", "begin", "start my", "kick off"),
        "es": ("inicia", "iniciar", "empieza", "empezar", "comienza", "comenzar", "arranca"),
        "ru": ("начни", "начать", "запусти", "запустить", "включи", "стартуй"),
        "uz": ("boshla", "boshlang", "boshlash", "yoq"),
        "so": ("bilow", "billow", "bilaab", "bilaaw"),
        "pa": ("ਸ਼ੁਰੂ", "ਚਾਲੂ"),
    },
    "ACT_BOOK": {
        "en": ("book", "reserve", "reservation"),
        "es": ("reserva", "reservar", "reservame", "apartar", "aparta"),
        "ru": ("забронируй", "забронировать", "бронир*", "резерв*"),
        "uz": ("band", "bron", "bronla", "band qil"),
        "so": ("ballan", "ballansho", "qabso"),
        "pa": ("ਬੁੱਕ", "ਰਿਜ਼ਰਵ"),
    },
    "TOPIC_DETENTION": {
        "en": ("detention", "clock", "meter", "accruing", "detention clock"),
        "es": ("detencion", "reloj", "contador", "cronometro"),
        "ru": ("простой", "простоя", "простое", "простою", "детеншн", "часы", "счетчик"),
        "uz": ("kutish", "soat", "hisoblagich"),
        "so": ("saacad", "saacadda", "sugitaan", "sugitaanka"),
        "pa": ("ਡਿਟੈਂਸ਼ਨ", "ਘੜੀ"),
    },
    "TOPIC_RISK": {
        "en": ("risk", "hold", "held up"),
        "es": ("riesgo", "retraso"),
        "ru": ("риск", "риска", "задержк*"),
        "uz": ("xavf", "xavfi", "kechikish"),
        "so": ("khatar", "khatarta", "daahitaan"),
        "pa": ("ਜੋਖਮ", "ਖਤਰਾ"),
    },
    "TOPIC_FUEL": {
        "en": ("fuel", "diesel", "gas", "gas station", "fuel stop"),
        "es": ("combustible", "diesel", "gasolina", "gasolinera"),
        "ru": ("топливо", "топлива", "дизель", "дизеля", "солярка", "заправк*"),
        "uz": ("yoqilg'i", "yoqilgi", "dizel", "benzin", "zapravka"),
        "so": ("shidaal", "shidaalka", "naafto"),
        "pa": ("ਫਿਊਲ", "ਤੇਲ", "ਡੀਜ਼ਲ"),
    },
    "TOPIC_SAVINGS": {
        "en": ("saved", "savings", "save", "how much have i saved"),
        "es": ("ahorr*", "ahorrado", "ahorro"),
        "ru": ("сэконом*", "эконом*", "сберег*"),
        "uz": ("tejadim", "tejash", "tejag*", "tejamkorlik"),
        "so": ("badbaadiyay", "keyd", "keydka", "badbaadin"),
        "pa": ("ਬਚਤ", "ਬਚਾਏ"),
    },
    "TOPIC_PARKING": {
        "en": (
            "parking",
            "park",
            "spot",
            "lot",
            "truck stop",
            "where can i park",
            "where do i park",
        ),
        "es": (
            "estacionamiento",
            "estacionar",
            "estaciono",
            "parqueo",
            "parquear",
            "aparcar",
            "lugar",
            "plaza",
            "donde puedo estacionar",
            "donde estaciono",
        ),
        "ru": (
            "парковк*",
            "стоянк*",
            "паркинг",
            "припарк*",
            "место",
            "где парковка",
            "где можно припарковаться",
        ),
        "uz": (
            "to'xtash",
            "toxtash",
            "to'xtash joyi",
            "parkovka",
            "joy",
            "qayerda to'xtash mumkin",
        ),
        "so": ("baarkin", "goobta", "goob", "meel", "xagee baabuurka dhigi karaa"),
        "pa": ("ਪਾਰਕਿੰਗ", "ਥਾਂ", "ਥਾਂਵਾਂ"),
    },
    "TOPIC_SLEEP": {
        "en": (
            "sleep",
            "overnight",
            "rest tonight",
            "where do i sleep",
            "where can i sleep",
            "shut down",
        ),
        "es": ("dormir", "duermo", "pernoctar", "descansar", "donde duermo", "pasar la noche"),
        "ru": ("спать", "ночлег", "переночевать", "ночевк*", "где переночевать"),
        "uz": ("uxla*", "tunash", "tunab", "qayerda uxlashim mumkin"),
        "so": ("seexo", "seexdo", "hurdo", "habeenkan", "meesha aan seexdo"),
        "pa": ("ਸੌਣ", "ਸੌਂਦਾ", "ਰਾਤ"),
    },
    "TOPIC_BEST_HOUR": {
        "en": ("best time", "what time", "fastest", "best hour", "quickest"),
        "es": ("mejor hora", "a que hora", "mas rapido", "mejor momento"),
        "ru": ("лучшее время", "во сколько", "быстрее всего", "когда лучше"),
        "uz": ("eng yaxshi vaqt", "qachon borish", "eng tez"),
        "so": ("waqtiga fiican", "goorma", "ugu dhaqso"),
        "pa": ("ਸਭ ਤੋਂ ਵਧੀਆ ਸਮਾਂ", "ਕਦੋਂ"),
    },
    "TOPIC_DWELL": {
        "en": ("dwell", "how long", "unload", "unloading"),
        "es": ("cuanto tiempo", "descargar", "descarga", "demora"),
        "ru": ("сколько времени", "разгрузк*", "как долго", "простоять"),
        "uz": ("qancha vaqt", "tushirish", "yuk tushirish"),
        "so": ("muddo", "muddada", "dejinta", "intee in le'eg"),
        "pa": ("ਕਿੰਨਾ ਸਮਾਂ", "ਅਨਲੋਡ"),
    },
    "TOPIC_FACILITY": {
        "en": ("facility", "receiver", "shipper", "entrance", "dock", "gate", "warehouse"),
        "es": ("instalacion", "receptor", "remitente", "entrada", "muelle", "puerta", "bodega"),
        "ru": ("склад", "получатель", "отправитель", "вход", "ворота", "док", "терминал"),
        "uz": ("ombor", "qabul qiluvchi", "kirish", "darvoza", "terminal"),
        "so": ("bakhaar", "albaabka", "irida", "goobta shirkadda"),
        "pa": ("ਸਹੂਲਤ", "ਗੇਟ", "ਡੌਕ", "ਗੋਦਾਮ"),
    },
    "TOPIC_NEXT_ACTION": {
        "en": ("next action", "what should i do", "next step", "what do i do next"),
        "es": ("proximo paso", "siguiente paso", "que hago", "que debo hacer"),
        "ru": ("следующий шаг", "что делать", "что дальше", "какой следующий шаг"),
        "uz": ("keyingi qadam", "nima qilay", "nima qilishim kerak"),
        "so": ("talaabada xigta", "maxaan sameeyaa", "tallaabada xigta"),
        "pa": ("ਅਗਲਾ ਕਦਮ", "ਕੀ ਕਰਾਂ"),
    },
    "TOPIC_OWED": {
        "en": ("owed", "owe", "money", "what am i owed", "how much am i owed"),
        "es": ("deben", "debe", "adeudado", "dinero", "cuanto me deben"),
        "ru": ("должны", "задолженность", "деньги", "сколько мне должны"),
        "uz": ("qarz", "qarzdor", "pul", "qancha qarzdorlar"),
        "so": ("lacag", "lacagta", "i leeyahay", "la leeyahay", "immisa lacag ah"),
        "pa": ("ਬਕਾਇਆ", "ਪੈਸਾ", "ਪੈਸੇ"),
    },
    "TOPIC_POINTS": {
        "en": ("points", "reward", "rewards"),
        "es": ("puntos", "recompensa", "recompensas"),
        "ru": ("очки", "очков", "баллы", "баллов", "бонус*"),
        "uz": ("ball", "ballar", "ballarim", "mukofot"),
        "so": ("dhibco", "dhibcaha", "abaalmarin"),
        "pa": ("ਪੁਆਇੰਟ", "ਇਨਾਮ"),
    },
    "TOPIC_HELP": {
        "en": ("help", "what can you do", "what can i ask"),
        "es": ("ayuda", "que puedes hacer", "ayudame"),
        "ru": ("помощь", "что ты умеешь", "помоги"),
        "uz": ("yordam", "nima qila olasan", "yordam bering"),
        "so": ("caawimo", "caawi", "maxaad samayn kartaa"),
        "pa": ("ਮਦਦ", "ਸਹਾਇਤਾ"),
    },
}

# AI-CONTEXT: (intent, required_groups, any_of_groups). Required groups weigh
# double — they carry the ACTION, which is what separates "start my detention
# clock" from "how much detention am I at". Declared order breaks exact ties and
# is the ONLY thing order still decides.
_RULES: list[tuple[str, list[str], list[str]]] = [
    ("start_detention", ["ACT_START"], ["TOPIC_DETENTION"]),
    ("detention_risk", ["TOPIC_RISK"], ["TOPIC_DETENTION"]),
    ("book_parking", ["ACT_BOOK"], ["TOPIC_PARKING"]),
    ("fuel_savings", ["TOPIC_SAVINGS"], []),
    ("detention_status", [], ["TOPIC_DETENTION"]),
    ("fuel_nearby", [], ["TOPIC_FUEL"]),
    ("sleep_tonight", [], ["TOPIC_SLEEP"]),
    ("parking_nearby", [], ["TOPIC_PARKING"]),
    ("best_hour", [], ["TOPIC_BEST_HOUR"]),
    ("dwell_time", [], ["TOPIC_DWELL"]),
    ("facility_info", [], ["TOPIC_FACILITY"]),
    ("next_action", [], ["TOPIC_NEXT_ACTION"]),
    ("money_owed", [], ["TOPIC_OWED"]),
    ("points_balance", [], ["TOPIC_POINTS"]),
    ("help", [], ["TOPIC_HELP"]),
]

INTENTS = [r[0] for r in _RULES] + ["unknown"]


def _phrases(group: str, locales: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    table = _TERMS[group]
    out: list[tuple[str, ...]] = []
    for loc in locales:
        for term in table.get(loc, ()):
            out.append(tuple(_fold(p) for p in term.split() if p))
    return tuple(out)


def _group_score(tokens: tuple[str, ...], group: str, locales: tuple[str, ...]) -> int:
    return max((_phrase_score(tokens, p) for p in _phrases(group, locales)), default=0)


def _classify_in(tokens: tuple[str, ...], locales: tuple[str, ...]) -> str:
    best_intent = "unknown"
    best_score = 0
    for intent, required, any_of in _RULES:
        total = 0
        for group in required:
            score = _group_score(tokens, group, locales)
            if score == 0:
                total = 0
                break
            total += score * 2
        else:
            if any_of:
                any_score = max(_group_score(tokens, g, locales) for g in any_of)
                if any_score == 0:
                    continue
                total += any_score
            if total > best_score:
                best_intent, best_score = intent, total
    return best_intent


def classify(utterance: str, locale: str = DEFAULT_LOCALE) -> str:
    # AI-CONTEXT: the locale SCOPES the vocabulary; it does not merely hint at
    # it. An earlier draft fell back to scanning all six on a miss, which reads
    # as generous and is not: no cross-locale collision exists in these tables,
    # so the fallback made `locale` unobservable — threaded everywhere, provable
    # nowhere, which is the shape of every built-and-inert engine this codebase
    # has been caught by. English is always in scope because M11-FR6 says so,
    # not as a fallback. F9 classify remains the upgrade path for a true miss.
    tokens = tokenize(utterance)
    if not tokens:
        return "unknown"
    locales = (DEFAULT_LOCALE,) if locale == DEFAULT_LOCALE else (DEFAULT_LOCALE, locale)
    return _classify_in(tokens, locales)
