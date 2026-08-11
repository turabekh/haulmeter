"""Findings F1 and F2 — the claim lifecycle at the service layer.

`test_claim_uniqueness.py` is about what Postgres refuses on its own; this is about what
the product does when it meets that refusal. The two halves are separate on purpose: a
service test that passes because the application guard ran first proves nothing about the
concurrent case, and a database test proves nothing about what a driver sees. F3 and the
HTTP status codes are in `tests/api/test_detention_idempotency_api.py`.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.modules.m03_detention import public as m3
from app.modules.m03_detention.domain.models import DetentionClaim

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
FILED = T0 + timedelta(minutes=240)


def _stop(db, email="oo@example.com", broker_email="ap@acme.com"):
    account = identity.register_account(db, email, "pw-123456")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    broker = loads.create_counterparty(
        db, "Acme", loads.CounterpartyKind.broker, contact_email=broker_email
    )
    load = loads.create_load(
        db, account.id, counterparty_id=broker.id,
        detention_rate_cents_per_hour=7500, free_time_minutes=120,
    )
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery, appointment_start=T0)
    return account, stop


def _visit(db, account, arrival=T0, departure=FILED):
    """A pack needs a non-empty chain, and the chain is built from F3 geofence events."""
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=arrival)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=departure)


# --- F1: get-or-create ---
def test_starting_a_claim_twice_returns_the_same_claim(db):
    _, stop = _stop(db)

    first = m3.start_claim(db, stop, started_at=T0)
    second = m3.start_claim(db, stop, started_at=T0)

    assert first.id == second.id
    assert db.query(DetentionClaim).filter_by(stop_ref=stop.id).count() == 1


def test_a_filed_claim_does_not_block_a_new_one_for_the_same_stop(db):
    """The driver comes back to the same dock on another load."""
    account, stop = _stop(db)
    first = m3.start_claim(db, stop, started_at=T0)
    _visit(db, account)
    m3.generate_pack(db, first, now=FILED)

    second = m3.start_claim(db, stop, started_at=FILED)

    assert second.id != first.id
    assert second.state == m3.ClaimState.open


def test_claim_for_stop_prefers_the_open_claim_over_history(db):
    account, stop = _stop(db)
    filed = m3.start_claim(db, stop, started_at=T0)
    _visit(db, account)
    m3.generate_pack(db, filed, now=FILED)
    running = m3.start_claim(db, stop, started_at=FILED)

    assert m3.claim_for_stop(db, stop.id).id == running.id


def test_claim_for_stop_answers_with_history_when_nothing_is_open(db):
    """It used to RAISE here: `db.scalar` over an unordered set of two."""
    account, stop = _stop(db)
    older = m3.start_claim(db, stop, started_at=T0)
    _visit(db, account)
    m3.generate_pack(db, older, now=FILED)
    newer = m3.start_claim(db, stop, started_at=FILED)
    _visit(db, account, arrival=FILED + timedelta(minutes=1),
           departure=FILED + timedelta(minutes=240))
    m3.generate_pack(db, newer, now=FILED + timedelta(minutes=240))
    # `created_at` defaults to `now()`, which is TRANSACTION time — both rows would
    # otherwise carry the same instant and "most recent" would have nothing to read
    older.created_at = T0
    newer.created_at = FILED
    db.flush()

    assert m3.claim_for_stop(db, stop.id).id == newer.id


# --- F2: filing is once-only ---
def test_filing_a_company_drivers_pack_twice_is_refused(db):
    """The case the unique index CANNOT cover, which is why the state guard has to exist.

    A company driver files evidence-only: no receivable, so no `external_ref` and nothing
    for `uq_receivable_external_ref` to catch. The claim's own state is the only thing
    standing between one stop and an unbounded number of re-anchored evidence packs.
    """
    account = identity.register_account(db, "company@example.com", "pw-123456")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.company)
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    load = loads.create_load(
        db, account.id, detention_rate_cents_per_hour=7500, free_time_minutes=120
    )
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery, appointment_start=T0)
    claim = m3.start_claim(db, stop, started_at=T0)
    _visit(db, account)
    m3.generate_pack(db, claim, now=FILED)
    assert claim.state == m3.ClaimState.exported

    with pytest.raises(m3.ClaimAlreadyFiled):
        m3.generate_pack(db, claim, now=FILED)


def test_filing_a_claim_twice_is_refused(db):
    account, stop = _stop(db)
    claim = m3.start_claim(db, stop, started_at=T0)
    _visit(db, account)
    m3.generate_pack(db, claim, now=FILED)

    with pytest.raises(m3.ClaimAlreadyFiled):
        m3.generate_pack(db, claim, now=FILED)


def test_one_detention_opens_exactly_one_receivable(db):
    account, stop = _stop(db)
    claim = m3.start_claim(db, stop, started_at=T0)
    _visit(db, account)
    m3.generate_pack(db, claim, now=FILED)

    with pytest.raises(m3.ClaimAlreadyFiled):
        m3.generate_pack(db, claim, now=FILED)

    receivables = ledger.list_receivables(db, account.id)
    assert len(receivables) == 1
    assert receivables[0].amount_cents == claim.amount_cents


def test_the_receivable_carries_the_claim_as_its_external_ref(db):
    """The ref is DERIVED from the claim, which is what makes the index a race backstop."""
    account, stop = _stop(db)
    claim = m3.start_claim(db, stop, started_at=T0)
    _visit(db, account)
    result = m3.generate_pack(db, claim, now=FILED)

    assert result["receivable"].external_ref == f"m03:{claim.id}"


def test_the_refusal_carries_the_receivable_the_first_filing_opened(db):
    account, stop = _stop(db)
    claim = m3.start_claim(db, stop, started_at=T0)
    _visit(db, account)
    result = m3.generate_pack(db, claim, now=FILED)

    with pytest.raises(m3.ClaimAlreadyFiled) as caught:
        m3.generate_pack(db, claim, now=FILED)

    assert caught.value.claim.receivable_ref == result["receivable"].id
