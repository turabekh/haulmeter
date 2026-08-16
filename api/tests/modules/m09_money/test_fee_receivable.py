"""AI-CONTEXT: the platform's share of a recovery, and the two things it must never be.

J1-R1 (§23 entry 172). The fee is a `fee` RECEIVABLE, not a ledger entry, and it carries
two guards that matter more than the arithmetic:

  1. **No ledger entry.** No cash crossed this platform — the driver invoiced the broker
     in their own name and was paid into their own bank. `m09`'s rationale has said so
     since the recovery path was built and R1 affirmed it unamended. A receivable records
     that something is OWED; a journal entry records that something MOVED.

  2. **No dunning, ever.** The machinery that chases an unpaid receivable was written to
     chase BROKERS. Pointing it at a driver would be this product doing to its own users
     the thing it exists to do FOR them. That guard is structural — a fee receivable has
     no `DetentionClaim`, and dunning selects through claims — and it is asserted here
     rather than trusted, because "nothing can reach it" is exactly the kind of claim that
     stops being true when someone adds a convenient query.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f07_ledger import public as ledger
from app.foundation.f08_notifications import public as notify
from app.foundation.f13_flags import public as flags
from app.modules.m03_detention import public as m3
from app.modules.m09_money import public as m9

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _driver(db, email="fee@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _recoverable(db, account, cents=34000):
    return ledger.create_receivable(db, account.id, ledger.ReceivableKind.detention, cents)


def _on(db):
    m9.register_module(db)
    flags.enable(db, m9.FEE_FLAG)
    db.flush()


def _pay(db, account, receivable):
    return m9.mark_receivable_paid(db, receivable, account.id)


# --- the arithmetic ---


def test_the_fee_is_the_prd_rate_on_what_was_recovered(db):
    """PRD §242/§414: ~15% at the automated stage. $340 recovered -> $51."""
    _on(db)
    assert m9.fee_cents_for(db, 34000) == 5100


def test_the_rate_is_config_because_a_price_is_an_owner_decision(db):
    """PRD §159 lists fee percentages among the things that must be runtime config. A
    price that needs a deploy to change is a price nobody can respond with."""
    _on(db)
    flags.set_config(db, m9.CONFIG_FEE_BASIS_POINTS, 2000)
    db.flush()

    assert m9.fee_cents_for(db, 34000) == 6800


def test_the_fee_can_never_exceed_the_recovery_it_is_taken_from(db):
    _on(db)
    flags.set_config(db, m9.CONFIG_FEE_BASIS_POINTS, 20000)  # an absurd 200%
    db.flush()

    assert m9.fee_cents_for(db, 34000) == 34000


def test_it_is_integer_arithmetic_all_the_way_down(db):
    """Money is cents and basis points here and everywhere else in this ledger; a float
    percentage is how a rounding difference becomes a reconciliation nobody can close."""
    _on(db)
    assert isinstance(m9.fee_cents_for(db, 33333), int)
    assert m9.fee_cents_for(db, 33333) == 5000  # 15% of 333.33 = 49.9995 -> 50.00


# --- what it is ---


def test_a_recovery_posts_a_fee_receivable_against_the_DRIVER(db):
    _on(db)
    account = _driver(db)
    receivable = _recoverable(db, account)

    _pay(db, account, receivable)

    fee = m9.fee_receivable_for(db, receivable)
    assert fee is not None
    assert fee.kind is ledger.ReceivableKind.fee
    assert fee.amount_cents == 5100
    # the SUBJECT is the driver — this is what they owe out of what they were paid
    assert fee.account_id == account.id
    # and NOT a broker: our fee has no business in a counterparty's payment history
    assert fee.counterparty_ref is None


def test_it_posts_NO_ledger_entry(db):
    """R1's first guard, affirming the m09 rationale unamended. No cash crossed this
    platform, so nothing may claim it did."""
    _on(db)
    account = _driver(db)
    receivable = _recoverable(db, account)

    _pay(db, account, receivable)

    assert m9.fee_receivable_for(db, receivable).entry_id is None


def test_posting_it_twice_is_the_same_row(db):
    """`external_ref` is unique-where-present, so a double recovery cannot bill a driver
    twice — the same index that stopped M3 invoicing a broker twice."""
    _on(db)
    account = _driver(db)
    receivable = _recoverable(db, account)

    from app.modules.m09_money.domain import service as m9_service

    _pay(db, account, receivable)
    first = m9.fee_receivable_for(db, receivable)
    # a second post, however it arrives — a retry, a replayed job, a concurrent writer.
    # Reached through the domain module because the poster is private on purpose; what is
    # public is the QUESTION (`fee_receivable_for`), not the act.
    m9_service._post_fee_receivable(db, receivable)

    assert m9.fee_receivable_for(db, receivable).id == first.id


def test_two_recoveries_are_two_fees(db):
    """Idempotency is per RECOVERY, not per driver — a driver who recovers twice owes
    twice, and keying on the account would silently forgive the second."""
    _on(db)
    account = _driver(db)
    one, two = _recoverable(db, account), _recoverable(db, account, 20000)

    _pay(db, account, one)
    _pay(db, account, two)

    assert m9.fee_receivable_for(db, one).id != m9.fee_receivable_for(db, two).id


# --- the flag ---


def test_no_fee_is_posted_while_the_flag_is_off(db):
    """A fee is a PRICE, and a price appears in front of a driver when the owner says so."""
    m9.register_module(db)
    db.flush()
    account = _driver(db)
    receivable = _recoverable(db, account)

    _pay(db, account, receivable)

    assert m9.fee_receivable_for(db, receivable) is None


# --- R1's second guard, structurally ---


def test_no_dunning_path_can_select_a_fee(db):
    """THE guard. Dunning chases BROKERS; pointing it at a driver would be this product
    doing to its own users the thing it exists to do for them.

    It is unreachable by construction — dunning selects through `DetentionClaim`, and a
    fee receivable has no claim — and that is asserted rather than trusted, because
    "nothing can reach it" stops being true the day someone adds a convenient query.
    """
    _on(db)
    account = _driver(db)
    receivable = _recoverable(db, account)
    _pay(db, account, receivable)
    fee = m9.fee_receivable_for(db, receivable)
    assert fee is not None

    # walk the whole cadence, well past every rung, with the gate registered
    gateway = notify.RecordingNotificationGateway()
    for day in (3, 10, 21, 25):
        m3.run_dunning(db, gateway, now=fee.created_at + timedelta(days=day, hours=1))
    notify.retry_unsent_messages(db, gateway)

    assert gateway.sent == []
    assert m3.claim_for_receivable(db, fee.id) is None


def test_the_scan_itself_never_returns_a_fee(db):
    """One layer below the send: the claim scan is what a future caller would reuse, so
    the emptiness has to hold there rather than only at the gateway."""
    _on(db)
    account = _driver(db)
    receivable = _recoverable(db, account)
    _pay(db, account, receivable)
    fee = m9.fee_receivable_for(db, receivable)

    claims = m3.claims_awaiting_dunning(db, fee.created_at + timedelta(days=21))

    assert all(c.receivable_ref != fee.id for c in claims)
