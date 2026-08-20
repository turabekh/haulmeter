"""AI-CONTEXT: what a driver gets WITHOUT choosing (§23 entry 231).

Two owner decisions in one place, because they pull in opposite directions and the pair
is the point:

  · `vendor_alert` is ON by default now. The 2026-07-25 entry made it the first opt-in
    class on the reasoning that "silence is never consent"; the owner has reversed that.
    Every OTHER anti-spam law it carries — one a day, route-relevance, quiet hours, the
    per-vendor mute — is untouched, and these tests are what says so.
  · `lot_status_prompt` is DORMANT. Its only switch was removed, so leaving it
    dispatchable would keep asking the drivers who had already opted in while taking
    away the control that turns it off (§21.8: off is exactly as easy as on).

A default only decides for an account with NO preference row. An explicit choice is a
choice, and neither of these may overwrite one.
"""

from datetime import UTC, datetime

from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify

T0 = datetime(2026, 7, 25, 14, 0, tzinfo=UTC)  # outside quiet hours


def _account(db, email):
    return identity.register_account(db, email, "pw-123456")


def _send(db, account, gateway, category, now=T0, subject_ref=None):
    return notify.dispatch(
        db,
        account.id,
        notify.NotificationTier.P1,
        category,
        "Osh at Love's 341",
        "Until 9pm · exit 341",
        "/vendor/abc",
        gateway,
        now=now,
        subject_ref=subject_ref,
    )


def test_a_driver_who_never_chose_gets_vendor_alerts(db):
    """The reversal itself. No preference row, and the alert goes."""
    account = _account(db, "never-chose@example.com")
    gateway = notify.RecordingNotificationGateway()
    note = _send(db, account, gateway, notify.VENDOR_ALERT_CLASS)

    assert note.status == notify.NotificationStatus.queued
    assert note.suppress_reason is None


def test_an_explicit_opt_out_still_wins(db):
    """A default decides for the undecided and for nobody else. A driver who turned
    these off must not be turned back on by a change to what silence means."""
    account = _account(db, "said-no@example.com")
    notify.set_class_opt_in(db, account.id, notify.VENDOR_ALERT_CLASS, False)
    note = _send(db, account, notify.RecordingNotificationGateway(), notify.VENDOR_ALERT_CLASS)

    assert note.suppress_reason == notify.SuppressReason.not_opted_in


def test_the_other_anti_spam_laws_survive_the_flip(db):
    """M13-FR6 is a bundle and only ONE of its clauses was reversed. The cap is the one
    most likely to be lost by accident, because default-on is what makes it bite."""
    account = _account(db, "capped@example.com")
    gateway = notify.RecordingNotificationGateway()
    first = _send(db, account, gateway, notify.VENDOR_ALERT_CLASS)
    second = _send(db, account, gateway, notify.VENDOR_ALERT_CLASS)

    assert first.status == notify.NotificationStatus.queued
    assert second.suppress_reason == notify.SuppressReason.budget


def test_a_muted_vendor_stays_muted_without_a_preference_row(db):
    """The per-vendor mute has to work for a driver who never opted in, because now
    there are such drivers receiving these — there were none before."""
    account = _account(db, "muted@example.com")
    notify.mute_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-9")
    note = _send(
        db, account, notify.RecordingNotificationGateway(),
        notify.VENDOR_ALERT_CLASS, subject_ref="vendor-9",
    )

    assert note.suppress_reason == notify.SuppressReason.muted


def test_the_lot_prompt_is_dormant_even_for_a_driver_who_opted_in(db):
    """THE POINT OF DORMANCY, and the reason clearing rows would not have been enough.

    Three accounts on production hold an explicit `opted_in=true` for this class. Their
    row is a real choice and this code does not erase it — it stops the class dispatching
    at all, so nobody is asked a question whose OFF switch no longer exists.
    """
    account = _account(db, "already-in@example.com")
    notify.set_class_opt_in(db, account.id, notify.LOT_STATUS_PROMPT_CLASS, True)
    gateway = notify.RecordingNotificationGateway()
    note = _send(db, account, gateway, notify.LOT_STATUS_PROMPT_CLASS)

    assert note.status == notify.NotificationStatus.suppressed
    assert note.suppress_reason == notify.SuppressReason.not_opted_in
    assert gateway.sent == []


def test_dormancy_is_declared_on_the_class_and_not_hidden_in_a_branch(db):
    """Reactivation must be one greppable field, the same shape as `MAP_DORMANT` — a
    dormant class scattered through `dispatch` as a special case is a class nobody can
    find again."""
    spec = notify.get_class(notify.LOT_STATUS_PROMPT_CLASS)
    assert spec is not None, "dormant means asleep, not deleted — the laws stay reviewable"
    assert spec.dormant is True
    assert notify.get_class(notify.VENDOR_ALERT_CLASS).dormant is False
