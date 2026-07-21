from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f13_flags import public as flags
from app.modules.m06_parking import public as m6
from app.modules.m10_community import public as m10

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)


def _acct(db, email):
    return identity.register_account(db, email, "pw-123456")


def _present(db, account_id, facility_id, at=T0):
    location.arm_geofence(db, account_id, facility_id)
    location.evaluate_ping(db, account_id, *DALLAS, occurred_at=at)


def _truck_stop(db, name="Loves"):
    return facility.create_facility(db, facility.FacilityType.truck_stop, name, *DALLAS)


def test_flag_registers(db):
    m10.register_module(db)
    assert flags.can_activate(db, "m10_community") is True


def test_earn_credits_points_balance(db):
    driver = _acct(db, "d@x.com")
    assert m10.points_balance(db, driver.id) == 0
    awarded = m10.award_contribution(db, driver.id, "review", T0)
    assert awarded == 15  # EARN_RULES["review"]
    assert m10.points_balance(db, driver.id) == 15


def test_earn_rate_reads_f13_config_knob(db):
    # the per-kind earn rate is a live F13-config knob (edited in the F14 admin
    # console); unset falls back to EARN_RULES, set applies to the next award
    driver = _acct(db, "d@x.com")
    flags.set_config(db, f"{m10.CONFIG_EARN_PREFIX}review", 25, scope="rewards")
    awarded = m10.award_contribution(db, driver.id, "review", T0)
    assert awarded == 25  # the configured rate, not the 15 default
    assert m10.points_balance(db, driver.id) == 25

    # an un-configured kind still uses its compiled default
    assert m10.award_contribution(db, driver.id, "handoff", T0) == 10


def test_redeem_reduces_balance_and_returns_discount(db):
    driver = _acct(db, "d@x.com")
    m10.award_contribution(db, driver.id, "review", T0)  # +15
    discount = m10.redeem_points(db, driver.id, 10, T0)
    assert discount == 10  # 1¢/point
    assert m10.points_balance(db, driver.id) == 5
    with pytest.raises(m10.InsufficientPoints):
        m10.redeem_points(db, driver.id, 999, T0)


def test_rate_limit_blocks_farming(db):
    driver = _acct(db, "d@x.com")
    for i in range(m10.RATE_LIMIT_PER_DAY):
        m10.award_contribution(db, driver.id, "answer", T0 + timedelta(seconds=i))
    with pytest.raises(m10.RateLimited):
        m10.award_contribution(db, driver.id, "answer", T0 + timedelta(seconds=999))


def test_book_with_points_funds_discount_against_m6(db):
    owner = _acct(db, "owner@x.com")
    driver = _acct(db, "driver@x.com")
    prop = m6.create_property(db, owner.id, "Yardline", *DALLAS, vetted=True)
    spot = m6.add_spot(db, prop, "A1", price_cents_per_night=2400)
    # give the driver 20 points to spend
    m10.award_contribution(db, driver.id, "review", T0)
    m10.award_contribution(db, driver.id, "review", T0)  # 30 total
    booking, discount = m10.book_with_points(
        db, spot, driver.id, T0, T0 + timedelta(days=1), points=20
    )
    assert discount == 20  # 20 points -> 20¢
    assert booking.price_cents == 2400  # the driver still books the spot
    assert m10.points_balance(db, driver.id) == 10  # 30 earned - 20 spent


def test_handoff_relay_both_earn_on_confirmed_enter(db):
    broadcaster = _acct(db, "leaver@x.com")
    claimer = _acct(db, "taker@x.com")
    stop = _truck_stop(db)
    _present(db, broadcaster.id, stop.id)
    handoff = m10.broadcast_handoff(db, broadcaster.id, stop.id, T0 + timedelta(minutes=15), T0)
    assert handoff.state == m10.HandoffState.open

    m10.claim_handoff(db, handoff, claimer.id, T0)
    assert handoff.state == m10.HandoffState.claimed

    _present(db, claimer.id, stop.id, at=T0 + timedelta(minutes=10))
    m10.confirm_handoff(db, handoff, T0 + timedelta(minutes=10))
    assert handoff.state == m10.HandoffState.confirmed
    assert m10.points_balance(db, broadcaster.id) == 10  # EARN_RULES["handoff"]
    assert m10.points_balance(db, claimer.id) == 10


def test_handoff_free_lot_only_and_presence_required(db):
    driver = _acct(db, "d@x.com")
    # a bookable M6 property is NOT a free lot — relay must refuse it
    owner = _acct(db, "owner@x.com")
    prop = m6.create_property(db, owner.id, "Yardline", *DALLAS)
    with pytest.raises(m10.NotFreeLot):
        m10.broadcast_handoff(db, driver.id, prop.facility_ref, T0 + timedelta(minutes=15), T0)
    # a free lot but the broadcaster isn't present
    stop = _truck_stop(db)
    with pytest.raises(m10.NotPresent):
        m10.broadcast_handoff(db, driver.id, stop.id, T0 + timedelta(minutes=15), T0)


def test_reputation_and_leaderboard(db):
    a = _acct(db, "a@x.com")
    b = _acct(db, "b@x.com")
    for _ in range(3):
        m10.award_contribution(db, a.id, "review", T0)  # 45
    m10.award_contribution(db, b.id, "answer", T0)  # 5

    rep = m10.reputation(db, a.id)
    assert rep.points_earned == 45
    assert rep.contribution_count == 3
    assert rep.level == "rookie"  # < 100

    board = m10.leaderboard(db, limit=10)
    assert board[0]["account_id"] == a.id  # top contributor leads
    assert board[0]["points"] == 45


def test_facility_qa_presence_gates_answer_earn(db):
    asker = _acct(db, "asker@x.com")
    onsite = _acct(db, "onsite@x.com")
    remote = _acct(db, "remote@x.com")
    stop = _truck_stop(db)
    q = m10.ask_question(db, asker.id, stop.id, "Is the north entrance open?", T0)

    _present(db, onsite.id, stop.id)
    a1 = m10.answer_question(db, onsite.id, q, "Yes, open now.", T0)
    assert a1.presence_proven is True
    assert m10.points_balance(db, onsite.id) == 5  # on-site answer earns

    a2 = m10.answer_question(db, remote.id, q, "Was closed last week.", T0)
    assert a2.presence_proven is False
    assert m10.points_balance(db, remote.id) == 0  # remote answer doesn't earn

    questions = m10.list_questions(db, stop.id)
    assert len(questions) == 1
    assert len(questions[0].answers) == 2
