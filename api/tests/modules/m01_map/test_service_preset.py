"""AI-CONTEXT: A5 — the Service preset (repair, tire, wash, parts).

Drivers asked for repair shops, tire shops and "other entities that may help" on the
map. The rules to find them existed; nothing reached them (see
test_ingest_extract_filter.py). These tests are about what the preset SHOWS once the
data is there, and the one thing it must never do is answer "where can I get fixed"
with every truck stop that sells diesel.
"""

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f13_flags import public as flags
from app.modules.m01_map import public as m1

MADISON = (43.0731, -89.4012)


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _fac(db, ftype, name, lat, lon, services=None, **attrs):
    fac = facility.create_facility(db, ftype, name, lat, lon)
    fac.attributes = {**({"services": services} if services else {}), **attrs}
    db.flush()
    return fac


def test_the_preset_shows_repair_shops_and_bays_inside_other_facilities(db):
    """Both halves, because the co-location rule means the two look nothing alike in
    the database: a standalone shop is a `repair` FACILITY, while Love's Truck Care is
    a `truck_repair` SERVICE on a truck stop. Measured on the Wisconsin pull — 10 of
    the 65 repair records merged into a host, so a preset that filtered on kind alone
    would hide every TA Truck Service and Love's Truck Care in the state."""
    _fac(db, facility.FacilityType.repair, "Portage Diesel Repair", *MADISON,
         services=["truck_repair"])
    _fac(db, facility.FacilityType.truck_stop, "Loves Travel Stop", 43.0732, -89.4013,
         services=["fuel", "truck_repair"])

    pins = m1.map_overlay(db, _account(db).id, *MADISON, 5000, preset=m1.Preset.service)
    assert {p.name for p in pins} == {"Portage Diesel Repair", "Loves Travel Stop"}


def test_a_truck_stop_that_only_sells_diesel_is_not_a_service(db):
    """The line this preset has to hold. `fuel` and `scale` are SERVICE_KINDS too, and
    including them would put 874 fuel sites and 705 scales on a chip a driver taps
    while broken down — which is the same as having no chip."""
    _fac(db, facility.FacilityType.truck_stop, "Pilot Travel Center", *MADISON,
         services=["fuel", "scale"])
    _fac(db, facility.FacilityType.rest_area, "I-94 Rest Area", 43.0733, -89.4014)

    pins = m1.map_overlay(db, _account(db).id, *MADISON, 5000, preset=m1.Preset.service)
    assert pins == []


def test_the_preset_and_the_card_cannot_disagree_about_what_a_service_is():
    # §23 entry 94's regression, one layer down: `sells_fuel` is one definition
    # because the preset that draws a pin and the badge that prices it must agree.
    # `has_service` is one for the same reason.
    assert m1.has_service("repair", [])
    assert m1.has_service("truck_stop", ["truck_repair"])
    assert not m1.has_service("truck_stop", ["fuel", "scale"])
    assert not m1.has_service("rest_area", [])


def test_the_preset_works_once_its_flag_is_REGISTERED(db):
    """Found by driving the real endpoint against the real registry, not by a test —
    the API returned ZERO service pins in Madison while 45 repair facilities sat in
    the table.

    `register_flag` creates a row with `enabled=False`, and `is_switched_off` reads
    "a row that says not enabled" as switched off. So the flag that was supposed to
    make this killable made it born dead. The kill-switch test below passed anyway,
    because before `register_module` runs there is no row at all and the predicate
    fails OPEN — it asserted the un-registered state and called it the default.

    A capability that is off the moment it is registered is the exact defect this
    whole requirement exists to fix, one layer up: not a missing feature, a feature
    nothing reaches."""
    _fac(db, facility.FacilityType.repair, "Portage Diesel Repair", *MADISON,
         services=["truck_repair"])
    m1.register_module(db)
    pins = m1.map_overlay(db, _account(db).id, *MADISON, 5000, preset=m1.Preset.service)
    assert [p.name for p in pins] == ["Portage Diesel Repair"]


def test_the_preset_can_be_killed_without_a_deploy(db):
    """Kill-switch semantics, like the module routes and deliberately NOT `is_enabled`:
    a capability that ships works until somebody switches it off. §23 entry 105 —
    a registry hiccup must not take a shipped feature dark."""
    _fac(db, facility.FacilityType.repair, "Portage Diesel Repair", *MADISON,
         services=["truck_repair"])
    account = _account(db)
    assert m1.map_overlay(db, account.id, *MADISON, 5000, preset=m1.Preset.service)

    m1.register_module(db)
    flags.kill(db, m1.SERVICE_PRESET_FLAG)
    assert m1.map_overlay(db, account.id, *MADISON, 5000, preset=m1.Preset.service) == []


def test_the_flag_carries_the_gate_that_says_the_data_arrived(db):
    """F13 validation gate (v2.0 acceptance criterion 6 — a flag that depends on the
    world carries one). The world this depends on is ingest coverage: the rules were
    starved for the whole life of the project, and nothing recorded that fact anywhere
    an operator could see it."""
    m1.register_module(db)
    gate = flags.get_gate(db, m1.SERVICE_PRESET_FLAG, "service_ingest_verified")
    assert gate is not None
    assert not gate.satisfied  # nine states of coverage is not "done"
