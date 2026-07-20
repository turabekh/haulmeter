from datetime import UTC, datetime

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f07_ledger import public as ledger
from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f13_flags import public as flags
from app.modules.m07_fuel import public as m7
from app.modules.m10_community import public as m10
from app.modules.m11_voice import public as m11

# eval fixture set (M11-FR1 DoD: >=15 intents, >=95% routing accuracy)
INTENT_FIXTURES = [
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
]
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


def test_handle_utterance_transcribes_then_routes(db):
    driver = _driver(db)
    provider = ai.FakeModelProvider()
    # the fake STT echoes the audio_ref into the transcript; drive a real intent
    resp = m11.handle_utterance(
        db, provider, driver.id, audio_ref="what am I owed", locale="es", driving=True
    )
    assert resp.intent == "money_owed"
    assert resp.mode == "voice"
    assert resp.audio_ref is not None and resp.audio_ref.startswith("audio://")
