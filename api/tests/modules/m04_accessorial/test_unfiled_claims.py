"""AI-CONTEXT: the half of the money pipeline the Money tab never showed.

The owner watched the Meter accrue on the Load tab, finished the stop, opened Money and
found nothing (§23 entry 226). Nothing was wrong with the arithmetic: the tab lists
FILED claims, and filing is what creates a receivable — so everything before filing was
invisible, including the only money the driver can still act on.
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
LATER = T0 + timedelta(days=10)
FREE = 120


def _driver(db, email):
    account = identity.register_account(db, email, "pw-12345")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    return account


def _claim(db, account, *, dwell_minutes, dock="Harvest Foods DC", broker="Blue Road Logistics",
           start=T0):
    """AI-CONTEXT: `start` exists because F3 REFUSES OUT-OF-ORDER PINGS (F3-3).

    Two claims in one test share an account and therefore one evaluation cursor. Building
    the second one at the same T0 replays pings the cursor has already passed, so they are
    recorded and never evaluated — no presence, no arrival, and a claim that silently
    accrues nothing. The first draft of this fixture did exactly that and the row simply
    vanished from the list rather than failing.
    """
    fac = facility.create_facility(db, facility.FacilityType.shipper_receiver, dock, *DALLAS)
    cp = loads.create_counterparty(
        db, broker, loads.CounterpartyKind.broker, contact_email="ap@blue.com"
    )
    load = loads.create_load(
        db, account.id, counterparty_id=cp.id, reference_number="BL-9",
        detention_rate_cents_per_hour=7500, free_time_minutes=FREE,
    )
    stop = loads.add_stop(db, load, fac.id, loads.StopType.delivery, appointment_start=start)
    claim = m3.start_claim(db, stop, started_at=start)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=start)
    left = start + timedelta(minutes=dwell_minutes)
    location.evaluate_ping(db, account.id, *FAR, occurred_at=left)
    return claim, stop


def test_a_stop_that_ran_past_free_time_and_was_never_filed_is_listed(db):
    account = _driver(db, "unfiled-real@example.com")
    _claim(db, account, dwell_minutes=FREE + 60)  # one hour past, at $75.00/hr

    rows = m4.unfiled_claims(db, account.id, now=LATER)

    assert len(rows) == 1
    assert rows[0]["amount_cents"] == 7500
    assert rows[0]["counterparty_name"] == "Blue Road Logistics"
    assert rows[0]["facility_name"] == "Harvest Foods DC"
    assert rows[0]["stop_id"] is not None, "the row must carry what filing acts on"


def test_a_stop_that_ended_inside_free_time_is_not_listed(db):
    """It owes nothing, `generate_pack` would open no receivable, and on the owner's own
    account every claim is this one — listing them would bury the rows that are money."""
    account = _driver(db, "unfiled-zero@example.com")
    _claim(db, account, dwell_minutes=45)

    assert m4.unfiled_claims(db, account.id, now=LATER) == []


def test_a_filed_claim_leaves_this_list_and_joins_the_owed_one(db):
    """The two halves are exclusive: filing is exactly the thing that moves a row across."""
    account = _driver(db, "unfiled-moves@example.com")
    claim, _stop = _claim(db, account, dwell_minutes=FREE + 60)
    assert len(m4.unfiled_claims(db, account.id, now=LATER)) == 1
    assert m4.money_owed(db, account.id) == []

    m3.generate_pack(db, claim, now=LATER)

    assert m4.unfiled_claims(db, account.id, now=LATER) == []
    assert len(m4.money_owed(db, account.id)) == 1


def test_the_oldest_unbilled_stop_comes_first(db):
    account = _driver(db, "unfiled-order@example.com")
    # BOTH stamped: `created_at` is TRANSACTION time, so an unanchored claim is dated
    # today and ages NEGATIVELY against a fixture `now` in the past — the same trap
    # `test_money_owed_rows.py` records for the receivable it anchors
    new_claim, _ = _claim(db, account, dwell_minutes=FREE + 30, dock="Newer Dock")
    old, _ = _claim(db, account, dwell_minutes=FREE + 30, dock="Older Dock",
                    start=T0 + timedelta(days=1))
    new_claim.created_at = T0
    old.created_at = T0 - timedelta(days=40)
    db.flush()

    rows = m4.unfiled_claims(db, account.id, now=LATER)

    assert rows[0]["facility_name"] == "Older Dock"
    assert rows[0]["aging_days"] > rows[1]["aging_days"]


def test_the_amount_is_the_live_clock_not_the_stored_snapshot(db):
    account = _driver(db, "unfiled-live@example.com")
    claim, _ = _claim(db, account, dwell_minutes=FREE + 120)

    assert claim.amount_cents == 0, "precondition: the stored column is a filing-time snapshot"
    assert m4.unfiled_claims(db, account.id, now=LATER)[0]["amount_cents"] == 15000
