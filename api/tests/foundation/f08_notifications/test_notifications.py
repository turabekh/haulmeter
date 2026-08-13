from datetime import UTC, datetime

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify

NOON = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
NIGHT = datetime(2026, 7, 20, 23, 30, tzinfo=UTC)


def _account(db, email="driver@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _dispatch(db, account, gateway, tier, **kw):
    return notify.dispatch(
        db,
        account.id,
        tier,
        kw.pop("category", "detention"),
        kw.pop("title", "Detention started"),
        kw.pop("body", "$75/h accruing"),
        kw.pop("deep_link", "longhaul://load/stop/1"),
        gateway,
        **kw,
    )


def test_p2_is_digest_only_never_pushed(db):
    account = _account(db)
    gw = notify.RecordingNotificationGateway()
    n = _dispatch(db, account, gw, notify.NotificationTier.P2, now=NOON)
    assert n.status == notify.NotificationStatus.digested
    assert n.channel == notify.NotificationChannel.in_app
    assert gw.sent == []
    assert len(notify.digest(db, account.id)) == 1


def test_p0_always_sends_even_at_night(db):
    account = _account(db)
    gw = notify.RecordingNotificationGateway()
    n = _dispatch(db, account, gw, notify.NotificationTier.P0, now=NIGHT)
    assert n.status == notify.NotificationStatus.sent
    assert len(gw.sent) == 1


def test_p1_sends_when_clear(db):
    account = _account(db)
    gw = notify.RecordingNotificationGateway()
    n = _dispatch(db, account, gw, notify.NotificationTier.P1, now=NOON)
    assert n.status == notify.NotificationStatus.sent
    assert n.channel == notify.NotificationChannel.push


def test_p1_suppressed_by_quiet_hours(db):
    account = _account(db)
    gw = notify.RecordingNotificationGateway()
    n = _dispatch(db, account, gw, notify.NotificationTier.P1, now=NIGHT)
    assert n.status == notify.NotificationStatus.suppressed
    assert n.suppress_reason == notify.SuppressReason.quiet_hours
    assert gw.sent == []


def test_p1_suppressed_by_budget(db):
    account = _account(db)
    gw = notify.RecordingNotificationGateway()
    _dispatch(db, account, gw, notify.NotificationTier.P1, now=NOON)
    _dispatch(db, account, gw, notify.NotificationTier.P1, now=NOON)
    third = _dispatch(db, account, gw, notify.NotificationTier.P1, now=NOON)
    assert third.status == notify.NotificationStatus.suppressed
    assert third.suppress_reason == notify.SuppressReason.budget
    assert len(gw.sent) == 2
    assert notify.p1_budget_used(db, account.id, NOON) == 2


def test_p1_suppressed_while_resting(db):
    account = _account(db)
    gw = notify.RecordingNotificationGateway()
    n = _dispatch(
        db,
        account,
        gw,
        notify.NotificationTier.P1,
        now=NOON,
        driver_state=notify.DriverState.resting,
    )
    assert n.suppress_reason == notify.SuppressReason.resting


def test_driving_delivers_audio_not_interactive(db):
    account = _account(db)
    gw = notify.RecordingNotificationGateway()
    n = _dispatch(
        db,
        account,
        gw,
        notify.NotificationTier.P0,
        now=NOON,
        driver_state=notify.DriverState.driving,
    )
    assert n.status == notify.NotificationStatus.sent
    assert n.channel == notify.NotificationChannel.audio


def test_deep_link_required(db):
    account = _account(db)
    gw = notify.RecordingNotificationGateway()
    with pytest.raises(notify.MissingDeepLink):
        _dispatch(db, account, gw, notify.NotificationTier.P0, now=NOON, deep_link="")


def test_template_registry_returns_latest_active_version(db):
    notify.register_template(
        db,
        "detention_notice",
        "v1 body",
        notify.TemplateAudience.driver,
        notify.NotificationChannel.push,
        version=1,
    )
    notify.register_template(
        db,
        "detention_notice",
        "v2 body {rate}",
        notify.TemplateAudience.driver,
        notify.NotificationChannel.push,
        version=2,
    )
    active = notify.get_active_template(db, "detention_notice")
    assert active.version == 2
    subject, body = notify.render_template(active, {"rate": "$75/h"})
    assert body == "v2 body $75/h"


def test_counterparty_template_must_be_english(db):
    notify.register_template(
        db,
        "detention_invoice",
        "Detention owed: {amount}",
        notify.TemplateAudience.counterparty,
        notify.NotificationChannel.email,
        locale="en",
    )
    with pytest.raises(notify.CounterpartyMustBeEnglish):
        notify.register_template(
            db,
            "detention_invoice",
            "Detención: {amount}",
            notify.TemplateAudience.counterparty,
            notify.NotificationChannel.email,
            locale="es",
        )


def test_outbound_thread_tracking_and_reply(db):
    account = _account(db)
    gw = notify.RecordingNotificationGateway()
    thread = notify.create_thread(
        db, account.id, subject="Detention notice — load L-1001", reply_to="claims@longhaul"
    )
    msg = notify.send_counterparty_message(
        db, thread, "Please remit detention per rate con.", gw, "broker@acme.com", now=NOON
    )
    # AI-CONTEXT: recording the message no longer sends it — the `outbound_mail` sweep
    # does, off the request thread. The row is the promise; delivery is a separate fact,
    # which is exactly the distinction `sent_at` has always carried (audit F-06).
    assert msg.sent_at is None, "nothing has gone out yet"
    notify.retry_unsent_messages(db, gw, now=NOON)
    assert msg.sent_at == NOON
    assert msg.provider_ref is not None
    assert gw.sent[0].channel == "email"

    notify.mark_opened(db, msg, now=NIGHT)
    assert msg.opened_at == NIGHT

    reply = notify.record_inbound_reply(db, thread, "We will process this week.")
    assert reply.direction == notify.MessageDirection.inbound
    assert len(thread.messages) == 2
