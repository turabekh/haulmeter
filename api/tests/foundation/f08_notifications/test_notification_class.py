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


def test_a_dormant_class_is_off_however_the_driver_answered(db):
    # "never asked = never consented" was this class's rule until §23 entry 231; the
    # owner reversed it for `vendor_alert` and the assertion moved rather than
    # disappeared. `lot_status_prompt` is the class that is off for everyone now, and
    # its rule is stronger: dormant beats even an explicit yes, because the switch that
    # would take it back is gone (§21.8).
    account = _account(db)
    gateway = _gateway()
    notify.set_class_opt_in(db, account.id, notify.LOT_STATUS_PROMPT_CLASS, True)
    note = _send(db, account, gateway, category=notify.LOT_STATUS_PROMPT_CLASS)

    assert note.status == notify.NotificationStatus.suppressed
    assert note.suppress_reason == notify.SuppressReason.not_opted_in
    assert gateway.sent == []


def test_opting_in_lets_the_alert_through(db):
    account = _account(db, "in@example.com")
    notify.set_class_opt_in(db, account.id, notify.VENDOR_ALERT_CLASS, True)
    gateway = _gateway()
    note = _send(db, account, gateway)

    assert note.status == notify.NotificationStatus.queued
    # the push_delivery sweep is what hands a queued notification to the
    # push service; the request only decides (§13.1 laws included)
    notify.deliver_queued_notifications(db, lambda _a: gateway)
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

    assert first.status == notify.NotificationStatus.queued
    assert second.status == notify.NotificationStatus.suppressed
    assert second.suppress_reason == notify.SuppressReason.budget
    # the push_delivery sweep is what hands a queued notification to the
    # push service; the request only decides (§13.1 laws included)
    notify.deliver_queued_notifications(db, lambda _a: gateway)
    assert len(gateway.sent) == 1


def test_the_cap_reopens_after_the_window(db):
    account = _account(db, "window@example.com")
    notify.set_class_opt_in(db, account.id, notify.VENDOR_ALERT_CLASS, True)
    gateway = _gateway()

    _send(db, account, gateway, now=T0)
    later = _send(db, account, gateway, now=T0 + timedelta(hours=25))

    assert later.status == notify.NotificationStatus.queued
    # the push_delivery sweep is what hands a queued notification to the
    # push service; the request only decides (§13.1 laws included)
    notify.deliver_queued_notifications(db, lambda _a: gateway)
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
    assert other.status == notify.NotificationStatus.queued


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
    assert note.status == notify.NotificationStatus.queued


def test_vendor_alert_class_declares_its_anti_spam_laws(db):
    spec = notify.get_class(notify.VENDOR_ALERT_CLASS)
    # §23 entry 231 reversed ONE clause of M13-FR6 — the default — and the rest of the
    # bundle is asserted here precisely because a reversal is where the others get lost.
    assert spec.opt_in_default is True
    assert spec.max_per_day == 1
    assert spec.route_relevant_only is True
    assert spec.tier == notify.NotificationTier.P1  # never P0 — food is not urgent


# --- following: the positive half of the same preference ---
def test_following_is_consent_and_turns_the_class_on(db):
    # A deliberate tap on "follow" is a request to be told, and a follow into a class
    # that stayed OFF would be a control that reports success and does nothing. Since
    # §23 entry 231 the class no longer starts off, so the thing worth proving is that
    # follow still lands an EXPLICIT yes over an opt-out rather than relying on the
    # default to carry it.
    account = _account(db, "follow-on@example.com")
    notify.set_class_opt_in(db, account.id, notify.VENDOR_ALERT_CLASS, False)
    assert notify.is_opted_in(db, account.id, notify.VENDOR_ALERT_CLASS) is False

    notify.follow_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-1")

    assert notify.is_opted_in(db, account.id, notify.VENDOR_ALERT_CLASS) is True
    assert notify.is_following(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-1") is True


def test_following_clears_an_older_mute_on_the_same_subject(db):
    # muted months ago, followed today: the newer, explicit choice wins. Otherwise
    # the follow silently does nothing and the driver cannot see why.
    account = _account(db, "follow-unmute@example.com")
    notify.mute_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-2")
    assert notify.is_subject_muted(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-2") is True

    notify.follow_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-2")

    assert notify.is_subject_muted(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-2") is False
    gateway = _gateway()
    sent = _send(db, account, gateway, subject_ref="vendor-2")
    assert sent.status == notify.NotificationStatus.queued


def test_unfollowing_leaves_the_class_on(db):
    """Dropping one cook is not leaving the class. Turning it off is a separate,
    louder choice, and making it for someone would take away notifications they
    never asked to lose."""
    account = _account(db, "unfollow@example.com")
    notify.follow_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-3")
    notify.unfollow_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-3")

    assert notify.is_following(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-3") is False
    assert notify.is_opted_in(db, account.id, notify.VENDOR_ALERT_CLASS) is True


def test_unfollowing_something_never_followed_is_not_an_error(db):
    account = _account(db, "unfollow-none@example.com")
    assert notify.unfollow_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-x") is None


def test_followers_of_finds_the_audience_and_skips_anyone_who_left(db):
    stayed = _account(db, "stayed@example.com")
    left = _account(db, "left@example.com")
    other = _account(db, "other-vendor@example.com")
    for account in (stayed, left):
        notify.follow_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-4")
    notify.follow_subject(db, other.id, notify.VENDOR_ALERT_CLASS, "vendor-5")
    # left the class entirely without unfollowing — the follow list still names them
    notify.set_class_opt_in(db, left.id, notify.VENDOR_ALERT_CLASS, False)

    audience = notify.followers_of(db, notify.VENDOR_ALERT_CLASS, "vendor-4")

    assert stayed.id in audience
    assert left.id not in audience  # opting out of the class outranks a stale follow
    assert other.id not in audience


def test_a_follow_does_not_bypass_a_single_cap(db):
    """Following is consent to be told, never permission to be told twice. Every law
    the class declares still applies to a follower."""
    account = _account(db, "follow-caps@example.com")
    notify.follow_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-6")
    gateway = _gateway()

    first = _send(db, account, gateway, subject_ref="vendor-6")
    second = _send(db, account, gateway, subject_ref="vendor-6")
    assert first.status == notify.NotificationStatus.queued
    assert second.status == notify.NotificationStatus.suppressed
    assert second.suppress_reason == notify.SuppressReason.budget

    # and quiet hours still bite a follower
    quiet = _send(db, _account(db, "follow-quiet@example.com"), gateway, now=T0.replace(hour=23))
    assert quiet.status == notify.NotificationStatus.suppressed


# --- unmuting, the half `mute_subject` shipped without (§23 entry 114) ---


def test_unmuting_lets_the_subject_through_again(db):
    account = _account(db, "unmute@example.com")
    notify.set_class_opt_in(db, account.id, notify.VENDOR_ALERT_CLASS, True)
    notify.mute_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-7")
    gateway = _gateway()
    assert _send(db, account, gateway, subject_ref="vendor-7").suppress_reason == (
        notify.SuppressReason.muted
    )

    notify.unmute_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-7")

    assert _send(db, account, gateway, subject_ref="vendor-7").status == (
        notify.NotificationStatus.queued
    )


def test_unmuting_leaves_the_class_switch_alone(db):
    """The trap `follow_subject` sets and this must not: it clears a mute AND opts the
    class in. Un-silencing one subject is not consent to the whole class, which is
    `unfollow_subject`'s rule pointing the other way.

    ASSERTED IN BOTH DIRECTIONS since §23 entry 231. This test used to check only that
    the switch read False afterwards, which passed for the wrong reason: `mute_subject`
    was writing an opt-OUT as a side effect of creating the row, so the "unchanged" it
    was proving was really "off, because muting turned it off". The invariant is that
    neither mute nor unmute MOVES the switch — whichever way it was pointing.
    """
    left_on = _account(db, "unmute-default@example.com")
    notify.mute_subject(db, left_on.id, notify.VENDOR_ALERT_CLASS, "vendor-8")
    assert notify.is_opted_in(db, left_on.id, notify.VENDOR_ALERT_CLASS) is True
    notify.unmute_subject(db, left_on.id, notify.VENDOR_ALERT_CLASS, "vendor-8")
    assert notify.is_opted_in(db, left_on.id, notify.VENDOR_ALERT_CLASS) is True

    left_off = _account(db, "unmute-optout@example.com")
    notify.set_class_opt_in(db, left_off.id, notify.VENDOR_ALERT_CLASS, False)
    notify.mute_subject(db, left_off.id, notify.VENDOR_ALERT_CLASS, "vendor-8")
    notify.unmute_subject(db, left_off.id, notify.VENDOR_ALERT_CLASS, "vendor-8")
    assert notify.is_opted_in(db, left_off.id, notify.VENDOR_ALERT_CLASS) is False


def test_unmuting_leaves_the_other_mutes_in_place(db):
    account = _account(db, "unmute-one@example.com")
    notify.mute_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-9")
    notify.mute_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-10")

    notify.unmute_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-9")

    assert notify.is_subject_muted(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-9") is False
    assert notify.is_subject_muted(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-10") is True


def test_unmuting_with_no_preference_row_is_not_an_error(db):
    """A driver asking for a state they are already in has succeeded. Returning None
    rather than creating an empty row keeps `is_opted_in` reading the DEFAULT, which is
    the difference between "never asked" and "answered no"."""
    account = _account(db, "unmute-nothing@example.com")

    assert notify.unmute_subject(db, account.id, notify.VENDOR_ALERT_CLASS, "vendor-11") is None
    assert notify.get_class_pref(db, account.id, notify.VENDOR_ALERT_CLASS) is None
