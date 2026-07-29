"""AI-CONTEXT: "claim paid" — §13.2's third P0 example (§23 entry 108).

The gap here was not a missing dispatch site. `ReceivableState.recovered` and F7's
`record_recovery` had existed since the ledger shipped with **no application caller at
all** — only tests — so a claim could never become paid, `recovered_cents` was
structurally $0, and M12's fleet rollup counted a state nothing could reach.

So the first tests are about the ACTION existing, and the notification tests are mostly
about when it must stay silent.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.foundation.f08_notifications import public as notify
from app.modules.m03_detention import public as m3
from app.modules.m09_money import public as m9

DALLAS = (32.7767, -96.7970)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


def _claim_with_receivable(db, email="oo@example.com", amount=15000):
    account = identity.register_account(db, email, "pw-123456")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    broker = loads.create_counterparty(
        db, "Acme", loads.CounterpartyKind.broker, contact_email="ap@acme.com"
    )
    load = loads.create_load(
        db, account.id, counterparty_id=broker.id,
        detention_rate_cents_per_hour=7500, free_time_minutes=120,
    )
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery, appointment_start=T0)
    claim = m3.start_claim(db, stop, started_at=T0)
    receivable = m3.open_receivable(
        db, account.id, ledger.ReceivableKind.detention, amount, counterparty_ref=broker.id
    )
    claim.receivable_ref = receivable.id
    db.flush()
    return account, stop, claim, receivable


# --- the action that did not exist ---
def test_a_receivable_can_finally_be_marked_paid(db):
    account, stop, claim, receivable = _claim_with_receivable(db)
    assert receivable.state == ledger.ReceivableState.invoiced

    m9.mark_receivable_paid(db, receivable, account.id)

    assert receivable.state == ledger.ReceivableState.recovered


def test_paying_it_twice_is_refused_by_the_ledger(db):
    account, stop, claim, receivable = _claim_with_receivable(db)
    m9.mark_receivable_paid(db, receivable, account.id)

    with pytest.raises(ledger.InvalidTransition):
        m9.mark_receivable_paid(db, receivable, account.id)


def test_recovered_money_reaches_the_earnings_dashboard(db):
    """The point of the action: `recovered_cents` was structurally zero before it."""
    account, stop, claim, receivable = _claim_with_receivable(db, amount=15000)
    before = m9.earnings_dashboard(db, account.id).recovered_cents

    m9.mark_receivable_paid(db, receivable, account.id)
    after = m9.earnings_dashboard(db, account.id).recovered_cents

    assert before == 0
    assert after == 15000


# --- the notification, which is mostly a rule about silence ---
def test_the_driver_who_marked_it_is_told_nothing(db):
    """A notification exists to tell someone something they do not already know. The
    driver just tapped "the broker paid this"."""
    account, stop, claim, receivable = _claim_with_receivable(db)
    gw = notify.RecordingNotificationGateway()

    _, sent = m9.mark_receivable_paid(db, receivable, account.id, gateway=gw)

    assert sent is None
    assert gw.sent == []
    assert notify.inbox(db, account.id) == []


def test_a_recovery_recorded_by_someone_else_is_a_p0(db):
    """The case §13.2 means: a fleet manager or the M3-FR7 collection partner records
    it, and the money arriving is genuinely news to the driver."""
    account, stop, claim, receivable = _claim_with_receivable(db)
    someone_else = identity.register_account(db, "fleet@example.com", "pw-123456")
    gw = notify.RecordingNotificationGateway()

    _, sent = m9.mark_receivable_paid(db, receivable, someone_else.id, gateway=gw)

    assert sent is not None
    assert sent.tier == notify.NotificationTier.P0
    assert sent.status == notify.NotificationStatus.sent
    assert sent.title == "Claim paid · $150"
    assert sent.account_id == account.id  # the driver, not the actor


def test_the_p0_deep_links_to_the_claim_not_a_tab_root(db):
    account, stop, claim, receivable = _claim_with_receivable(db)
    other = identity.register_account(db, "fleet2@example.com", "pw-123456")
    gw = notify.RecordingNotificationGateway()

    _, sent = m9.mark_receivable_paid(db, receivable, other.id, gateway=gw)

    assert sent.deep_link == f"/claim/{stop.id}"


def test_an_accessorial_receivable_resolves_to_its_own_stop(db):
    """M3 and M4 are the two modules that open receivables; both must deep-link."""
    from app.modules.m04_accessorial import public as m4

    account, stop, claim, _ = _claim_with_receivable(db, email="acc@example.com")
    load = loads.get_load(db, stop.load_id)
    tonu = m4.file_tonu(db, load, 25000, stop=stop)
    other = identity.register_account(db, "fleet3@example.com", "pw-123456")
    gw = notify.RecordingNotificationGateway()
    receivable = db.get(ledger.Receivable, tonu.receivable_ref)

    _, sent = m9.mark_receivable_paid(db, receivable, other.id, gateway=gw)

    assert sent.deep_link == f"/claim/{stop.id}"


def test_a_receivable_no_claim_owns_is_recorded_but_not_announced(db):
    """§13.5 is enforced by `dispatch` itself, so a receivable that cannot be
    deep-linked is settled silently rather than landing somebody on a tab root."""
    account, stop, claim, _ = _claim_with_receivable(db, email="orphan@example.com")
    orphan = ledger.create_receivable(
        db, account.id, ledger.ReceivableKind.detention, 5000
    )
    other = identity.register_account(db, "fleet4@example.com", "pw-123456")
    gw = notify.RecordingNotificationGateway()

    receivable, sent = m9.mark_receivable_paid(db, orphan, other.id, gateway=gw)

    assert receivable.state == ledger.ReceivableState.recovered
    assert sent is None
    assert gw.sent == []


def test_claim_paid_is_not_an_opt_in_class(db):
    """Same rule §23 entry 106 settled for detention: money-critical P0s carry no
    opt-in switch a driver could be silently un-told by."""
    assert notify.get_class(m9.CLAIM_PAID_CATEGORY) is None


def test_the_p0_outlives_a_spent_budget(db):
    account, stop, claim, receivable = _claim_with_receivable(db)
    other = identity.register_account(db, "fleet5@example.com", "pw-123456")
    gw = notify.RecordingNotificationGateway()
    now = datetime.now(UTC)
    for i in range(notify.MAX_UNPROMPTED_P1_PER_DAY):
        notify.dispatch(
            db, account.id, notify.NotificationTier.P1, "document_expiry",
            f"filler {i}", "b", "/docs", gw, now=now,
        )
    control = notify.dispatch(
        db, account.id, notify.NotificationTier.P1, "document_expiry",
        "control", "b", "/docs", gw, now=now,
    )
    assert control.status == notify.NotificationStatus.suppressed  # the budget is spent

    _, sent = m9.mark_receivable_paid(db, receivable, other.id, gateway=gw, now=now)

    assert sent.status == notify.NotificationStatus.sent


def test_cents_are_not_rounded_away_in_the_figure(db):
    account, stop, claim, receivable = _claim_with_receivable(db, amount=12345)
    other = identity.register_account(db, "fleet6@example.com", "pw-123456")
    gw = notify.RecordingNotificationGateway()

    _, sent = m9.mark_receivable_paid(db, receivable, other.id, gateway=gw)

    assert sent.title == "Claim paid · $123.45"


def test_a_written_off_receivable_cannot_become_paid(db):
    account, stop, claim, receivable = _claim_with_receivable(db)
    ledger.transition_receivable(db, receivable, ledger.ReceivableState.written_off)

    with pytest.raises(ledger.InvalidTransition):
        m9.mark_receivable_paid(db, receivable, account.id)


def test_aging_does_not_change_the_outcome(db):
    """Guards against a future freshness rule being copied here from M3 by reflex:
    money arriving is news whenever it arrives."""
    account, stop, claim, receivable = _claim_with_receivable(db)
    other = identity.register_account(db, "fleet7@example.com", "pw-123456")
    gw = notify.RecordingNotificationGateway()

    _, sent = m9.mark_receivable_paid(
        db, receivable, other.id, gateway=gw, now=datetime.now(UTC) + timedelta(days=90)
    )

    assert sent.status == notify.NotificationStatus.sent
