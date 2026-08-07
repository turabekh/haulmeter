"""F-28 and F-29 — the points economy's two check-then-act defects.

F-28: `redeem_points` read a SUMMED balance and then wrote, with no lock. Two concurrent
redemptions both passed the sufficiency check and both posted; nothing in F7 forbids a
negative points account, so it went negative and stayed there.

F-29: the daily contribution cap counts `ContributionLog` rows, but a row was written only
when the contribution EARNED. `_earn_points` reads a live F13 config value, so an admin
setting an earn rate to 0 in the console did not merely stop paying for that contribution
type — it removed the cap on it. The anti-abuse control and the pricing control were the
same lever and nothing said so.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.foundation.f01_identity import public as identity
from app.foundation.f07_ledger import public as ledger
from app.foundation.f10_crowd import public as crowd
from app.foundation.f13_flags import public as flags
from app.modules.m06_parking import public as m6
from app.modules.m10_community import public as m10
from app.modules.m10_community.domain import service as m10_service

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 18, 0, tzinfo=UTC)


def _acct(db, email="d@x.com"):
    return identity.register_account(db, email, "pw-123456")


# --- F-29: the cap and the price are no longer one lever ---
def test_a_zero_earn_rate_still_logs_the_contribution(db):
    driver = _acct(db)
    flags.set_config(db, f"{m10_service.CONFIG_EARN_PREFIX}review", 0, scope="rewards")
    assert m10.award_contribution(db, driver.id, "review", T0) == 0
    assert m10.reputation(db, driver.id).contribution_count == 1
    assert m10.points_balance(db, driver.id) == 0  # logged, but not paid


def test_a_zero_earn_rate_cannot_switch_off_the_daily_cap(db):
    # the defect exactly: set the price to zero in the admin console and the contribution
    # type became invisible to the rate limiter, so it could be submitted without limit
    driver = _acct(db)
    flags.set_config(db, f"{m10_service.CONFIG_EARN_PREFIX}review", 0, scope="rewards")
    for _ in range(m10_service.RATE_LIMIT_PER_DAY):
        m10.award_contribution(db, driver.id, "review", T0)
    with pytest.raises(m10.RateLimited):
        m10.award_contribution(db, driver.id, "review", T0)


def test_an_unpaid_contribution_earns_no_points_on_the_leaderboard(db):
    # logging every contribution must not quietly inflate what a driver appears to have
    # earned — the row carries points=0 and the sums are unchanged
    driver = _acct(db)
    m10.award_contribution(db, driver.id, "review", T0)
    flags.set_config(db, f"{m10_service.CONFIG_EARN_PREFIX}review", 0, scope="rewards")
    m10.award_contribution(db, driver.id, "review", T0)
    assert m10.reputation(db, driver.id).points_earned == 15
    assert m10.reputation(db, driver.id).contribution_count == 2


# --- F-28: redemption ---
def test_redeeming_more_than_the_balance_is_refused(db):
    driver = _acct(db)
    m10.award_contribution(db, driver.id, "review", T0)  # 15
    with pytest.raises(m10.InsufficientPoints):
        m10.redeem_points(db, driver.id, 16, T0)


def test_redemption_takes_the_row_lock_before_reading_the_balance(db, monkeypatch):
    # the ORDERING is the fix, and it is the only part of it a single-transaction test can
    # observe: a lock taken after the read protects nothing. A genuine two-connection proof
    # that the lock blocks is test_the_lock_actually_blocks_a_second_transaction below.
    calls = []
    real_lock = ledger.lock_account
    real_balance = ledger.balance

    def _record(name, fn):
        def wrapped(db, account):
            calls.append(name)
            return fn(db, account)

        return wrapped

    monkeypatch.setattr(m10_service.ledger, "lock_account", _record("lock", real_lock))
    monkeypatch.setattr(m10_service.ledger, "balance", _record("read", real_balance))

    driver = _acct(db)
    m10.award_contribution(db, driver.id, "review", T0)
    calls.clear()
    m10.redeem_points(db, driver.id, 10, T0)
    assert calls[0] == "lock"
    assert "read" in calls


def test_book_with_points_leaves_the_balance_intact_when_the_spot_is_gone(db):
    # the old order redeemed FIRST, so a spot taken in between raised SpotUnavailable with
    # the points already gone — survivable only because get_session() rolls the request
    # back. Nothing rolls back here, and the balance must still be intact.
    owner = _acct(db, "owner@x.com")
    driver = _acct(db, "driver@x.com")
    prop = m6.create_property(db, owner.id, "Yardline Lot", *DALLAS, vetted=True)
    spot = m6.add_spot(db, prop, "A1", price_cents_per_night=2400)
    for _ in range(3):
        m10.award_contribution(db, driver.id, "review", T0)
    before = m10.points_balance(db, driver.id)

    m6.book(db, spot, driver.id, T0, T0 + timedelta(days=2))
    with pytest.raises(m6.SpotUnavailable):
        m10.book_with_points(db, spot, driver.id, T0, T0 + timedelta(days=2), 20, T0)

    assert m10.points_balance(db, driver.id) == before


# --- F-28: the lock, proved across two real connections ---
def test_the_lock_actually_blocks_a_second_transaction(engine):
    """The only test here that can fail if lock_account stops locking.

    Everything above runs in one transaction, where a lock is unobservable — it never
    contends with itself. This one commits, takes the lock on connection A, and gives
    connection B a short `lock_timeout` so "blocks indefinitely" becomes an error pytest
    can catch. It does NOT use the `db` fixture, because that fixture's work is invisible
    to any other connection, which is precisely the condition the race needs.
    """
    account_id = uuid.uuid4()  # ledger_account.owner_ref carries no FK, so no f01 row
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    holder, contender = factory(), factory()
    entry_id = None
    try:
        entry = crowd.issue_points(holder, account_id, 50)
        entry_id = entry.id
        holder.commit()

        holder.execute(text("SET lock_timeout = '2s'"))
        ledger.lock_account(holder, m10_service._points_account(holder, account_id))

        contender.execute(text("SET lock_timeout = '750ms'"))
        with pytest.raises(OperationalError):
            m10.redeem_points(contender, account_id, 50, T0)
    finally:
        contender.rollback()
        contender.close()
        holder.rollback()
        holder.close()
        cleanup = factory()
        try:
            if entry_id is not None:
                cleanup.execute(
                    text("DELETE FROM f07.ledger_posting WHERE entry_id = :e"), {"e": entry_id}
                )
                cleanup.execute(
                    text("DELETE FROM f07.journal_entry WHERE id = :e"), {"e": entry_id}
                )
            cleanup.execute(
                text("DELETE FROM f07.ledger_account WHERE owner_ref = :o"), {"o": account_id}
            )
            cleanup.commit()
        finally:
            cleanup.close()
