"""AI-CONTEXT: the year figure, and the property that lets it be large (§23 entry 142).

Entry 142 replaced a Money hero that was wrong three ways — it summed a category the list
did not show, over a lifetime where §10.3 asks for a period, and told a driver they had
received $1,432.50 when they had received $987. The fix was not a better formula. It was
a RULE: **the hero is a sum of the list directly beneath it**, so a driver can add it up
from their own screen.

The year figure inherits that rule and R1 extends it. A gross-of-fee total would be entry
142's mistake again in a smaller way — overstating by exactly what we took — so the figure
is NET, and the rows it is made of show the fee as a visible deduction.

These tests compute the hero from the same rows the list renders and fail on divergence.
That is deliberately not a re-implementation of the formula: it is the reconciliation a
driver would do with a finger on the screen, run in CI.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f07_ledger import public as ledger
from app.foundation.f13_flags import public as flags
from app.modules.m04_accessorial import public as m4
from app.modules.m09_money import public as m9

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _driver(db, email="year@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _on(db):
    m9.register_module(db)
    flags.enable(db, m9.FEE_FLAG)
    db.flush()


def _recovered(db, account, cents):
    r = ledger.create_receivable(db, account.id, ledger.ReceivableKind.detention, cents)
    m9.mark_receivable_paid(db, r, account.id)
    db.flush()
    return r


# --- the reconciliation property ---


def test_the_year_figure_equals_the_rows_beneath_it(db):
    """THE test. Not a re-implementation of the formula — the sum a driver would do with
    a finger on their own screen, over the rows the Money tab actually lists."""
    _on(db)
    account = _driver(db)
    for cents in (34000, 20000, 15000):
        _recovered(db, account, cents)

    summary = m9.earnings_dashboard(db, account.id, now=NOW)
    rows = m4.money_owed(db, account.id, now=NOW)

    listed = [r for r in rows if r["state"] == "recovered"]
    assert summary.recovered_year_net_cents == sum(r["net_cents"] for r in listed)
    assert summary.recovered_year_gross_cents == sum(r["amount_cents"] for r in listed)
    assert summary.fees_year_cents == sum(r["fee_cents"] for r in listed)


def test_the_figure_is_NET_and_therefore_smaller_than_gross(db):
    """A gross year total would overstate by exactly what we took — entry 142's failure
    in a smaller size."""
    _on(db)
    account = _driver(db)
    _recovered(db, account, 34000)

    summary = m9.earnings_dashboard(db, account.id, now=NOW)

    assert summary.recovered_year_gross_cents == 34000
    assert summary.fees_year_cents == 5100
    assert summary.recovered_year_net_cents == 28900


def test_every_row_can_be_taken_apart_into_gross_fee_net(db):
    """§11.7: a figure does not travel without what produced it. Each row carries all
    three, so the deduction is visible rather than implied by a smaller total."""
    _on(db)
    account = _driver(db)
    _recovered(db, account, 34000)

    row = [r for r in m4.money_owed(db, account.id, now=NOW) if r["state"] == "recovered"][0]

    assert row["amount_cents"] == 34000
    assert row["fee_cents"] == 5100
    assert row["net_cents"] == 28900
    assert row["amount_cents"] - row["fee_cents"] == row["net_cents"]


def test_a_recovery_with_no_fee_still_states_all_three(db):
    """Shape does not shift between a recovery with a fee and one without: zero taken,
    the whole amount kept. A missing key would make the screen render an absence as a
    blank where a statement belongs."""
    m9.register_module(db)
    db.flush()  # flag OFF — no fee posted
    account = _driver(db)
    _recovered(db, account, 34000)

    row = [r for r in m4.money_owed(db, account.id, now=NOW) if r["state"] == "recovered"][0]

    assert (row["fee_cents"], row["net_cents"]) == (0, 34000)


def test_only_THIS_year_counts(db):
    """§10.3 asks for a period. A lifetime total presented as a year is the second of
    entry 142's three errors."""
    _on(db)
    account = _driver(db)
    old = ledger.create_receivable(db, account.id, ledger.ReceivableKind.detention, 90000)
    old.created_at = NOW - timedelta(days=400)
    db.flush()
    m9.mark_receivable_paid(db, old, account.id)
    _recovered(db, account, 34000)

    summary = m9.earnings_dashboard(db, account.id, now=NOW)

    assert summary.year == NOW.year
    assert summary.recovered_year_gross_cents == 34000  # last year's $900 is not this year
    assert summary.recovered_cents == 124000  # lifetime still counts both


# --- the fee is not a claim a broker owes ---


def test_a_fee_never_appears_as_money_a_broker_owes(db):
    """The defect this would otherwise have shipped: a fee receivable never leaves
    `invoiced`, so it would have sat in the outstanding list and been SUMMED INTO the
    "what you are owed" hero — our own fee inflating the figure that tells a driver what
    brokers are sitting on. The biggest number on the screen, wrong, in the direction
    that flatters us."""
    _on(db)
    account = _driver(db)
    _recovered(db, account, 34000)

    rows = m4.money_owed(db, account.id, now=NOW)

    assert all(r["kind"] != "fee" for r in rows)
    outstanding = [r for r in rows if r["state"] not in ("recovered", "written_off")]
    assert sum(r["amount_cents"] for r in outstanding) == 0
