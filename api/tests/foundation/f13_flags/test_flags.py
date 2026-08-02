import pytest

from app.foundation.f13_flags import public as flags


def test_flag_without_gates_enables(db):
    flags.register_flag(db, "m01_map", description="Road Intelligence Map")
    assert flags.is_enabled(db, "m01_map") is False
    flags.enable(db, "m01_map")
    assert flags.is_enabled(db, "m01_map") is True


def test_unknown_flag_is_disabled(db):
    assert flags.is_enabled(db, "nope") is False


def test_gates_block_activation_until_satisfied(db):
    flags.register_flag(db, "m03_detention")
    flags.add_gate(db, "m03_detention", "legal_signoff")
    gate = flags.add_gate(db, "m03_detention", "collection_partner_agreement")
    assert flags.can_activate(db, "m03_detention") is False
    with pytest.raises(flags.GateNotSatisfied):
        flags.enable(db, "m03_detention")

    # satisfy both gates
    for g in flags.register_flag(db, "m03_detention").gates:
        flags.satisfy_gate(db, g)
    assert flags.can_activate(db, "m03_detention") is True
    flags.enable(db, "m03_detention")
    assert flags.is_enabled(db, "m03_detention") is True
    assert gate.satisfied is True


def test_kill_switch_forces_off(db):
    flags.register_flag(db, "m06_parking")
    flags.enable(db, "m06_parking")
    assert flags.is_enabled(db, "m06_parking") is True
    flags.kill(db, "m06_parking")
    assert flags.is_enabled(db, "m06_parking") is False
    flags.clear_kill(db, "m06_parking")
    assert flags.is_enabled(db, "m06_parking") is True


def test_config_registry_roundtrip_and_scope(db):
    flags.set_config(
        db, "detention_default_free_minutes", {"dry_van": 120, "reefer": 120}, scope="detention"
    )
    flags.set_config(db, "geofence_default_radius_m", 150, scope="geofence")
    assert flags.get_config(db, "geofence_default_radius_m") == 150
    assert flags.get_config(db, "missing", default="fallback") == "fallback"
    detention = flags.get_scope(db, "detention")
    assert detention["detention_default_free_minutes"]["reefer"] == 120


def test_a_flags_description_refreshes_on_reboot_but_its_switch_does_not(db):
    """AI-CONTEXT: A6 surfaced this. `m13_vendor` became the FOOD half of a module it
    used to name entirely, and `register_module` runs on every boot — but the
    description was written once and frozen, so every box that had already booted kept
    calling the food flag "M13 Vendor Network".

    A stale label on a switch is worse than no label: it answers the operator's
    question wrongly, and so stops them asking. `register_config` has always refreshed
    a declaration's default for exactly this reason; flags now match it.

    The half that must NOT refresh is `enabled` — that is operator state, and a
    redeploy silently flipping a flag back off is an outage nobody ordered."""
    flags.register_flag(db, "m13_vendor", description="M13 Vendor Network")
    flags.enable(db, "m13_vendor")

    flags.register_flag(db, "m13_vendor", description="M13 Vendor Network — food vendors")

    flag = db.get(flags.FeatureFlag, "m13_vendor")
    assert flag.description == "M13 Vendor Network — food vendors"
    assert flag.enabled is True  # the operator's decision survived the redeploy


def test_registering_without_a_description_does_not_erase_one(db):
    """A caller that passes no description is not asserting the flag has none."""
    flags.register_flag(db, "m06_parking", description="Parking marketplace")
    flags.register_flag(db, "m06_parking")
    assert db.get(flags.FeatureFlag, "m06_parking").description == "Parking marketplace"
