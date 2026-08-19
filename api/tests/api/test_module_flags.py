"""AI-CONTEXT: PRD §6's flag law, as tests (§23 entry 105).

The governing rule: each module is "built end-to-end **behind its own feature flag** in
the platform's flag registry… Flags exist for **operational safety and controlled
activation**." Audited 29 July 2026, that was true of exactly one module:

    modules declaring FLAG_KEY ......... 13 of 13
    flags registered in the database ...  3
    routers checking their flag ........  1 (m13_vendor)

So M2–M10 and M12 were reachable with no gate and there was **no kill switch**: if M3's
claim logic began producing wrong money on the deployed box, the only remedy was a
redeploy. §23 entries 92 and 93 both happened without one.

What these defend:
· every module router carries its gate — the check that catches a NEW module added
  without one, which is how twelve came to be open in the first place;
· a switched-off module answers 404, not 403, following M13: it is not there, and a
  403 would confirm the capability exists and is being withheld;
· the gate fails OPEN on an unregistered flag and CLOSED on an explicit decision,
  because registration runs at boot and a registry hiccup must not take the product
  dark;
· `register_all` is genuinely idempotent, because it now runs on every start.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db
from app.foundation.f13_flags import public as flags
from app.main import app
from app.module_registry import MODULES, register_all


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    resp = client.post(
        "/auth/register", json={"email": "flags@example.com", "password": "pw-123456"}
    )
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_every_module_router_carries_its_own_gate():
    """The structural check. A module added later without a gate is the defect this
    entry exists to fix, and it would be invisible to every other test in the tree."""
    import inspect
    import pathlib

    from app.api import deps

    api_dir = pathlib.Path(inspect.getfile(deps)).parent
    missing = []
    for path in sorted(api_dir.glob("m[01][0-9]_*.py")):
        source = path.read_text()
        # `require_any_module` is the same gate for a module built in halves (A6/M13).
        # Both forms count; anything else is a router nobody can switch off.
        if "require_module(" not in source and "require_any_module(" not in source:
            missing.append(path.name)
    assert missing == [], f"module routers with no flag gate: {missing}"


def test_all_fifteen_modules_are_registered(db):
    # AI-CONTEXT: M15 is the fifteenth (PRD Extension E3, owner decision D14 scope (b));
    # M14 was the fourteenth (E2, D8). The count is asserted rather than derived from
    # MODULES on purpose — deriving it would make this test agree with any list, including
    # one a module was accidentally dropped from. So adding a module is MEANT to fail this
    # test once, and the fix is to change the number here rather than to compute it.
    keys = register_all(db)
    assert len(keys) == 15
    for module in MODULES:
        assert db.get(flags.FeatureFlag, module.FLAG_KEY) is not None


def test_register_all_is_idempotent(db):
    """It runs on EVERY application start now. `add_gate` was not idempotent and the
    second boot hit a unique constraint, rolling the whole registry back."""
    first = register_all(db)
    second = register_all(db)
    assert first == second


def test_registration_never_overrules_an_owners_decision(db):
    """A deploy must not switch a module back on that somebody deliberately turned
    off — which is the entire point of having a kill switch."""
    register_all(db)
    flags.disable(db, "m03_detention")

    register_all(db)

    assert flags.is_switched_off(db, "m03_detention") is True


def test_a_switched_off_module_is_not_there(client, auth, db):
    register_all(db)
    flags.disable(db, "m03_detention")

    resp = client.get("/detention/claims", headers=auth)

    # 404, not 403 — following M13. A disabled module is absent, and a 403 would
    # confirm the capability exists and is being withheld.
    assert resp.status_code == 404


def test_an_unregistered_flag_leaves_a_module_reachable(db):
    """Fails OPEN on absence, CLOSED on a decision. Registration runs at boot; if it
    ever fails, `is_enabled` semantics would answer 404 for twelve modules at once —
    a self-inflicted outage of exactly the kind §23 92/93/100 kept finding."""
    assert flags.is_switched_off(db, "m99_never_registered") is False


def test_the_kill_switch_still_closes_the_gate(db):
    register_all(db)
    flags.kill(db, "m03_detention")
    assert flags.is_switched_off(db, "m03_detention") is True


# --- F-02 + F-12: the gate mechanism that had never gated anything ---
#
# AI-CONTEXT: measured on the running box before any of this was written — three modules
# carry validation gates, all SIX were unsatisfied, and all three flags read enabled:
#
#     m03_detention   collection_partner_agreement=false, legal_signoff=false
#     m06_parking     damage_liability_posture=false, refund_policy=false
#     m07_fuel        merchant_agreement=false, payment_partner=false
#
# `enable()` is the only function in F13 that reads a gate, and `register_all` set
# `enabled` by assignment, so it was never on the path. These tests hold the separation
# that fixed it (§23 entry 133).


def test_registration_writes_no_operator_state(db):
    """The heart of F-02. `register_all` used to assign `flag.enabled = True`, which
    bypassed `enable()` and therefore every validation gate. It must now declare the code
    default and leave the operator's column untouched."""
    register_all(db)
    for module in MODULES:
        row = db.get(flags.FeatureFlag, module.FLAG_KEY)
        assert row.enabled is None, f"{module.FLAG_KEY}: registration wrote a decision"
    # and the twelve that were live on 29 July still come up live, by declaration
    assert flags.is_enabled(db, "m03_detention") is True


def test_a_gate_refuses_a_deliberate_activation(db):
    """What the gates are FOR, and what they had never once done."""
    register_all(db)
    flags.disable(db, "m03_detention")  # an operator switches the wedge off
    with pytest.raises(flags.GateNotSatisfied):
        flags.enable(db, "m03_detention")  # ...and cannot switch it back on unverified
    assert flags.is_enabled(db, "m03_detention") is False


def test_a_satisfied_gate_lets_the_activation_through(db):
    """The other direction, or the test above would pass against a flag that can never
    be enabled at all."""
    register_all(db)
    flags.disable(db, "m03_detention")
    row = db.get(flags.FeatureFlag, "m03_detention")
    for gate in row.gates:
        flags.satisfy_gate(db, gate, note="test")
    flags.enable(db, "m03_detention")
    assert flags.is_enabled(db, "m03_detention") is True


def test_the_two_predicates_agree_on_every_registered_flag(db):
    """F-12. `is_switched_off` and `is_enabled` were separate implementations of one
    question, and the audit's point was that they "only agree because F-02 force-enables
    everything". They share `_effective` now, so agreement is structural."""
    register_all(db)
    flags.disable(db, "m06_parking")
    flags.kill(db, "m07_fuel")
    rows = db.query(flags.FeatureFlag).all()
    assert len(rows) > 10  # the assertion must have something to range over
    for row in rows:
        assert flags.is_enabled(db, row.key) is not flags.is_switched_off(db, row.key), row.key


def test_the_two_predicates_still_diverge_on_an_ABSENT_flag(db):
    """And that divergence is deliberate, not the defect. Both defaults are §23 entry
    105's and both survive: a capability nobody registered must not FIRE, and a registry
    hiccup must not take twelve modules dark and 404 the product."""
    assert flags.is_enabled(db, "m99_never_registered") is False  # does not run
    assert flags.is_switched_off(db, "m99_never_registered") is False  # not withheld


def test_a_flag_running_ahead_of_its_gates_says_so(db):
    """The honest half of F-02. Blocking the default would have taken M3's detention
    clock down — the wedge — so the 29 July decision stands and the unmet preconditions
    are REPORTED instead. This is the mechanism that stops that being silent."""
    register_all(db)
    ahead = dict(flags.running_ahead_of_gates(db))
    assert ahead["m03_detention"] == ["collection_partner_agreement", "legal_signoff"]
    assert ahead["m06_parking"] == ["damage_liability_posture", "refund_policy"]
    assert ahead["m07_fuel"] == ["merchant_agreement", "payment_partner"]
    # a module with no gates is not "ahead" of anything
    assert "m09_money" not in ahead


def test_a_satisfied_module_drops_off_the_ahead_report(db):
    """Otherwise the report could be a hardcoded list of three keys."""
    register_all(db)
    row = db.get(flags.FeatureFlag, "m07_fuel")
    for gate in row.gates:
        flags.satisfy_gate(db, gate, note="test")
    assert "m07_fuel" not in dict(flags.running_ahead_of_gates(db))


def test_a_switched_off_module_is_not_reported_as_running_ahead(db):
    """It is not running at all, so it is not running ahead of anything."""
    register_all(db)
    flags.disable(db, "m06_parking")
    assert "m06_parking" not in dict(flags.running_ahead_of_gates(db))


def test_the_code_default_refreshes_but_the_decision_never_does(db):
    """`register_flag` refreshes `description` and now `default_on`, because both are
    facts about the shipped code. `enabled` is the operator's and a redeploy must never
    flip it back — the rule that column was already written to obey."""
    flags.register_flag(db, "zz_test_flag", description="first", default_on=False)
    flags.register_flag(db, "zz_test_flag", description="second", default_on=True)
    row = db.get(flags.FeatureFlag, "zz_test_flag")
    assert row.description == "second"
    assert row.default_on is True
    assert row.enabled is None  # never written by registration

    flags.disable(db, "zz_test_flag")
    flags.register_flag(db, "zz_test_flag", description="second", default_on=True)
    assert db.get(flags.FeatureFlag, "zz_test_flag").enabled is False  # decision survives
    assert flags.is_enabled(db, "zz_test_flag") is False


def test_clearing_a_decision_hands_the_flag_back_to_its_default(db):
    """Without this there is no way back: `disable()` writes False and the declared
    default could never apply again."""
    register_all(db)
    flags.disable(db, "m09_money")
    assert flags.is_enabled(db, "m09_money") is False
    flags.clear_decision(db, "m09_money")
    assert db.get(flags.FeatureFlag, "m09_money").enabled is None
    assert flags.is_enabled(db, "m09_money") is True


def test_a_kill_switch_beats_both_the_default_and_the_decision(db):
    register_all(db)
    flags.kill(db, "m01_map")
    assert flags.is_enabled(db, "m01_map") is False
    flags.clear_decision(db, "m01_map")
    assert flags.is_enabled(db, "m01_map") is False  # default cannot outrank a kill


# --- F-17: the cost control that had never governed a call ---
def test_every_module_gets_an_ai_budget_at_boot(db):
    """`_check_budget` returned silently for a module with no ModuleBudget row, and
    nothing in the product ever wrote one — `set_module_budget` had no caller outside
    the tests. So F9's cap was a well-designed guard, tested in isolation, that had
    never governed a single call: structurally the same finding as the twelve unflagged
    modules this file already exists to prevent.

    Seeded for ALL modules, not only the four calling F9 today, because a per-module
    opt-in is a list someone must remember to extend and the cost of forgetting is
    silent unlimited spend."""
    from app.foundation.f09_ai_gateway import public as ai

    register_all(db)
    missing = [m.MODULE for m in MODULES if db.get(ai.ModuleBudget, m.MODULE) is None]
    assert missing == [], f"modules that could spend with no cap: {missing}"


def test_an_existing_budget_is_never_overruled_by_a_restart(db):
    # the same rule register_all applies to flag state: the number is an operator's
    # decision, and a deploy must not reset it
    from app.foundation.f09_ai_gateway import public as ai

    register_all(db)
    ai.set_module_budget(db, "m03", monthly_budget_micros=7)
    register_all(db)
    assert db.get(ai.ModuleBudget, "m03").monthly_budget_micros == 7


def test_the_default_budget_is_a_live_f13_config_knob(db):
    from app.foundation.f09_ai_gateway import public as ai
    from app.foundation.f13_flags import public as flags

    flags.set_config(db, ai.CONFIG_MONTHLY_BUDGET, 123_456, scope="ai")
    register_all(db)
    assert db.get(ai.ModuleBudget, MODULES[0].MODULE).monthly_budget_micros == 123_456


def test_a_dormant_map_refuses_its_endpoints(client, db):
    """AI-CONTEXT: the dormancy flip is only real if the ENDPOINTS go dark with the tab
    (owner decision D21, §23 entry 228).

    Hiding a surface while its API stays open is not dormancy, it is a hidden feature —
    and §23 entry 105's module-flag gate is what makes the difference. `m01_map` now
    declares `default_on=False`, so a box where no operator has decided anything serves
    no map at all.
    """
    from app.modules.m01_map import public as m1

    m1.register_module(db)
    reg = client.post(
        "/auth/register", json={"email": "dormant@example.com", "password": "pw-123456"}
    )
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}

    resp = client.get(
        "/map/overlay?min_lat=32&min_lon=-97&max_lat=33&max_lon=-96", headers=headers
    )

    assert resp.status_code == 404, "the map is dormant; its endpoints must refuse"
