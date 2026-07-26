from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f04_evidence import public as evidence
from app.foundation.f05_load import public as loads

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _account(db, email="oo@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _facility(db, name="Receiver Dock", coords=DALLAS):
    return facility.create_facility(db, facility.FacilityType.shipper_receiver, name, *coords)


def test_create_counterparty_and_payment_behavior(db):
    cp = loads.create_counterparty(
        db, "Acme Brokerage", loads.CounterpartyKind.broker, mc_number="MC123456"
    )
    loads.record_payment_observation(db, cp, 30)
    loads.record_payment_observation(db, cp, 40)
    assert cp.payment_behavior["avg_days_to_pay"] == 35
    loads.record_claim(db, cp)
    assert cp.claim_count == 1


def test_create_load_manual_with_terms(db):
    account = _account(db)
    cp = loads.create_counterparty(db, "Broker A", loads.CounterpartyKind.broker)
    load = loads.create_load(
        db,
        account.id,
        counterparty_id=cp.id,
        reference_number="L-1001",
        rate_cents=250000,
        detention_rate_cents_per_hour=7500,
        free_time_minutes=120,
    )
    assert load.source == loads.LoadSource.manual
    assert load.status == loads.LoadStatus.draft
    assert load.counterparty_id == cp.id


def test_create_load_from_parsed_terms_seam(db):
    account = _account(db)
    parsed = {
        "reference_number": "RC-77",
        "rate_cents": 300000,
        "detention_rate_cents_per_hour": 6000,
        "free_time_minutes": 120,
        "accessorial_terms": {"tonu": "50% of linehaul"},
    }
    load = loads.create_load_from_parsed_terms(db, account.id, parsed)
    assert load.source == loads.LoadSource.rate_con_parse
    assert load.accessorial_terms["tonu"] == "50% of linehaul"
    assert load.free_time_minutes == 120


def test_add_stops_ordered_and_facility_validated(db):
    account = _account(db)
    load = loads.create_load(db, account.id)
    pickup = _facility(db, "Shipper")
    delivery = _facility(db, "Receiver", coords=(32.9, -96.8))
    s0 = loads.add_stop(db, load, pickup.id, loads.StopType.pickup)
    s1 = loads.add_stop(db, load, delivery.id, loads.StopType.delivery)
    assert [s.sequence for s in loads.list_stops(db, load)] == [0, 1]
    assert s0.stop_type == loads.StopType.pickup
    assert s1.stop_type == loads.StopType.delivery


def test_add_stop_unknown_facility_raises(db):
    import uuid

    account = _account(db)
    load = loads.create_load(db, account.id)
    with pytest.raises(loads.FacilityNotFound):
        loads.add_stop(db, load, uuid.uuid4(), loads.StopType.delivery)


def test_effective_terms_stop_override_beats_load(db):
    account = _account(db)
    load = loads.create_load(
        db, account.id, detention_rate_cents_per_hour=7500, free_time_minutes=120
    )
    fac = _facility(db)
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery, free_time_minutes=60)
    free_time, rate = loads.effective_detention_terms(db, stop)
    assert free_time == 60
    assert rate == 7500


def test_arm_stop_wires_geofence_and_evidence_log(db):
    account = _account(db)
    load = loads.create_load(db, account.id)
    fac = _facility(db)
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery, appointment_start=T0)

    loads.arm_stop(db, stop)
    assert stop.geofence_armed is True
    assert stop.status == loads.StopStatus.armed
    assert stop.evidence_log_id is not None

    log = db.get(evidence.EvidenceLog, stop.evidence_log_id)
    assert log is not None
    assert log.stop_ref == stop.id

    events = location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    assert [e.event_type for e in events] == [location.GeofenceEventType.ENTER]


def test_disarm_stop_stops_evaluation(db):
    account = _account(db)
    load = loads.create_load(db, account.id)
    fac = _facility(db)
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery)
    loads.arm_stop(db, stop)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)

    loads.disarm_stop(db, stop, occurred_at=T0 + timedelta(minutes=5))
    assert stop.geofence_armed is False
    after = location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0 + timedelta(minutes=30))
    assert after == []


def test_load_status_transitions(db):
    account = _account(db)
    load = loads.create_load(db, account.id)
    loads.set_load_status(db, load, loads.LoadStatus.active)
    assert load.status == loads.LoadStatus.active
    loads.set_load_status(db, load, loads.LoadStatus.completed)
    assert load.status == loads.LoadStatus.completed


# --- The rate con, parsed (PRD §108's PRIMARY way a load is created) ---
def test_a_rate_con_silent_on_detention_says_so(db):
    """M4-FR4's pre-acceptance warning. "Silent on detention" is not "no detention" —
    it means the contract does not say, which is a fact about the paper the driver
    should learn before accepting the load, not after waiting four hours at a dock."""
    silent = loads.silent_terms({"rate_cents": 250000})

    assert set(silent) == {"detention", "free_time", "tonu"}


def test_a_term_the_contract_states_is_not_warned_about(db):
    parsed = {
        "detention_rate_cents_per_hour": 7500,
        "free_time_minutes": 120,
        "accessorial_terms": {"tonu": "50% of linehaul"},
    }

    assert loads.silent_terms(parsed) == []


def test_a_null_term_is_treated_as_silence_not_as_zero(db):
    """An explicit null and a missing key mean the same thing: the document does not
    say. Reading null as "no free time" would put a driver on a clock the contract
    never agreed to."""
    assert "free_time" in loads.silent_terms(
        {"detention_rate_cents_per_hour": 7500, "free_time_minutes": None}
    )


def test_the_parsed_receiver_is_matched_against_facilities_we_already_know(db):
    """Matched rather than created: a facility row per filed load is how the registry
    accumulates duplicates, and those duplicates are what M2's dwell history
    aggregates over."""
    known = _facility(db, name="ACME Distribution Center")

    candidates = loads.facility_candidates(db, {"receiver_name": "Acme Distribution"})

    assert [c["facility_id"] for c in candidates] == [str(known.id)]
    assert candidates[0]["score"] > 0


def test_a_rate_con_with_no_receiver_name_offers_no_match(db):
    """Rather than matching everything, or nothing, by accident."""
    _facility(db, name="Somewhere Else")

    assert loads.facility_candidates(db, {"receiver_name": None}) == []
    assert loads.facility_candidates(db, {}) == []


def test_name_similarity_cannot_tell_the_right_dock_from_a_wrong_one(db):
    """The measurement behind offering matches without pre-selecting one. Against
    "ACME Distribution Center", an unrelated "Dallas Distribution Center" scores 0.645
    and the correct-but-abbreviated "ACME Distribution Ctr" scores 0.679 — four
    hundredths apart, because the score is dominated by the words they share. No
    threshold separates them, so the screen offers and the driver picks."""
    _facility(db, name="Dallas Distribution Center")
    _facility(db, name="ACME Distribution Ctr", coords=(32.9, -96.9))

    ranked = loads.facility_candidates(db, {"receiver_name": "ACME Distribution Center"})

    by_name = {c["name"]: c["score"] for c in ranked}
    assert by_name["ACME Distribution Ctr"] - by_name["Dallas Distribution Center"] < 0.05
    # both are offered; neither carries a flag that would let a screen tick it by default
    assert all("confident" not in c for c in ranked)


def test_an_unrelated_facility_is_not_offered_at_all(db):
    """Below F2's suggestion floor there is no useful signal left."""
    _facility(db, name="Memphis Cold Storage")

    assert loads.facility_candidates(db, {"receiver_name": "ACME Distribution Center"}) == []


def test_a_term_the_contract_states_is_not_called_silence_over_a_capital_letter(db):
    """Found in a live parse: the model names terms the way the contract does, and
    returned {"TONU": "50% of linehaul if cancelled after arrival"}. An exact-key
    lookup for "tonu" missed it, so the screen said the rate con was SILENT on TONU
    while quoting the clause granting it. A driver who believes there is no TONU
    clause does not claim TONU."""
    parsed = {
        "detention_rate_cents_per_hour": 7500,
        "free_time_minutes": 120,
        "accessorial_terms": {
            "TONU": "50% of linehaul if cancelled after arrival.",
            "Detention": "$75.00 per hour after 2 hours free time.",
        },
    }

    assert loads.silent_terms(parsed) == []
