"""AI-CONTEXT: driver push left the request thread, and these are the tests that can tell.

`dispatch` called `send_push` inline — a POST per subscription with a ten-second timeout,
once per browser a driver has, inside the request handler and holding a pooled database
connection on a third party. §23 records that failure mode as an outage: "QueuePool limit
of size 5 overflow 10 reached", the API out of connections and answering nothing.

THE SPLIT THESE TESTS DEFEND. Everything that DECIDES stays in `dispatch` — quiet hours,
the interruption budget, opt-in, mute, and the DRIVING/RESTING channel — because each is a
fact about the instant a driver would be interrupted and none survives being re-asked a
minute later. Only the transport moved.

Thirty-two tests elsewhere assert that decision by asserting `queued`. None of them would
notice if `deliver_queued_notifications` never ran, which is why this file exists and why
each behaviour here is proved by breaking it.
"""

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify


class Recorder:
    """The push half of the gateway contract: never raises, records what it was given."""

    def __init__(self):
        self.pushed = []

    def send_push(self, to_ref, title, body, deep_link=None, actions=None):
        self.pushed.append(
            {"to": to_ref, "title": title, "body": body, "link": deep_link, "actions": actions}
        )
        return "push-ok"


class Broken:
    def send_push(self, *_a, **_k):
        raise RuntimeError("push service unreachable")


@pytest.fixture
def driver(db):
    return identity.register_account(db, "push@example.com", "pw-123456")


def _p0(db, driver, title="Detention started"):
    return notify.dispatch(
        db,
        driver.id,
        notify.NotificationTier.P0,
        "detention_started",
        title,
        "Free time expired at Harvest Foods DC.",
        "/load/l-1/claim",
        Recorder(),  # ignored: dispatch no longer sends
    )


class TestTheRequestDecidesAndDoesNotSend:
    def test_a_dispatch_opens_no_connection(self, db, driver):
        gateway = Recorder()

        notification = notify.dispatch(
            db,
            driver.id,
            notify.NotificationTier.P0,
            "detention_started",
            "t",
            "b",
            "/load/l-1/claim",
            gateway,
        )

        assert gateway.pushed == [], "the request path must not talk to a push service"
        assert notification.status == notify.NotificationStatus.queued
        assert notification.dispatched_at is None, "nothing has been handed over yet"
        assert notification.decided_at is not None, "but the interruption is already spent"

    def test_the_sweep_hands_it_over_and_records_when(self, db, driver):
        notification = _p0(db, driver)
        gateway = Recorder()

        summary = notify.deliver_queued_notifications(db, lambda _a: gateway)

        assert summary == {"delivered": 1, "failed": 0}
        assert notification.status == notify.NotificationStatus.sent
        assert notification.dispatched_at is not None
        assert gateway.pushed[0]["title"] == "Detention started"
        assert gateway.pushed[0]["link"] == "/load/l-1/claim", "§13.5 travels with the push"

    def test_a_delivered_notification_is_never_swept_again(self, db, driver):
        _p0(db, driver)
        gateway = Recorder()

        notify.deliver_queued_notifications(db, lambda _a: gateway)
        again = notify.deliver_queued_notifications(db, lambda _a: gateway)

        assert again["delivered"] == 0
        assert len(gateway.pushed) == 1, "a driver must not be pushed the same thing twice"

    def test_a_push_service_having_a_bad_minute_keeps_the_row(self, db, driver):
        notification = _p0(db, driver)

        summary = notify.deliver_queued_notifications(db, lambda _a: Broken())

        assert summary == {"delivered": 0, "failed": 1}
        assert notification.status == notify.NotificationStatus.queued, "still owed"
        # and the next sweep delivers it — a P0 is not lost to a transient outage
        gateway = Recorder()
        notify.deliver_queued_notifications(db, lambda _a: gateway)
        assert len(gateway.pushed) == 1


class TestTheTrayButtonsSurviveTheWait:
    def test_actions_are_persisted_and_handed_over(self, db, driver):
        # AI-CONTEXT: `actions` used to go straight from the parameter to the gateway and
        # was stored nowhere, so deferring the send would have dropped it silently. The
        # one notification that uses them is the lot-status prompt, whose own comment says
        # "the answer must be one tap from a LOCKED phone or it is a task, not a
        # confirmation". Losing them fails nothing and breaks exactly that.
        buttons = [
            {"action": "lot:empty", "title": "Empty"},
            {"action": "lot:some", "title": "Some"},
        ]
        notification = notify.dispatch(
            db,
            driver.id,
            notify.NotificationTier.P0,
            "lot_status",
            "How full is this lot?",
            "b",
            "/facility/f-1",
            Recorder(),
            actions=buttons,
        )
        assert notification.actions == buttons, "persisted, not just passed through"

        gateway = Recorder()
        notify.deliver_queued_notifications(db, lambda _a: gateway)

        assert gateway.pushed[0]["actions"] == buttons


class TestTheBudgetCountsTheDecision:
    """AI-CONTEXT: the law that deferring delivery would have silently switched off.

    §13.1's budget counted `status = sent AND dispatched_at >= now - 24h`. A queued
    notification satisfies neither, so a burst inside one sweep window would every one of
    them have read zero used — the two-a-day cap, and every per-class daily cap, gone.
    """

    def test_a_queued_p1_spends_the_budget_before_it_is_delivered(self, db, driver):
        from datetime import UTC, datetime

        now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)

        def p1(title):
            return notify.dispatch(
                db,
                driver.id,
                notify.NotificationTier.P1,
                "generic",
                title,
                "b",
                "/load/l-1",
                Recorder(),
                now=now,
            )

        first, second = p1("one"), p1("two")
        third = p1("three")

        assert first.status == notify.NotificationStatus.queued
        assert second.status == notify.NotificationStatus.queued
        # nothing has been DELIVERED yet, and the cap must still bite
        assert third.status == notify.NotificationStatus.suppressed
        assert third.suppress_reason == notify.SuppressReason.budget

    def test_the_window_follows_the_caller_s_clock(self, db, driver):
        # AI-CONTEXT: `decided_at` rather than `created_at`, because `created_at` is a
        # server default and ignores the `now` a caller passes — which would make the
        # budget wrong for any job replaying on a historical clock, and untestable here.
        from datetime import UTC, datetime, timedelta

        long_ago = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
        now = long_ago + timedelta(days=2)

        for title in ("one", "two"):
            notify.dispatch(
                db, driver.id, notify.NotificationTier.P1, "generic", title, "b",
                "/load/l-1", Recorder(), now=long_ago,
            )
        later = notify.dispatch(
            db, driver.id, notify.NotificationTier.P1, "generic", "three", "b",
            "/load/l-1", Recorder(), now=now,
        )

        assert later.status == notify.NotificationStatus.queued, (
            "two days on, the window has moved and the cap has reopened"
        )


class TestTheDriverCanSeeItBeforeItIsDelivered:
    def test_a_queued_notification_is_in_the_inbox(self, db, driver):
        # hiding it until the sweep runs would mean a driver who opens the app in the
        # minute after their detention clock expired sees an empty inbox and concludes
        # nothing happened — the one reading §13.2's P0 exists to prevent
        _p0(db, driver, title="Detention started")

        inbox = notify.inbox(db, driver.id)

        assert [n.title for n in inbox] == ["Detention started"]


class TestItIsWiredToTheWorker:
    def test_the_sweep_runs_on_the_worker(self):
        from app.worker import _jobs

        job = next(j for j in _jobs() if j.name == "push_delivery")
        assert job.flag_key is None, "a flag nobody registered would mean no push ever goes"
        assert job.interval_seconds == 60
