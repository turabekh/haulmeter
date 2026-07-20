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
