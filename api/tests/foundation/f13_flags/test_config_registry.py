"""AI-CONTEXT: a config key nobody can FIND is not configuration.

A1 requirement 1 says the capture checklist "is configuration (F13), not code", and it
is — `capture_checklist` reads `a01.capture_checklist` and an operator can POST it. But
`GET /admin/config` lists `get_scope`, which returns rows that EXIST, and
`/config/scopes` returns scopes that have entries. An unset key appears nowhere, and its
own endpoint's docstring is the giveaway: "so an operator never has to guess a scope
name to discover what is configurable". Guessing the KEY was still the only way in.

Measured before building this: `a01.capture_checklist` is the first config key any
component in the product reads. Nothing anywhere calls `set_config` outside the admin
endpoint and tests — so there was no established seeding pattern to follow, and no
declaration mechanism to extend. This is it.

DECLARING is deliberately not SETTING. Writing the default into a row would freeze
today's default in the database, so a later change to the code default would silently
not apply to any box that had ever booted. A declaration carries the default without
materialising it.
"""

from app.foundation.f13_flags import public as flags


def test_a_declared_key_is_discoverable_before_anyone_sets_it(db):
    flags.register_config(db, "a01.capture_checklist", {"delivery": ["bol"]}, "Capture checklist")
    declared = flags.declared_configs(db, "global")
    assert "a01.capture_checklist" in declared
    assert declared["a01.capture_checklist"]["default"] == {"delivery": ["bol"]}
    assert declared["a01.capture_checklist"]["set"] is False


def test_declaring_does_NOT_write_the_value(db):
    """The freeze this avoids. A declaration that seeds a row pins the default at the
    moment the box first booted, and every later change to the code default is a change
    that appears to have no effect."""
    flags.register_config(db, "a01.capture_checklist", {"delivery": ["bol"]}, "Capture checklist")
    assert flags.get_config(db, "a01.capture_checklist") is None
    assert "a01.capture_checklist" not in flags.get_scope(db, "global")


def test_setting_it_marks_it_set_and_keeps_the_default_visible(db):
    # an operator comparing what they changed against what shipped needs both
    flags.register_config(db, "a01.capture_checklist", {"delivery": ["bol"]}, "Capture checklist")
    flags.set_config(db, "a01.capture_checklist", {"delivery": ["bol", "pod"]})
    row = flags.declared_configs(db, "global")["a01.capture_checklist"]
    assert row["set"] is True
    assert row["value"] == {"delivery": ["bol", "pod"]}
    assert row["default"] == {"delivery": ["bol"]}


def test_re_registering_is_idempotent_and_refreshes_the_default(db):
    # `register_module` runs on every boot; a second declaration must not duplicate,
    # and a code default that changed must be what the console shows
    flags.register_config(db, "k", {"a": 1}, "first")
    flags.register_config(db, "k", {"a": 2}, "second")
    declared = flags.declared_configs(db, "global")
    assert declared["k"]["default"] == {"a": 2}
    assert declared["k"]["description"] == "second"


def test_M5_declares_the_checklist_when_the_module_registers(db):
    """The point of all of it: booting the box makes the checklist discoverable."""
    from app.modules.m05_protection import public as m5

    m5.register_module(db)
    declared = flags.declared_configs(db, "global")
    assert m5.CAPTURE_CHECKLIST_CONFIG in declared
    assert declared[m5.CAPTURE_CHECKLIST_CONFIG]["default"] == m5.DEFAULT_CAPTURE_CHECKLIST



def test_the_ADMIN_CONSOLE_is_told_what_is_tunable(db):
    """Over HTTP, because the domain layer knowing is not the point — the operator
    reading the console is. `/config` returned only rows that exist."""
    import uuid

    from fastapi.testclient import TestClient

    from app.api.deps import get_db
    from app.foundation.f01_identity import public as identity
    from app.foundation.f01_identity.domain.models import Account
    from app.main import app
    from app.modules.m05_protection import public as m5

    m5.register_module(db)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        reg = client.post(
            "/auth/register", json={"email": "admin@example.com", "password": "pw-123456"}
        ).json()
        identity.attach_role(
            db, db.get(Account, uuid.UUID(reg["account_id"])), identity.Role.platform_admin
        )
        db.flush()
        body = client.get(
            "/admin/config", headers={"Authorization": f"Bearer {reg['token']}"}
        ).json()
        assert m5.CAPTURE_CHECKLIST_CONFIG in body["declared"]
        assert body["declared"][m5.CAPTURE_CHECKLIST_CONFIG]["set"] is False
        # and NOT in `entries`, because nothing has been set — the distinction this
        # whole mechanism exists to draw
        assert m5.CAPTURE_CHECKLIST_CONFIG not in body["entries"]
    finally:
        app.dependency_overrides.clear()


def test_a_box_with_nothing_configured_still_offers_a_SCOPE(db):
    """`/config/scopes` listed scopes that have ENTRIES. On a box where nobody has set
    anything — every box, on first boot — it returned an empty list, so the console's
    scope dropdown was empty and the declared keys behind it were unreachable. The
    endpoint's own comment promised an operator "never has to guess a scope name"."""
    import uuid

    from fastapi.testclient import TestClient

    from app.api.deps import get_db
    from app.foundation.f01_identity import public as identity
    from app.foundation.f01_identity.domain.models import Account
    from app.main import app
    from app.modules.m05_protection import public as m5

    m5.register_module(db)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        reg = client.post(
            "/auth/register", json={"email": "admin2@example.com", "password": "pw-123456"}
        ).json()
        identity.attach_role(
            db, db.get(Account, uuid.UUID(reg["account_id"])), identity.Role.platform_admin
        )
        db.flush()
        scopes = client.get(
            "/admin/config/scopes", headers={"Authorization": f"Bearer {reg['token']}"}
        ).json()
        assert "global" in scopes
    finally:
        app.dependency_overrides.clear()
