"""AI-CONTEXT: opt-in notification classes (design-prd §23 E-D1).

A class is a bundle of interruption laws stricter than its tier: OFF until the
driver turns it on, its own daily cap on top of the §13.1 budget, quiet hours, and
a one-tap per-subject mute. These tests are the enforcement — the laws are only
real if silence stays silent and the cap actually bites.
"""

from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify

T0 = datetime(2026, 7, 25, 14, 0, tzinfo=UTC)  # outside quiet hours


def _account(db, email="alerts@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _gateway():
    return notify.RecordingNotificationGateway()


def _send(db, account, gateway, now=T0, subject_ref=None, category=notify.VENDOR_ALERT_CLASS):
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


def test_class_is_off_until_the_driver_opts_in(db):
    # never asked = never consented. The absence of a preference row must read as
    # OFF, not as "no objection".
    account = _account(db)
    gateway = _gateway()
    note = _send(db, account, gateway)

    assert note.status == notify.NotificationStatus.suppressed
    assert note.suppress_reason == notify.SuppressReason.not_opted_in
    assert gateway.sent == []


def test_opting_in_lets_the_alert_through(db):
    account = _account(db, "in@example.com")
    notify.set_class_opt_in(db, account.id, notify.VENDOR_ALERT_CLASS, True)
    gateway = _gateway()
    note = _send(db, account, gateway)

    assert note.status == notify.NotificationStatus.sent
    assert len(gateway.sent) == 1


def test_opting_back_out_stops_them_again(db):
    account = _account(db, "out@example.com")
    notify.set_class_opt_in(db, account.id, notify.VENDOR_ALERT_CLASS, True)
    notify.set_class_opt_in(db, account.id, notify.VENDOR_ALERT_CLASS, False)
    note = _send(db, account, _gateway())
    assert note.suppress_reason == notify.SuppressReason.not_opted_in


def test_class_cap_is_one_per_day(db):
    # FR6 anti-spam: at most one vendor push per driver per day, whatever the P1
    # budget would otherwise allow
    account = _account(db, "cap@example.com")
    notify.set_class_opt_in(db, account.id, notify.VENDOR_ALERT_CLASS, True)
    gateway = _gateway()

    first = _send(db, account, gateway, now=T0)
    second = _send(db, account, gateway, now=T0 + timedelta(hours=2))

    assert first.status == notify.NotificationStatus.sent
    assert second.status == notify.NotificationStatus.suppressed
    assert second.suppress_reason == notify.SuppressReason.budget
    assert len(gateway.sent) == 1


def test_the_cap_reopens_after_the_window(db):
    account = _account(db, "window@example.com")
    notify.set_class_opt_in(db, account.id, notify.VENDOR_ALERT_CLASS, True)
    gateway = _gateway()

    _send(db, account, gateway, now=T0)
    later = _send(db, account, gateway, now=T0 + timedelta(hours=25))

    assert later.status == notify.NotificationStatus.sent
    assert len(gateway.sent) == 2


def test_muting_one_vendor_leaves_the_rest_of_the_class_on(db):
    # one-tap mute per vendor: a driver silences one cook without losing the feature
    account = _account(db, "mute@example.com")
    notify.set_class_opt_in(db, account.id, notify.VENDOR_ALERT_CLASS, True)
    notify.mute_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-1")
    gateway = _gateway()

    muted = _send(db, account, gateway, subject_ref="vendor-1")
    other = _send(db, account, gateway, subject_ref="vendor-2")

    assert muted.suppress_reason == notify.SuppressReason.muted
    assert other.status == notify.NotificationStatus.sent


def test_class_respects_quiet_hours(db):
    account = _account(db, "quiet@example.com")
    notify.set_class_opt_in(db, account.id, notify.VENDOR_ALERT_CLASS, True)
    night = datetime(2026, 7, 25, 23, 30, tzinfo=UTC)  # inside the 22:00-06:00 default

    note = _send(db, account, _gateway(), now=night)
    assert note.suppress_reason == notify.SuppressReason.quiet_hours


def test_ungoverned_categories_are_unaffected(db):
    # the gate must only touch registered classes — every existing notification
    # category keeps its plain tier behavior
    account = _account(db, "plain@example.com")
    gateway = _gateway()
    note = _send(db, account, gateway, category="detention_started")

    assert notify.get_class("detention_started") is None
    assert note.status == notify.NotificationStatus.sent


def test_vendor_alert_class_declares_its_anti_spam_laws(db):
    spec = notify.get_class(notify.VENDOR_ALERT_CLASS)
    assert spec.opt_in_default is False
    assert spec.max_per_day == 1
    assert spec.route_relevant_only is True
    assert spec.tier == notify.NotificationTier.P1  # never P0 — food is not urgent
