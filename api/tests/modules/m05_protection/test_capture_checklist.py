"""AI-CONTEXT: A1 requirement 1 — "A capture checklist per stop type — BOL, seal, cargo
condition, lumper receipt, damage. The checklist is configuration (F13), not code."

The last clause is the requirement. `CONDITION_SEQUENCE` next door is a hardcoded Python
list, and changing it means a deploy; a checklist that varies by customer, by lane and by
what a receiver actually demands cannot live there. F13 exists precisely for "runtime
config: rate tables, geofence tuning, points economy rates" (§7.13), and this is the same
kind of thing.

A DELIVERY is not a PICKUP. A driver dropping a load has a POD to photograph and no seal
to record; a driver collecting one has the seal and no POD. Asking for the wrong artifact
is how a checklist teaches people to ignore it.
"""

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f05_load import public as loads
from app.foundation.f13_flags import public as flags
from app.modules.m05_protection import public as m5


def _stop(db, stop_type=None):
    account = identity.register_account(db, "driver@example.com", "pw-123456")
    broker = loads.create_counterparty(db, "Bolt Logistics", loads.CounterpartyKind.broker)
    load = loads.create_load(db, account.id, counterparty_id=broker.id, reference_number="BL-1")
    fac = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Dock 4", 41.87, -87.62
    )
    stop = loads.add_stop(db, load, fac.id, stop_type or loads.StopType.delivery)
    return account, stop


def test_a_default_exists_before_anyone_configures_anything(db):
    """An unconfigured deployment must still ask for the paperwork. A checklist that is
    empty until an operator fills it in is a feature nobody switches on."""
    m5.register_module(db)
    items = m5.capture_checklist(db, loads.StopType.delivery)
    assert items, "no default checklist — an unconfigured box asks for nothing"
    assert "bol" in items


def test_a_pickup_and_a_delivery_ask_for_different_things(db):
    m5.register_module(db)
    pickup = m5.capture_checklist(db, loads.StopType.pickup)
    delivery = m5.capture_checklist(db, loads.StopType.delivery)
    assert pickup != delivery
    assert "seal" in pickup, "a driver collecting a load records the seal"
    assert "pod" in delivery, "a driver dropping one has a POD and no seal to record"


def test_an_operator_can_change_it_without_a_deploy(db):
    """The whole of "configuration, not code". A receiver that demands a lumper receipt
    should not need a release."""
    m5.register_module(db)
    flags.set_config(
        db,
        m5.CAPTURE_CHECKLIST_CONFIG,
        {"delivery": ["bol", "pod", "lumper_receipt"]},
    )
    assert m5.capture_checklist(db, loads.StopType.delivery) == ["bol", "pod", "lumper_receipt"]


def test_a_stop_type_the_config_does_not_mention_falls_back(db):
    # a partial config must not silently produce an empty checklist for everything else
    m5.register_module(db)
    flags.set_config(db, m5.CAPTURE_CHECKLIST_CONFIG, {"delivery": ["bol"]})
    assert m5.capture_checklist(db, loads.StopType.pickup), (
        "configuring one stop type emptied the others"
    )


def test_every_stop_type_gets_something(db):
    """A5's lesson one layer over: a rule whose input never arrives is not a rule. A
    stop type with no checklist asks a driver for nothing and looks like it worked."""
    m5.register_module(db)
    for stop_type in loads.StopType:
        assert m5.capture_checklist(db, stop_type), f"{stop_type.value} asks for nothing"


# --- the checklist has to be ANSWERABLE, not just displayed ---


def test_every_default_item_has_somewhere_to_capture_it(db):
    """A5's lesson, one layer up: a rule whose input never arrives is not a rule.

    Three of A1's five items were F6 doc types; `seal` and `damage` were not, and a
    checklist row for an artifact with no capture path is a tick that can never turn
    green. `has_bol` already learned the mirror of this — it rendered an unconditional
    ✓ and "a checklist that always says yes is decoration". One that always says no is
    the same decoration facing the other way, and it is worse: it trains a driver that
    the list is broken."""
    m5.register_module(db)
    for stop_type in loads.StopType:
        for item in m5.capture_checklist(db, stop_type):
            assert m5.checklist_capture_path(item) is not None, (
                f"{item!r} is on the default checklist with nowhere to capture it"
            )


def test_an_uncaptured_stop_reads_as_missing_not_as_done(db):
    m5.register_module(db)
    _account, stop = _stop(db)
    rows = m5.stop_checklist(db, stop)
    assert rows, "no checklist for a real stop"
    assert all(r["captured"] is False for r in rows)
    assert {r["item"] for r in rows} == set(m5.capture_checklist(db, stop.stop_type))


def test_photographing_the_bol_ticks_exactly_that_row(db):
    m5.register_module(db)
    account, stop = _stop(db)
    m5.capture_document(
        db,
        account.id,
        doc_type="bol",
        content=b"scan",
        filename="bol.jpg",
        content_type="image/jpeg",
        stop_ref=stop.id,
    )
    rows = {r["item"]: r["captured"] for r in m5.stop_checklist(db, stop)}
    assert rows["bol"] is True
    assert not any(v for k, v in rows.items() if k != "bol"), "one capture ticked others"


def test_damage_is_IF_APPLICABLE_and_a_clean_stop_is_not_incomplete(db):
    """A clean stop has no damage to photograph. A checklist that reports a clean stop
    as incomplete is one a driver learns to dismiss — and a dismissed checklist is the
    review-step-as-rubber-stamp failure `draft_stop_packet_on_exit` was built to avoid."""
    m5.register_module(db)
    _account, stop = _stop(db)
    rows = {r["item"]: r for r in m5.stop_checklist(db, stop)}
    assert rows["damage"]["required"] is False
    assert rows["bol"]["required"] is True
    assert m5.checklist_outstanding(db, stop) == [
        r["item"] for r in m5.stop_checklist(db, stop) if r["required"]
    ]
