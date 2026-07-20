import pytest

from app.foundation.f01_identity import public as identity


def test_register_creates_account_and_password_method(db):
    account = identity.register_account(db, "Driver@Example.com ", "s3cret-pass")
    assert account.email == "driver@example.com"
    assert len(account.auth_methods) == 1
    method = account.auth_methods[0]
    assert method.method_type == identity.MethodType.password
    assert method.is_primary is True
    assert method.secret_ref is not None
    assert method.secret_ref != "s3cret-pass"


def test_no_activation_step_account_is_immediately_usable(db):
    identity.register_account(db, "ready@example.com", "pw-123456")
    authed = identity.authenticate(db, "ready@example.com", "pw-123456")
    assert authed is not None


def test_duplicate_email_rejected(db):
    identity.register_account(db, "dupe@example.com", "pw-123456")
    with pytest.raises(identity.EmailAlreadyRegistered):
        identity.register_account(db, "Dupe@example.com", "another-pw")


def test_authenticate_wrong_password_returns_none(db):
    identity.register_account(db, "wrong@example.com", "correct-pw")
    assert identity.authenticate(db, "wrong@example.com", "bad-pw") is None


def test_authenticate_unknown_email_returns_none(db):
    assert identity.authenticate(db, "ghost@example.com", "whatever") is None


def test_session_roundtrip(db):
    account = identity.register_account(db, "sess@example.com", "pw-123456")
    session = identity.create_session(db, account, client_skew_ms=250)
    assert session.client_skew_ms == 250
    resolved = identity.resolve_session(db, session.token)
    assert resolved is not None
    assert resolved.id == account.id


def test_expired_session_resolves_to_none(db):
    from datetime import timedelta

    account = identity.register_account(db, "exp@example.com", "pw-123456")
    session = identity.create_session(db, account, ttl=timedelta(seconds=-1))
    assert identity.resolve_session(db, session.token) is None


def test_auth_method_registry_password_implemented_others_are_seams(db):
    assert identity.is_implemented(identity.MethodType.password) is True
    for seam in (
        identity.MethodType.oauth,
        identity.MethodType.otp_email,
        identity.MethodType.otp_sms,
    ):
        assert identity.is_implemented(seam) is False


def test_adding_unimplemented_method_with_credential_fails_cleanly(db):
    account = identity.register_account(db, "seam@example.com", "pw-123456")
    with pytest.raises(identity.AuthMethodNotEnabled):
        identity.add_auth_method(
            db, account, identity.MethodType.otp_sms, "+15555550123", credential="000000"
        )


def test_second_auth_method_links_to_same_account(db):
    account = identity.register_account(db, "linked@example.com", "pw-123456")
    method = identity.add_auth_method(db, account, identity.MethodType.oauth, "google:subject-123")
    assert method.account_id == account.id
    assert method.secret_ref is None


def test_roles_and_org_membership(db):
    account = identity.register_account(db, "multi@example.com", "pw-123456")
    identity.attach_role(db, account, identity.Role.driver)
    fleet = identity.create_organization(db, identity.OrgType.fleet, "Acme Freight")
    identity.attach_role(db, account, identity.Role.fleet_admin, org_id=fleet.id)
    identity.add_membership(db, fleet, account)
    db.refresh(account)
    role_values = {r.role for r in account.roles}
    assert identity.Role.driver in role_values
    assert identity.Role.fleet_admin in role_values


def test_authority_type_gates_invoicing(db):
    account = identity.register_account(db, "oo@example.com", "pw-123456")
    profile = identity.upsert_driver_profile(
        db, account, authority_type=identity.AuthorityType.own_mc, home_timezone="America/Chicago"
    )
    assert identity.can_invoice(profile) is True

    company = identity.register_account(db, "company@example.com", "pw-123456")
    company_profile = identity.upsert_driver_profile(
        db, company, authority_type=identity.AuthorityType.company
    )
    assert identity.can_invoice(company_profile) is False
