from datetime import UTC, datetime

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f07_ledger import public as ledger
from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f13_flags import public as flags
from app.foundation.f15_localization import public as localization
from app.modules.m07_fuel import public as m7
from app.modules.m10_community import public as m10
from app.modules.m11_voice import public as m11
from app.modules.m11_voice.domain import lexicon, messages

# eval fixture set (M11-FR1/FR6 DoD: >=15 intents, >=95% routing accuracy
# IN EACH LAUNCH LANGUAGE). Audit F-30: the English list below was the whole
# fixture set, so five of six launch locales scored 0% and nothing measured it.
EVAL_FIXTURES: dict[str, list[tuple[str, str]]] = {
    "en": [
        ("start my detention clock", "start_detention"),
        ("what's my detention risk at this receiver", "detention_risk"),
        ("how much detention am I at", "detention_status"),
        ("how much have I saved on fuel", "fuel_savings"),
        ("cheapest diesel ahead", "fuel_nearby"),
        ("book a parking spot", "book_parking"),
        ("where do I sleep tonight", "sleep_tonight"),
        ("any parking near exit 42", "parking_nearby"),
        ("best time to arrive at the receiver", "best_hour"),
        ("how long to unload here", "dwell_time"),
        ("is the north entrance open", "facility_info"),
        ("what's the next action on my claims", "next_action"),
        ("what am I owed", "money_owed"),
        ("how many points do I have", "points_balance"),
        ("what can you do", "help"),
        ("banana helicopter purple", "unknown"),
    ],
    "es": [
        ("inicia mi reloj de detencion", "start_detention"),
        ("cual es el riesgo de detencion en este receptor", "detention_risk"),
        ("cuanta detencion tengo", "detention_status"),
        ("cuanto he ahorrado en combustible", "fuel_savings"),
        ("diesel mas barato adelante", "fuel_nearby"),
        ("reservar un lugar de estacionamiento", "book_parking"),
        ("donde duermo esta noche", "sleep_tonight"),
        ("hay estacionamiento cerca de la salida 42", "parking_nearby"),
        ("mejor hora para llegar al receptor", "best_hour"),
        ("cuanto tiempo para descargar aqui", "dwell_time"),
        ("esta abierta la entrada norte", "facility_info"),
        ("cual es el proximo paso de mis reclamos", "next_action"),
        ("cuanto me deben", "money_owed"),
        ("cuantos puntos tengo", "points_balance"),
        ("que puedes hacer", "help"),
        ("platano helicoptero morado", "unknown"),
    ],
    "ru": [
        ("запусти счетчик простоя", "start_detention"),
        ("какой риск простоя здесь", "detention_risk"),
        ("сколько у меня простоя", "detention_status"),
        ("сколько я сэкономил на топливе", "fuel_savings"),
        ("где дешевый дизель впереди", "fuel_nearby"),
        ("забронируй место на стоянке", "book_parking"),
        ("где переночевать сегодня", "sleep_tonight"),
        ("есть парковка рядом", "parking_nearby"),
        ("во сколько лучше приехать", "best_hour"),
        ("сколько времени на разгрузку", "dwell_time"),
        ("ворота открыты", "facility_info"),
        ("что делать дальше", "next_action"),
        ("сколько мне должны", "money_owed"),
        ("сколько у меня баллов", "points_balance"),
        ("что ты умеешь", "help"),
        ("банан вертолет фиолетовый", "unknown"),
    ],
    "uz": [
        ("detention soatini boshla", "start_detention"),
        ("bu yerda detention xavfi bormi", "detention_risk"),
        ("mening detention qancha", "detention_status"),
        ("yoqilg'ida qancha tejadim", "fuel_savings"),
        ("eng arzon dizel qayerda", "fuel_nearby"),
        ("to'xtash joyini band qil", "book_parking"),
        ("bugun qayerda uxlashim mumkin", "sleep_tonight"),
        ("yaqin atrofda to'xtash joyi bormi", "parking_nearby"),
        ("qachon borish yaxshi", "best_hour"),
        ("yuk tushirish qancha vaqt oladi", "dwell_time"),
        ("darvoza ochiqmi", "facility_info"),
        ("keyingi qadam nima", "next_action"),
        ("menga qancha qarz", "money_owed"),
        ("menda qancha ball bor", "points_balance"),
        ("nima qila olasan", "help"),
        ("banan vertolyot binafsha", "unknown"),
    ],
    "so": [
        ("detention saacadda bilow", "start_detention"),
        ("halkan khatarta detention", "detention_risk"),
        ("immisa detention ayaan haystaa", "detention_status"),
        ("immisa ayaan badbaadiyay shidaalka", "fuel_savings"),
        ("shidaalka ugu jaban", "fuel_nearby"),
        ("goobta ballan qabso", "book_parking"),
        ("meesha aan seexdo caawa", "sleep_tonight"),
        ("baarkin u dhow", "parking_nearby"),
        ("goorma ayaa ugu fiican", "best_hour"),
        ("intee in le'eg dejinta", "dwell_time"),
        ("albaabka ma furan yahay", "facility_info"),
        ("maxaan sameeyaa xiga", "next_action"),
        ("immisa lacag ah ayaa la ii leeyahay", "money_owed"),
        ("immisa dhibco ayaan haystaa", "points_balance"),
        ("maxaad samayn kartaa", "help"),
        ("moos helikobtar buluug", "unknown"),
    ],
    "pa": [
        ("ਮੇਰਾ ਡਿਟੈਂਸ਼ਨ ਸ਼ੁਰੂ ਕਰੋ", "start_detention"),
        ("ਇੱਥੇ ਡਿਟੈਂਸ਼ਨ ਦਾ ਜੋਖਮ", "detention_risk"),
        ("ਮੇਰਾ ਡਿਟੈਂਸ਼ਨ ਕਿੰਨਾ ਹੈ", "detention_status"),
        ("ਮੈਂ ਫਿਊਲ ਤੇ ਕਿੰਨੀ ਬਚਤ ਕੀਤੀ", "fuel_savings"),
        ("ਸਸਤਾ ਡੀਜ਼ਲ ਕਿੱਥੇ ਹੈ", "fuel_nearby"),
        ("ਥਾਂ ਬੁੱਕ ਕਰੋ", "book_parking"),
        ("ਮੈਂ ਰਾਤ ਨੂੰ ਕਿੱਥੇ ਸੌਣਾ ਹੈ", "sleep_tonight"),
        ("ਨੇੜੇ ਪਾਰਕਿੰਗ", "parking_nearby"),
        ("ਕਦੋਂ ਪਹੁੰਚਣਾ ਵਧੀਆ ਹੈ", "best_hour"),
        ("ਅਨਲੋਡ ਕਰਨ ਵਿੱਚ ਕਿੰਨਾ ਸਮਾਂ", "dwell_time"),
        ("ਗੇਟ ਖੁੱਲ੍ਹਾ ਹੈ", "facility_info"),
        ("ਅਗਲਾ ਕਦਮ ਕੀ ਹੈ", "next_action"),
        ("ਮੈਨੂੰ ਕਿੰਨਾ ਬਕਾਇਆ ਹੈ", "money_owed"),
        ("ਮੇਰੇ ਕਿੰਨੇ ਪੁਆਇੰਟ ਹਨ", "points_balance"),
        ("ਮਦਦ", "help"),
        ("ਕੇਲਾ ਹੈਲੀਕਾਪਟਰ ਜਾਮਨੀ", "unknown"),
    ],
}
INTENT_FIXTURES = EVAL_FIXTURES["en"]
T0 = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)


def _driver(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def test_flag_registers(db):
    m11.register_module(db)
    assert flags.can_activate(db, "m11_voice") is True


def test_intent_routing_accuracy_meets_dob(db):
    correct = sum(1 for utt, expected in INTENT_FIXTURES if m11.classify_intent(utt) == expected)
    accuracy = correct / len(INTENT_FIXTURES)
    assert accuracy >= 0.95, f"routing accuracy {accuracy:.2%} below 95%"
    # >=15 distinct intents exercised (DoD)
    assert len({e for _, e in INTENT_FIXTURES if e != "unknown"}) >= 15


@pytest.mark.parametrize("locale", localization.LAUNCH_LOCALES)
def test_intent_routing_accuracy_per_launch_language(db, locale):
    # M11-FR6 + the DoD's "in each launch language" (audit F-30). Before this,
    # es/pa/ru/uz/so scored 0% and no test could see it.
    fixtures = EVAL_FIXTURES[locale]
    misses = [
        (utt, expected, m11.classify_intent(utt, locale))
        for utt, expected in fixtures
        if m11.classify_intent(utt, locale) != expected
    ]
    accuracy = 1 - len(misses) / len(fixtures)
    assert accuracy >= 0.95, f"{locale} routing accuracy {accuracy:.2%} below 95%: {misses}"
    assert len({e for _, e in fixtures if e != "unknown"}) >= 15


def test_every_launch_locale_has_a_fixture_set(db):
    assert set(EVAL_FIXTURES) == set(localization.LAUNCH_LOCALES)


def test_substring_matching_does_not_route(db):
    # the predecessor asked `term in utterance`: "gas" inside "Vegas" routed to
    # fuel, "sleep" inside "sleeper" routed to sleep_tonight
    assert m11.classify_intent("I am in Las Vegas") == "unknown"
    assert m11.classify_intent("my sleeper berth heater is broken") == "unknown"


def test_specificity_beats_rule_order(db):
    # audit F-30's second note: fuel_nearby preceded parking_nearby, so this
    # classified as fuel purely because of list position
    assert m11.classify_intent("where can I park near a gas station") == "parking_nearby"


def test_embedded_english_trucking_terms_route_in_any_locale(db):
    # M11-FR6 mixed-language; F15 keeps trucking jargon English in all six
    assert m11.classify_intent("empieza mi detention clock", "es") == "start_detention"
    assert m11.classify_intent("detention soatini boshla", "uz") == "start_detention"
    # the jargon M11 routes on is jargon F15 rules stays English
    assert "detention" in localization.DEFAULT_GLOSSARY
    for locale in localization.LAUNCH_LOCALES:
        assert m11.classify_intent("detention", locale) == "detention_status"


def test_russian_idle_time_is_not_the_word_simply(db):
    # "простой" is idle time; "просто" is the everyday word "simply". A prefix
    # rule would collapse them and route ordinary speech to a detention intent.
    assert m11.classify_intent("сколько у меня простоя", "ru") == "detention_status"
    assert m11.classify_intent("это просто тест", "ru") == "unknown"


def test_gurmukhi_survives_tokenization(db):
    # Python's re \w excludes combining marks, so the naive tokenizer shredded
    # "ਮੇਰਾ" into "ਮ","ਰ" and Punjabi matched nothing at all
    assert lexicon.tokenize("ਮੇਰਾ ਡਿਟੈਂਸ਼ਨ") == ("ਮੇਰਾ", "ਡਿਟੈਂਸ਼ਨ")
    assert lexicon.tokenize("yoqilg'i") == ("yoqilg'i",)


def test_accented_and_unaccented_spanish_both_route(db):
    # STT and drivers both drop accents. The accented word must be the ONLY
    # signal in these utterances — "inicia mi reloj de detención" routes on
    # "inicia" and "reloj" and would pass under a broken fold, proving nothing.
    assert m11.classify_intent("detención", "es") == "detention_status"
    assert m11.classify_intent("detencion", "es") == "detention_status"
    assert m11.classify_intent("cuánto he ahorrado", "es") == "fuel_savings"
    assert lexicon.tokenize("Detención") == ("detencion",)


def test_locale_scopes_the_vocabulary_rather_than_hinting_at_it(db):
    # if this passes under BOTH locales the parameter is decorative and every
    # test that claims to prove locale threading is proving nothing
    assert m11.classify_intent("сколько мне должны", "ru") == "money_owed"
    assert m11.classify_intent("сколько мне должны", "en") == "unknown"


def test_motion_policy_defers_committing_actions(db):
    driver = _driver(db)
    # in motion, "start my clock" must NOT commit — confirm on screen when stopped
    resp = m11.route(db, driver.id, "start my detention clock", driving=True)
    assert resp.intent == "start_detention"
    assert resp.needs_confirmation is True
    assert resp.data.get("deferred") is True
    assert resp.mode == "voice"


def test_money_owed_intent_dispatches_to_claims(db):
    driver = _driver(db)
    ledger.create_receivable(db, driver.id, ledger.ReceivableKind.detention, 15000)
    resp = m11.route(db, driver.id, "what am I owed")
    assert resp.intent == "money_owed"
    assert "$150.00" in resp.spoken
    assert len(resp.data["claims"]) == 1


def test_points_and_fuel_savings_intents(db):
    driver = _driver(db)
    m10.award_contribution(db, driver.id, "review", T0)
    resp = m11.route(db, driver.id, "how many points do I have")
    assert resp.intent == "points_balance"
    assert resp.data["points"] == 15

    station = facility.create_facility(db, facility.FacilityType.fuel_station, "Pilot", 32.8, -96.8)
    merchant = m7.register_merchant(db, "FuelCo")
    m7.set_station_pricing(
        db,
        station.id,
        419,
        discount_cents_per_gal=25,
        spread_cents_per_gal=4,
        merchant_id=merchant.id,
    )
    m7.settle(db, m7.issue_pump_code(db, driver.id, station.id, gallons=100))
    resp2 = m11.route(db, driver.id, "how much have I saved on fuel")
    assert resp2.intent == "fuel_savings"
    assert resp2.data["fuel_saved_cents"] == 2500


def test_ghostwriter_drafts_english_with_tone(db):
    driver = _driver(db)
    m11.register_module(db)  # registers the F9 drafting prompt
    provider = ai.FakeModelProvider()
    draft = m11.draft_counterparty_message(
        db,
        provider,
        driver.id,
        "detention notice",
        "3 hours past free time at Dallas Receiver",
        tone="firm",
    )
    assert "ENGLISH" in draft  # the prompt enforces English outbound (F15)
    assert "firm" in draft  # the firm tone preset flowed through
    assert len(draft) > 0


def test_claim_assistant_next_actions(db):
    driver = _driver(db)
    ledger.create_receivable(db, driver.id, ledger.ReceivableKind.detention, 15000)
    r2 = ledger.create_receivable(db, driver.id, ledger.ReceivableKind.tonu, 30000)
    ledger.transition_receivable(db, r2, ledger.ReceivableState.disputed)

    items = m11.claim_assistant(db, driver.id)
    by_kind = {i.kind: i for i in items}
    assert by_kind["detention"].next_action == "send a reminder"  # invoiced
    assert by_kind["tonu"].next_action == "escalate with your GPS evidence"  # disputed


def test_handle_utterance_transcribes_then_routes(db, monkeypatch):
    """Real bytes in, routed answer plus the transcript out.

    AI-CONTEXT: this used to pass `audio_ref="what am I owed"` and rely on the fake STT
    echoing that string back as the transcript — so the test's own input was its expected
    output, and the assertion held whether or not any recogniser existed. It could not
    have failed when the module had no reachable STT path, which it did not (entry 209).
    The recogniser is stubbed at the seam now; what is under test is that the transcript
    reaches the router and comes back with the answer.
    """
    from app.modules.m11_voice.domain import service

    driver = _driver(db)
    monkeypatch.setattr(service, "listen", lambda db, audio, locale="en": "what am I owed")

    resp, transcript = m11.handle_utterance(
        db, ai.FakeModelProvider(), driver.id, b"\x00fake-webm-bytes",
        locale="es", driving=True,
    )

    assert transcript == "what am I owed"
    assert resp.intent == "money_owed"
    assert resp.mode == "voice"
    # the answer is BYTES or nothing — never a `audio://` string
    assert resp.audio is None or isinstance(resp.audio, bytes)


# --- N-01: the copilot answers in the language it understood ---
def test_every_spoken_string_exists_in_all_six_launch_locales(db):
    # F15's own rule: "a driver-facing string missing any of them fails CI"
    m11.register_module(db)
    for key in messages.VOICE_MESSAGES:
        full = messages.KEY_PREFIX + key
        assert localization.missing_locales(db, full) == [], f"{key} missing locales"
        assert localization.is_complete(db, full) is True


def test_every_intent_the_router_can_return_has_something_to_say(db):
    # `_say` raises KeyError on an unknown key, deliberately — a new intent added to
    # the lexicon with no message would otherwise be a 500 in a moving truck. This
    # makes that gap fail in CI instead.
    for intent in m11.INTENTS:
        if intent in ("money_owed", "next_action", "points_balance", "fuel_savings",
                      "sleep_tonight", "detention_status", "help", "unknown"):
            continue  # these have their own keys, asserted by the dispatch tests
        assert f"handoff.{intent}" in messages.VOICE_MESSAGES, intent


def test_a_spanish_driver_is_answered_in_spanish(db):
    driver = _driver(db)
    m11.register_module(db)
    ledger.create_receivable(db, driver.id, ledger.ReceivableKind.detention, 15000)

    resp = m11.route(db, driver.id, "cuanto me deben", context={"locale": "es"})
    assert resp.intent == "money_owed"
    assert "Te deben" in resp.spoken
    # the MONEY is not localized — F15 fixes currency USD and units imperial
    assert "$150.00" in resp.spoken


def test_the_same_question_in_english_is_unchanged(db):
    driver = _driver(db)
    m11.register_module(db)
    ledger.create_receivable(db, driver.id, ledger.ReceivableKind.detention, 15000)

    resp = m11.route(db, driver.id, "what am I owed")
    assert "You're owed $150.00 across 1 claims." == resp.spoken


def test_the_deferred_confirmation_is_localized_because_it_is_always_spoken(db):
    # mode="voice" — the driver cannot read the screen to recover from this one
    driver = _driver(db)
    m11.register_module(db)
    resp = m11.route(
        db, driver.id, "empieza mi detention clock", context={"locale": "es"}, driving=True
    )
    assert resp.intent == "start_detention"
    assert resp.mode == "voice"
    assert resp.spoken == messages.VOICE_MESSAGES["deferred"]["es"]


def test_a_handoff_speaks_the_topic_rather_than_an_english_slug(db):
    driver = _driver(db)
    m11.register_module(db)
    resp = m11.route(db, driver.id, "hay estacionamiento cerca", context={"locale": "es"})
    assert resp.intent == "parking_nearby"
    assert resp.spoken == messages.VOICE_MESSAGES["handoff.parking_nearby"]["es"]
    assert "parking_nearby" not in resp.spoken  # the old slug interpolation


def test_a_missing_catalogue_row_falls_back_to_english_not_to_silence(db):
    # F-17's third option: `main.py` only warns if boot registration fails, so a strict
    # lookup would turn one missing row into a silent copilot at speed
    driver = _driver(db)
    m11.register_module(db)
    localization.register_message(db, messages.KEY_PREFIX + "unknown", "es", "")

    resp = m11.route(db, driver.id, "banana helicoptero morado", context={"locale": "es"})
    assert resp.intent == "unknown"
    assert resp.spoken == messages.VOICE_MESSAGES["unknown"]["en"]


def test_an_unregistered_catalogue_still_speaks(db):
    # register_module has NOT run here — nothing seeded the catalogue at all
    driver = _driver(db)
    resp = m11.route(db, driver.id, "how many points do I have")
    assert resp.intent == "points_balance"
    assert resp.spoken == "You have 0 points."


# --- the copilot's ears and mouth (decision 209) ---------------------------------------
#
# AI-CONTEXT: `audio_ref` WAS A FAKE ON PRODUCTION and nothing was red.
#
# `_maybe_tts` called `ai.synthesize`, which reaches the live provider's `synthesize` —
# and `AnthropicModelProvider.synthesize` delegates to `self._fallback`, the
# `FakeModelProvider`, whose implementation is:
#
#     return f"audio://{locale}/{hashlib.sha256(text.encode()).hexdigest()[:12]}"
#
# So every spoken answer the API ever returned was a hash in a scheme nothing serves. The
# UI never read the field, so the fake was never even visible as a broken link — the
# HANDOFF-138 §2 pattern once more. These were watched failing against that code.


def test_a_spoken_answer_is_never_a_fake_uri(db):
    """The single assertion that would have caught it: `audio://` is not audio."""
    from app.modules.m11_voice.domain import service

    spoken = service.speak(db, "Ikki soat kutdingiz.", locale="uz")

    assert spoken is None or isinstance(spoken, bytes)
    assert not (isinstance(spoken, str) and spoken.startswith("audio://"))


def test_the_fake_provider_can_never_supply_a_voice(db):
    """A fake is right for a test and is never a driver's answer.

    The old path took whatever the provider returned. This one goes to the Azure adapter
    or returns None — there is no third answer, and no provider can inject one.
    """
    import inspect

    from app.foundation.f09_ai_gateway.domain.provider import FakeModelProvider
    from app.modules.m11_voice.domain import service

    fake = FakeModelProvider()
    assert fake.synthesize("hello", "uz").startswith("audio://")  # unchanged, for tests

    # ...and the copilot cannot consult it: `speak` takes no provider at all. This is a
    # structural claim rather than a behavioural one on purpose — the old bug was that a
    # provider COULD supply the voice, and the fix is that the parameter is gone.
    assert "provider" not in inspect.signature(service.speak).parameters


def test_every_launch_locale_has_a_voice_or_honestly_has_none(db):
    """A locale we cannot speak returns None and keeps its text (§14.5).

    Q: why assert the map rather than the synthesis? Because a WRONG Azure voice name is
    a 502 at the moment a driver asks, and the names in this map were verified against
    the live voice list rather than remembered.
    """
    from app.modules.m11_voice.domain import service

    for locale in ("en", "es", "ru", "uz", "pa", "so"):
        settings = service.copilot_voice(db, locale)
        assert settings is not None, f"{locale} has no voice"
        assert settings["voice"].startswith(("en-", "es-", "ru-", "uz-", "pa-", "so-"))
    assert service.copilot_voice(db, "xx") is None
