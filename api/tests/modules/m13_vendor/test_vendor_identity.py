"""AI-CONTEXT: M13-FR1 — vendor identity, the verification ladder, and Q-5 dedupe.

The two disciplines under test: a driver never sees the same cook twice under two
names (Q-5), and no rung of the verification ladder ever claims more than happened
(§11.7 — `documents_on_file` means paperwork was uploaded and reviewed, not that
anyone inspected a kitchen).
"""

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f14_admin import public as admin
from app.modules.m13_vendor import public as m13


def _account(db, email):
    return identity.register_account(db, email, "pw-123456")


def _vendor(db, email="cook@example.com", name="Osh Express", metro="orlando-fl", **kwargs):
    account = _account(db, email)
    return m13.register_vendor(
        db,
        account.id,
        name,
        m13.VendorType.food_mobile,
        metro=metro,
        languages=["uz", "ru"],
        halal_answered=True,
        halal_disclosure="Halal butcher in Orlando",
        **kwargs,
    )


def test_registering_a_vendor_attaches_the_vendor_role_and_an_owner_member(db):
    vendor = _vendor(db)
    account = db.get(identity.Account, vendor.owner_account_id)

    assert any(r.role == identity.Role.vendor for r in account.roles)
    assert [m.member_role for m in vendor.members] == [m13.MemberRole.owner]
    assert vendor.verify_status == m13.VendorVerifyStatus.unverified
    assert vendor.status == m13.VendorStatus.active


def test_a_helper_can_join_a_vendor(db):
    # one vendor account, several people: the owner cooks, a helper posts the schedule
    vendor = _vendor(db)
    helper = _account(db, "helper@example.com")
    m13.add_member(db, vendor, helper.id)

    assert m13.is_member(db, vendor.id, helper.id)
    assert any(r.role == identity.Role.vendor for r in db.get(identity.Account, helper.id).roles)


# --- Q-5: one canonical vendor ---
def test_same_phone_is_caught_as_a_duplicate(db):
    _vendor(db, contact_phone="(407) 555-0134")
    other = _account(db, "second@example.com")

    with pytest.raises(m13.DuplicateVendor):
        m13.register_vendor(
            db,
            other.id,
            "Osh Express Orlando",
            m13.VendorType.food_mobile,
            metro="orlando-fl",
            contact_phone="407-555-0134",  # same number, different formatting
        )


def test_a_similar_name_in_the_same_metro_is_caught(db):
    _vendor(db, name="Samarkand Plov")
    other = _account(db, "third@example.com")

    with pytest.raises(m13.DuplicateVendor):
        m13.register_vendor(
            db, other.id, "samarkand plov", m13.VendorType.food_mobile, metro="orlando-fl"
        )


def test_the_same_name_in_a_different_metro_is_a_different_vendor(db):
    # blocking is per metro: two unrelated cooks may genuinely share a dish name
    _vendor(db, name="Samarkand Plov")
    other = _account(db, "chicago@example.com")

    vendor = m13.register_vendor(
        db, other.id, "Samarkand Plov", m13.VendorType.food_mobile, metro="chicago-il"
    )
    assert vendor.id is not None


def test_one_owner_cannot_hold_two_vendor_profiles(db):
    vendor = _vendor(db)
    with pytest.raises(m13.DuplicateVendor):
        m13.register_vendor(
            db, vendor.owner_account_id, "Totally Different Name", m13.VendorType.food_mobile
        )


def test_duplicates_merge_rather_than_coexist(db):
    canonical = _vendor(db, name="Osh Express")
    dupe = _vendor(db, email="dupe@example.com", name="Osh Xpress", metro="tampa-fl")

    m13.merge_vendors(db, canonical, dupe)

    assert dupe.status == m13.VendorStatus.merged
    assert m13.resolve_vendor(db, dupe.id).id == canonical.id
    # a merged vendor is never a future merge target
    assert canonical not in [] and dupe not in m13.find_vendor_duplicates(
        db, "Osh Xpress", "tampa-fl", None
    )


# --- FR1: the verification ladder ---
def test_uploading_a_document_moves_to_documents_on_file_and_queues_review(db):
    vendor = _vendor(db)
    record = m13.attach_document(
        db,
        vendor,
        vendor.owner_account_id,
        m13.DocumentKind.license,
        b"%PDF-1.4 permit",
        "permit.pdf",
    )

    assert vendor.verify_status == m13.VendorVerifyStatus.documents_on_file
    assert record.review_status == m13.DocumentReviewStatus.pending
    pending = admin.list_pending_moderation(db)
    assert any(i.content_kind == "vendor_document" for i in pending)


def test_documents_on_file_does_not_mean_verified(db):
    # the honesty line: paperwork on file is NOT an inspection, and the ladder must
    # not skip a rung on its own. Only an explicit admin decision reaches `verified`.
    vendor = _vendor(db)
    m13.attach_document(
        db, vendor, vendor.owner_account_id, m13.DocumentKind.license, b"x", "l.pdf"
    )
    assert vendor.verify_status != m13.VendorVerifyStatus.verified

    m13.set_verification(db, vendor, m13.VendorVerifyStatus.verified)
    assert vendor.verify_status == m13.VendorVerifyStatus.verified


def test_an_admin_decision_resolves_the_moderation_item(db):
    vendor = _vendor(db)
    moderator = _account(db, "mod@example.com")
    record = m13.attach_document(
        db, vendor, vendor.owner_account_id, m13.DocumentKind.insurance, b"x", "i.pdf"
    )

    m13.decide_document(db, record, approve=True, moderator_account_id=moderator.id)

    assert record.review_status == m13.DocumentReviewStatus.approved
    assert db.get(admin.ModerationItem, record.moderation_ref).status == (
        admin.ModerationStatus.approved
    )


def test_suspending_a_vendor_removes_it_from_discovery(db):
    vendor = _vendor(db)
    m13.suspend_vendor(db, vendor, True)

    assert vendor.status == m13.VendorStatus.suspended
    assert m13.in_discovery(db, vendor) is False


def test_reinstating_clears_the_publish_suspension(db):
    vendor = _vendor(db)
    vendor.publish_suspended = True
    vendor.consecutive_no_shows = 3
    m13.suspend_vendor(db, vendor, True)
    m13.suspend_vendor(db, vendor, False)

    assert vendor.publish_suspended is False
    assert vendor.consecutive_no_shows == 0


def test_module_registers_its_flag_off_and_an_admin_view(db):
    from app.foundation.f13_flags import public as flags

    m13.register_module(db)
    assert flags.is_enabled(db, m13.FLAG_KEY) is False  # PRD §6: flags default OFF
    assert any(v.key == "m13.vendors" for v in admin.list_admin_views(db))
