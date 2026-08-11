"""Findings F1 and F2 — one open claim per stop, one receivable per filing, in Postgres.

These deliberately bypass the service layer. A test that only exercises the application
guard proves nothing about the race the guard cannot see: `claim_for_stop(...) or
start_claim(...)` reads committed rows, and a concurrent transaction's insert is not one
of them. The service-level behaviour is `test_claim_idempotency.py`; this file is about
what the database refuses on its own.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.modules.m03_detention.domain.enums import ClaimMode, ClaimState
from app.modules.m03_detention.domain.models import DetentionClaim

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


def _stop(db, email="oo@example.com"):
    account = identity.register_account(db, email, "pw-123456")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    load = loads.create_load(
        db, account.id, detention_rate_cents_per_hour=7500, free_time_minutes=120
    )
    return account, loads.add_stop(db, load, dock.id, loads.StopType.delivery, appointment_start=T0)


def _raw_claim(account, stop, state=ClaimState.open):
    return DetentionClaim(
        stop_ref=stop.id,
        facility_ref=stop.facility_id,
        account_id=account.id,
        mode=ClaimMode.invoice,
        free_time_minutes=120,
        detention_rate_cents_per_hour=7500,
        clock_since=T0,
        state=state,
    )


def test_the_database_refuses_a_second_open_claim_for_one_stop(db):
    account, stop = _stop(db)
    db.add(_raw_claim(account, stop))
    db.flush()

    db.add(_raw_claim(account, stop))
    with pytest.raises(IntegrityError):
        db.flush()


def test_a_stop_may_carry_history_beside_its_open_claim(db):
    """The predicate is `state = 'open'`, not the column — a driver returns to a dock."""
    account, stop = _stop(db)
    db.add(_raw_claim(account, stop, state=ClaimState.invoiced))
    db.add(_raw_claim(account, stop, state=ClaimState.exported))
    db.flush()

    db.add(_raw_claim(account, stop, state=ClaimState.open))
    db.flush()  # the one open claim is still allowed alongside two filed ones

    assert db.query(DetentionClaim).filter_by(stop_ref=stop.id).count() == 3


def test_the_database_refuses_a_second_receivable_for_one_external_ref(db):
    account, _ = _stop(db)
    ref = "m03:11111111-1111-1111-1111-111111111111"
    ledger.create_receivable(
        db, account.id, ledger.ReceivableKind.detention, 15000, external_ref=ref
    )
    db.flush()

    # `create_receivable` flushes, so the database refuses inside the call itself
    with pytest.raises(IntegrityError):
        ledger.create_receivable(
            db, account.id, ledger.ReceivableKind.detention, 15000, external_ref=ref
        )


def test_receivables_without_an_external_ref_are_unconstrained(db):
    """Partial on NOT NULL: M4 and the other openers still pass nothing."""
    account, _ = _stop(db)
    ledger.create_receivable(db, account.id, ledger.ReceivableKind.detention, 15000)
    ledger.create_receivable(db, account.id, ledger.ReceivableKind.detention, 15000)
    db.flush()  # two NULLs are not a duplicate
