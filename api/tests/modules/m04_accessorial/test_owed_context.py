"""AI-CONTEXT: the Money tab said "add your first load" to a driver holding seven.

Reproduces the state the owner reported on 2026-08-19 (§23 entry 215), measured on
production before a line was changed: `turabekh@gmail.com` had 7 loads and 14 detention
claims, every claim `open` with `detention_seconds = 0`, because every stop had ended
INSIDE its free time. No claim accrued, so no receivable opened, so `money_owed` was
correctly empty — and §15.3's single empty sentence told the driver to do the one thing
they had already done fourteen times. An empty state that can only describe a driver who
has done nothing reads, to everyone else, as a broken screen.

The cases below are the four the tab must tell apart, and the third is the only one with
money in it.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.modules.m03_detention import public as m3
from app.modules.m04_accessorial import public as m4

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
FREE_TIME = 120


def _driver(db, email):
    account = identity.register_account(db, email, "pw-12345")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    return account


def _stop_with_claim(db, account, *, arrived, departed):
    """A started claim whose stop was arrived at and left — the shape of every real one."""
    dock = facility.create_facility(
        db, facility.FacilityType.shipper_receiver, "Dallas Cold Storage", *DALLAS
    )
    cp = loads.create_counterparty(
        db, "Acme Brokerage", loads.CounterpartyKind.broker, contact_email="ap@acme.com"
    )
    load = loads.create_load(
        db, account.id, counterparty_id=cp.id, reference_number="BL-77",
        detention_rate_cents_per_hour=7500, free_time_minutes=FREE_TIME,
    )
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery, appointment_start=T0)
    claim = m3.start_claim(db, stop, started_at=arrived)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=arrived)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=departed)
    return claim


def test_a_driver_who_has_never_recorded_a_load_says_so(db):
    account = _driver(db, "ctx-none@example.com")

    ctx = m4.owed_context(db, account.id)

    assert ctx == {"has_loads": False, "open_claims": 0, "accrued_unfiled_cents": 0}


def test_the_owners_state_loads_and_claims_that_accrued_nothing(db):
    """THE REPORTED BUG. Seven loads, claims open, every stop inside its free time."""
    account = _driver(db, "ctx-freetime@example.com")
    for _ in range(3):
        _stop_with_claim(db, account, arrived=T0, departed=T0 + timedelta(minutes=45))

    ctx = m4.owed_context(db, account.id, now=T0 + timedelta(days=1))

    assert ctx["has_loads"] is True, "the driver has recorded loads and the tab must know"
    assert ctx["open_claims"] == 3
    assert ctx["accrued_unfiled_cents"] == 0, "45 minutes is inside 120 of free time"
    assert m4.money_owed(db, account.id) == [], "nothing accrued, so nothing is owed — correctly"


def test_money_already_accrued_on_a_stop_that_was_never_filed(db):
    """The case worth money: the meter ran past free time and nobody filed the claim."""
    account = _driver(db, "ctx-unfiled@example.com")
    _stop_with_claim(db, account, arrived=T0, departed=T0 + timedelta(minutes=FREE_TIME + 60))

    ctx = m4.owed_context(db, account.id, now=T0 + timedelta(days=1))

    assert ctx["open_claims"] == 1
    # one hour past free time at $75.00/hr, and the driver has not billed anybody for it
    assert ctx["accrued_unfiled_cents"] == 7500
    assert m4.money_owed(db, account.id) == [], "unfiled money is not owed money — yet"


def test_the_accrued_figure_comes_from_the_live_clock_not_the_stored_column(db):
    """`claim.amount_cents` is written at FILING time and reads 0 on every open claim.

    A context built from the column would report zero for a driver sitting on real
    detention — a zero that means "not measured" (TRAPS), on the one screen where a
    zero is the reported symptom.
    """
    account = _driver(db, "ctx-snapshot@example.com")
    claim = _stop_with_claim(
        db, account, arrived=T0, departed=T0 + timedelta(minutes=FREE_TIME + 120)
    )

    assert claim.amount_cents == 0, "precondition: the stored snapshot is still zero"
    ctx = m4.owed_context(db, account.id, now=T0 + timedelta(days=1))
    assert ctx["accrued_unfiled_cents"] == 15000
