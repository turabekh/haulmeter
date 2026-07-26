from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f07_ledger import public as ledger
from app.foundation.f10_crowd import public as crowd
from app.foundation.f13_flags import public as flags

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _facility(db, name="Truck Stop", coords=DALLAS):
    return facility.create_facility(db, facility.FacilityType.truck_stop, name, *coords)


def _make_present(db, account, fac):
    location.arm_geofence(db, account.id, fac.id)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)


def _points_balance(db, account):
    acct = ledger.get_or_create_account(
        db,
        ledger.LedgerAccountKind.points_balance,
        f"points:{account.id}",
        currency=ledger.Currency.points,
        owner_ref=account.id,
    )
    return ledger.balance(db, acct)


def test_presence_proven_submission_awards_points(db):
    account = _account(db)
    fac = _facility(db)
    _make_present(db, account, fac)
    sub = crowd.submit(
        db,
        account.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "full"},
        submitted_at=T0,
    )
    assert sub.presence_proven is True
    assert (
        _points_balance(db, account) == crowd.POINTS_PER_SIGNAL[crowd.SignalType.parking_fullness]
    )


def test_unproven_submission_recorded_but_no_points(db):
    account = _account(db)
    fac = _facility(db)
    sub = crowd.submit(
        db,
        account.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "some"},
        submitted_at=T0,
    )
    assert sub.presence_proven is False
    assert _points_balance(db, account) == 0


def test_submit_unknown_facility_raises(db):
    import uuid

    account = _account(db)
    with pytest.raises(crowd.FacilityNotFound):
        crowd.submit(
            db,
            account.id,
            uuid.uuid4(),
            crowd.SignalType.fuel_price,
            {"price_cents": 459},
            submitted_at=T0,
        )


def test_award_cooldown_blocks_second_award_but_belief_still_updates(db):
    # a driver re-reporting the same signal at the same facility inside the cooldown
    # window earns points once; the belief still moves to their freshest reading.
    account = _account(db)
    fac = _facility(db)
    _make_present(db, account, fac)
    unit = crowd.POINTS_PER_SIGNAL[crowd.SignalType.parking_fullness]

    crowd.submit(
        db,
        account.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "full"},
        submitted_at=T0,
    )
    assert _points_balance(db, account) == unit

    # re-report 2h later (< 6h default cooldown): no second award...
    later = T0 + timedelta(hours=2)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=later)
    sub2 = crowd.submit(
        db,
        account.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "empty"},
        submitted_at=later,
    )
    assert sub2.awarded is False
    assert _points_balance(db, account) == unit  # unchanged

    # ...but the belief still updated to the freshest reading
    belief = crowd.update_belief(db, fac.id, crowd.SignalType.parking_fullness, as_of=later)
    assert belief.value == {"status": "empty"}


def test_award_resumes_after_cooldown_window(db):
    account = _account(db)
    fac = _facility(db)
    _make_present(db, account, fac)
    unit = crowd.POINTS_PER_SIGNAL[crowd.SignalType.parking_fullness]

    crowd.submit(
        db,
        account.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "full"},
        submitted_at=T0,
    )
    # 7h later (> 6h default cooldown): award resumes
    after = T0 + timedelta(hours=7)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=after)
    sub2 = crowd.submit(
        db,
        account.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "full"},
        submitted_at=after,
    )
    assert sub2.awarded is True
    assert _points_balance(db, account) == unit * 2


def test_award_cooldown_is_per_driver(db):
    # the cooldown is keyed to the driver — two distinct drivers reporting inside the
    # window are BOTH awarded (only self-farming is blocked).
    fac = _facility(db)
    unit = crowd.POINTS_PER_SIGNAL[crowd.SignalType.parking_fullness]
    a = _account(db, "a@example.com")
    b = _account(db, "b@example.com")
    _make_present(db, a, fac)
    _make_present(db, b, fac)

    crowd.submit(
        db,
        a.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "full"},
        submitted_at=T0,
    )
    crowd.submit(
        db,
        b.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "full"},
        submitted_at=T0,
    )
    assert _points_balance(db, a) == unit
    assert _points_balance(db, b) == unit


def test_award_cooldown_duration_is_f13_configurable(db):
    # shrinking the window via F13 config lets an award resume sooner
    flags.set_config(db, crowd.CONFIG_AWARD_COOLDOWN_KEY, 60)  # 1 minute
    account = _account(db)
    fac = _facility(db)
    _make_present(db, account, fac)
    unit = crowd.POINTS_PER_SIGNAL[crowd.SignalType.parking_fullness]

    crowd.submit(
        db,
        account.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "full"},
        submitted_at=T0,
    )
    after = T0 + timedelta(minutes=2)  # past the shrunken 1-min window
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=after)
    crowd.submit(
        db,
        account.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "full"},
        submitted_at=after,
    )
    assert _points_balance(db, account) == unit * 2


def test_authoritative_submissions_never_award_regardless_of_cooldown(db):
    # a feed (TPIMS) carries no account and issues no points, so the cooldown never
    # applies to it — repeated feed readings never touch a points balance.
    fac = _facility(db)
    for i in range(3):
        crowd.submit_authoritative(
            db,
            fac.id,
            crowd.SignalType.parking_fullness,
            {"status": "full", "source": "tpims"},
            submitted_at=T0 + timedelta(minutes=i),
            source="tpims",
        )
    pool = ledger.get_or_create_account(
        db, ledger.LedgerAccountKind.points_pool, "points:pool", currency=ledger.Currency.points
    )
    assert ledger.balance(db, pool) == 0


def test_trust_scoring_adjusts(db):
    account = _account(db)
    base = crowd.get_or_create_trust(db, account.id).score
    crowd.adjust_trust(db, account.id, confirmed=True)
    up = crowd.get_or_create_trust(db, account.id).score
    assert up > base
    crowd.adjust_trust(db, account.id, confirmed=False)
    down = crowd.get_or_create_trust(db, account.id).score
    assert down < up


def test_categorical_belief_is_trust_and_recency_weighted(db):
    fac = _facility(db)
    truster = _account(db, "trusted@example.com")
    _make_present(db, truster, fac)
    crowd.adjust_trust(db, truster.id, confirmed=True)  # bump trust above base
    crowd.adjust_trust(db, truster.id, confirmed=True)
    doubter = _account(db, "new@example.com")

    # one high-trust "full" vs one base-trust "empty"
    crowd.submit(
        db,
        truster.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "full"},
        submitted_at=T0,
    )
    crowd.submit(
        db,
        doubter.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "empty"},
        submitted_at=T0,
        award=False,
    )
    belief = crowd.aggregate_belief(db, fac.id, crowd.SignalType.parking_fullness, as_of=T0)
    assert belief.value == {"status": "full"}
    assert belief.sample_size == 2
    assert 0.0 < belief.confidence <= 1.0


def test_one_driver_reporting_repeatedly_counts_once(db):
    # a driver re-reporting the same spot must NOT inflate the "N drivers" count or
    # stack weight onto their own opinion — only their freshest reading counts.
    fac = _facility(db)
    spammer = _account(db, "spammer@example.com")
    for i in range(4):  # same driver, four reports, changing their mind on the last
        crowd.submit(
            db,
            spammer.id,
            fac.id,
            crowd.SignalType.parking_fullness,
            {"status": "empty" if i < 3 else "full"},
            submitted_at=T0 + timedelta(minutes=i),
            award=False,
        )
    at = T0 + timedelta(minutes=4)
    belief = crowd.aggregate_belief(db, fac.id, crowd.SignalType.parking_fullness, as_of=at)
    assert belief.sample_size == 1  # one distinct driver, not four
    assert belief.value == {"status": "full"}  # their freshest opinion wins, not a stacked tally

    # a second, distinct driver now genuinely makes it two
    other = _account(db, "other@example.com")
    crowd.submit(
        db,
        other.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "full"},
        submitted_at=T0 + timedelta(minutes=4),
        award=False,
    )
    at = T0 + timedelta(minutes=4)
    belief = crowd.aggregate_belief(db, fac.id, crowd.SignalType.parking_fullness, as_of=at)
    assert belief.sample_size == 2  # two distinct drivers


def test_time_decay_favours_fresher_reports(db):
    fac = _facility(db)
    a = _account(db, "a@example.com")
    b = _account(db, "b@example.com")
    # stale "full" from 3h ago, fresh "empty" now — parking half-life is 1h
    crowd.submit(
        db,
        a.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "full"},
        submitted_at=T0 - timedelta(hours=3),
        award=False,
    )
    crowd.submit(
        db,
        b.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "empty"},
        submitted_at=T0,
        award=False,
    )
    belief = crowd.aggregate_belief(db, fac.id, crowd.SignalType.parking_fullness, as_of=T0)
    assert belief.value == {"status": "empty"}


def test_numeric_belief_weighted_average(db):
    fac = _facility(db, "Fuel")
    a = _account(db, "a@example.com")
    b = _account(db, "b@example.com")
    crowd.submit(
        db,
        a.id,
        fac.id,
        crowd.SignalType.fuel_price,
        {"price_cents": 400},
        submitted_at=T0,
        award=False,
    )
    crowd.submit(
        db,
        b.id,
        fac.id,
        crowd.SignalType.fuel_price,
        {"price_cents": 500},
        submitted_at=T0,
        award=False,
    )
    belief = crowd.aggregate_belief(db, fac.id, crowd.SignalType.fuel_price, as_of=T0)
    assert belief.value["price_cents"] == 450


def test_update_and_get_belief_persists(db):
    fac = _facility(db)
    a = _account(db, "a@example.com")
    crowd.submit(
        db,
        a.id,
        fac.id,
        crowd.SignalType.weigh_station_status,
        {"open": True},
        submitted_at=T0,
        award=False,
    )
    crowd.update_belief(db, fac.id, crowd.SignalType.weigh_station_status, as_of=T0)
    stored = crowd.get_belief(db, fac.id, crowd.SignalType.weigh_station_status)
    assert stored.value == {"open": True}
    assert stored.sample_size == 1


def test_no_belief_when_no_recent_submissions(db):
    fac = _facility(db)
    a = _account(db, "a@example.com")
    crowd.submit(
        db,
        a.id,
        fac.id,
        crowd.SignalType.parking_fullness,
        {"status": "full"},
        submitted_at=T0 - timedelta(days=2),
        award=False,
    )
    belief = crowd.aggregate_belief(db, fac.id, crowd.SignalType.parking_fullness, as_of=T0)
    assert belief is None
