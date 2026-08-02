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


def test_all_thirteen_modules_are_registered(db):
    keys = register_all(db)
    assert len(keys) == 13
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
