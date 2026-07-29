"""AI-CONTEXT: where a push actually goes (§23 entry 111).

The subscription table is the half of §13 that reaches a driver who is NOT looking.
What is asserted here is mostly the KEYING — one row per browser, re-subscribe updates,
an endpoint that changes hands is reassigned — because every one of those, wrong, ends
as a driver hearing the same alert twice or hearing somebody else's money.
"""

from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify


def _account(db, email="drv@example.com"):
    return identity.register_account(db, email, "pw-123456")


def test_a_browser_is_registered_once(db):
    acct = _account(db)

    notify.save_subscription(db, acct.id, "https://push.example/a", "p", "a")

    assert len(notify.subscriptions_for(db, acct.id)) == 1


def test_re_subscribing_the_same_browser_updates_rather_than_accumulates(db):
    """A browser re-subscribes on its own schedule. Keyed on account instead of
    endpoint this would buzz the same phone twice, forever."""
    acct = _account(db)
    notify.save_subscription(db, acct.id, "https://push.example/a", "p1", "a1")

    notify.save_subscription(db, acct.id, "https://push.example/a", "p2", "a2")
    subs = notify.subscriptions_for(db, acct.id)

    assert len(subs) == 1
    assert subs[0].p256dh == "p2"


def test_a_driver_with_two_devices_gets_two_rows(db):
    """A phone and a cab tablet are two browsers and both should buzz."""
    acct = _account(db)

    notify.save_subscription(db, acct.id, "https://push.example/phone", "p", "a")
    notify.save_subscription(db, acct.id, "https://push.example/tablet", "p", "a")

    assert len(notify.subscriptions_for(db, acct.id)) == 2


def test_an_endpoint_that_changes_hands_is_reassigned_not_duplicated(db):
    """One browser has one owner: the last person to log in on it. Two accounts
    pushing to one device would send a driver someone else's money alerts."""
    first = _account(db, "first@example.com")
    second = _account(db, "second@example.com")
    notify.save_subscription(db, first.id, "https://push.example/shared", "p", "a")

    notify.save_subscription(db, second.id, "https://push.example/shared", "p", "a")

    assert notify.subscriptions_for(db, first.id) == []
    assert len(notify.subscriptions_for(db, second.id)) == 1


def test_unsubscribing_is_scoped_to_the_asking_account(db):
    """One driver must not be able to silence another."""
    mine = _account(db, "mine@example.com")
    theirs = _account(db, "theirs@example.com")
    notify.save_subscription(db, theirs.id, "https://push.example/theirs", "p", "a")

    removed = notify.drop_subscription_by_endpoint(db, mine.id, "https://push.example/theirs")

    assert removed is False
    assert len(notify.subscriptions_for(db, theirs.id)) == 1


def test_unsubscribing_removes_my_own(db):
    acct = _account(db)
    notify.save_subscription(db, acct.id, "https://push.example/a", "p", "a")

    assert notify.drop_subscription_by_endpoint(db, acct.id, "https://push.example/a") is True
    assert notify.subscriptions_for(db, acct.id) == []


# --- the gateway, and the rule it is shaped around ---
def test_an_unconfigured_deployment_falls_back_to_recording(db):
    """Same shape as every other provider seam: no keypair -> the deterministic one, so
    a laptop still exercises every tiering decision F8 makes."""
    acct = _account(db)

    gw = notify.gateway_for(db, acct.id)

    assert isinstance(gw, notify.RecordingNotificationGateway)


def test_the_push_gateway_reports_itself_unconfigured_without_keys(db):
    acct = _account(db)

    gw = notify.WebPushNotificationGateway(db, acct.id)

    assert gw.configured is False
    # and it must not raise — a dispatch may never fail because of transport
    assert gw.send_push(str(acct.id), "t", "b", "/claim/x") == "push-unconfigured"


def test_the_deep_link_travels_with_the_push(db):
    """§13.5: one definition of "where this is about" serves the tray and the inbox."""
    acct = _account(db)
    gw = notify.RecordingNotificationGateway()

    notify.dispatch(
        db, acct.id, notify.NotificationTier.P0, "detention_start",
        "Detention started · $75/h", "b", "/claim/abc", gw,
    )

    assert gw.sent[0].deep_link == "/claim/abc"
