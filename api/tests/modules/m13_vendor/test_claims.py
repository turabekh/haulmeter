"""AI-CONTEXT: M13-FR7 — service-center facility claiming.

The rule worth the most here is E3.2's union discipline: **a claim can never erase
what ingestion knows.** These tests prove it holds by construction — curated facts
live on the claim row, nothing writes back to `f02.facility`, and the read path
unions the two. That is the payoff of the Q12 decision (attributes, one source of
truth): FR7 reads the same `services` list rather than keeping a rival copy.

Also under test: one approved claim per facility (a rival becomes a DISPUTE for a
human, because "who owns this business" is not a question code should answer), and
an unclaimed facility staying a plain POI.
"""

from datetime import UTC, datetime

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f13_flags import public as flags
from app.foundation.f14_admin import public as admin
from app.modules.m13_vendor import public as m13

JOPLIN = (37.084, -94.513)
T0 = datetime(2026, 7, 26, 9, 0, tzinfo=UTC)


def _account(db, email):
    return identity.register_account(db, email, "pw-123456")


def _service_vendor(db, email="shop@example.com", name="Gateway Truck Service", metro="joplin-mo"):
    account = _account(db, email)
    return m13.register_vendor(
        db,
        account.id,
        name,
        m13.VendorType.service_center,
        metro=metro,
        languages=["en"],
        halal_answered=True,
    )


def _service_facility(db, name="Gateway Truck Service", services=None):
    fac = facility.create_facility(db, facility.FacilityType.repair, name, *JOPLIN)
    fac.attributes = {"services": services or [facility.SERVICE_TIRE]}
    return fac


def _claim(db, vendor, fac, name=None, account_id=None):
    return m13.submit_claim(
        db,
        vendor,
        fac.id,
        name or vendor.name,
        account_id or vendor.owner_account_id,
        document_content=b"%PDF business license",
        filename="license.pdf",
        now=T0,
    )


# --- the gate ---
def test_a_service_center_claims_a_service_facility(db):
    vendor, fac = _service_vendor(db), _service_facility(db)
    claim = _claim(db, vendor, fac)

    assert claim.status == m13.ClaimStatus.pending
    assert claim.name_match_score == 1.0
    assert claim.document_id is not None
    assert any(i.content_kind == "facility_claim" for i in admin.list_pending_moderation(db))


def test_a_food_vendor_cannot_claim_a_facility(db):
    account = _account(db, "cook@x.com")
    cook = m13.register_vendor(
        db, account.id, "Osh Express", m13.VendorType.food_mobile, metro="joplin-mo"
    )
    fac = _service_facility(db)
    with pytest.raises(m13.NotAServiceCenter):
        _claim(db, cook, fac)


def test_a_facility_with_no_ingested_services_cannot_be_claimed(db):
    # FR7 reads the E3.2 list — if ingestion never saw service capability there is
    # nothing to claim, and inventing it here would create a second source of truth
    vendor = _service_vendor(db)
    plain = facility.create_facility(
        db, facility.FacilityType.truck_stop, "Gateway Truck Service", *JOPLIN
    )
    with pytest.raises(m13.NotAServiceFacility):
        _claim(db, vendor, plain)


def test_a_name_that_does_not_match_is_refused(db):
    vendor = _service_vendor(db, name="Totally Unrelated Repairs")
    fac = _service_facility(db, name="Gateway Truck Service")
    with pytest.raises(m13.NameMismatch) as exc:
        _claim(db, vendor, fac)
    assert exc.value.score < exc.value.required


def test_the_name_match_threshold_is_f13_tunable(db):
    vendor = _service_vendor(db, name="Gateway Repairs")
    fac = _service_facility(db, name="Gateway Truck Service")
    flags.set_config(db, m13.CONFIG_CLAIM_NAME_MATCH, 0.95)
    with pytest.raises(m13.NameMismatch):
        _claim(db, vendor, fac)


# --- the union discipline (E3.2) ---
def test_a_claim_cannot_erase_ingested_services(db):
    # THE test for the Q12 decision: curation is additive by construction
    vendor = _service_vendor(db)
    fac = _service_facility(db, services=[facility.SERVICE_TIRE, facility.SERVICE_WASH])
    claim = _claim(db, vendor, fac)
    m13.decide_claim(db, claim, approve=True, now=T0)

    m13.curate_claim(db, claim, services_added=[facility.SERVICE_TOWING])

    view = m13.claimed_facility_view(db, fac.id)
    assert set(view.services) == {
        facility.SERVICE_TIRE,
        facility.SERVICE_WASH,
        facility.SERVICE_TOWING,
    }
    # and the facility record itself is untouched — nothing wrote back to f02
    assert set(fac.attributes["services"]) == {facility.SERVICE_TIRE, facility.SERVICE_WASH}


def test_curation_adds_hours_and_phone(db):
    vendor, fac = _service_vendor(db), _service_facility(db)
    claim = _claim(db, vendor, fac)
    m13.decide_claim(db, claim, approve=True, now=T0)
    m13.curate_claim(db, claim, hours="Mon-Sat 6a-10p", phone="4175550123")

    view = m13.claimed_facility_view(db, fac.id)
    assert view.hours == "Mon-Sat 6a-10p"
    assert view.phone == "4175550123"
    assert view.vendor_name == "Gateway Truck Service"


def test_curating_twice_never_drops_an_earlier_addition(db):
    vendor, fac = _service_vendor(db), _service_facility(db)
    claim = _claim(db, vendor, fac)
    m13.decide_claim(db, claim, approve=True, now=T0)

    m13.curate_claim(db, claim, services_added=[facility.SERVICE_TOWING])
    m13.curate_claim(db, claim, services_added=[facility.SERVICE_PARTS])

    assert set(claim.services_added) == {facility.SERVICE_TOWING, facility.SERVICE_PARTS}


# --- lifecycle ---
def test_an_unclaimed_facility_stays_a_plain_poi(db):
    fac = _service_facility(db)
    assert m13.claimed_facility_view(db, fac.id) is None


def test_a_pending_claim_does_not_yet_change_the_facility(db):
    vendor, fac = _service_vendor(db), _service_facility(db)
    _claim(db, vendor, fac)
    assert m13.claimed_facility_view(db, fac.id) is None


def test_a_rejected_claim_leaves_the_facility_plain(db):
    vendor, fac = _service_vendor(db), _service_facility(db)
    claim = _claim(db, vendor, fac)
    m13.decide_claim(db, claim, approve=False, now=T0)

    assert claim.status == m13.ClaimStatus.rejected
    assert m13.claimed_facility_view(db, fac.id) is None


def test_a_suspended_claimant_stops_showing_as_the_owner(db):
    vendor, fac = _service_vendor(db), _service_facility(db)
    claim = _claim(db, vendor, fac)
    m13.decide_claim(db, claim, approve=True, now=T0)
    m13.suspend_vendor(db, vendor, True)

    assert m13.claimed_facility_view(db, fac.id) is None


# --- disputes ---
def test_a_second_claimant_becomes_a_dispute_not_a_rejection(db):
    # ownership is a fact about the world; code escalates rather than guesses
    first, fac = _service_vendor(db), _service_facility(db)
    m13.decide_claim(db, _claim(db, first, fac), approve=True, now=T0)

    # a rival business in a NEIGHBOURING metro — Q-5 correctly refuses a same-metro twin
    rival = _service_vendor(db, "rival@x.com", "Gateway Truck Services", metro="springfield-mo")
    dispute = _claim(db, rival, fac)

    assert dispute.status == m13.ClaimStatus.disputed
    assert any(
        i.content_kind == "facility_claim_dispute" for i in admin.list_pending_moderation(db)
    )


def test_a_disputed_claim_cannot_be_approved_while_another_holds_the_facility(db):
    first, fac = _service_vendor(db), _service_facility(db)
    m13.decide_claim(db, _claim(db, first, fac), approve=True, now=T0)
    rival = _service_vendor(db, "rival2@x.com", "Gateway Truck Services", metro="springfield-mo")
    dispute = _claim(db, rival, fac)

    with pytest.raises(m13.AlreadyClaimed):
        m13.decide_claim(db, dispute, approve=True, now=T0)


def test_a_decision_is_recorded_in_the_audit_log(db):
    vendor, fac = _service_vendor(db), _service_facility(db)
    moderator = _account(db, "mod@x.com")
    claim = _claim(db, vendor, fac)
    m13.decide_claim(db, claim, approve=True, moderator_account_id=moderator.id, now=T0)

    actions = [a for a in admin.list_actions(db) if a.action == "facility_claim_decide"]
    assert actions and actions[-1].detail["approved"] is True


def test_claims_for_vendor_lists_their_history(db):
    vendor, fac = _service_vendor(db), _service_facility(db)
    _claim(db, vendor, fac)
    assert len(m13.claims_for_vendor(db, vendor.id)) == 1
