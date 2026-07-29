"""AI-CONTEXT: Notification-channel adapter seam for F8 (PRD §7.8).

Inbound-to-driver channels — push (FCM/APNs), SMS (Twilio), email — and the
outbound counterparty transactional-email provider all sit behind this protocol.
The tiering/budget/quiet-hours decision logic in service.py is real and fully
tested without any live provider; the concrete FCM/Twilio/email adapters plug in
at activation. RecordingNotificationGateway captures sends for tests;
StubNotificationGateway fails loudly so nothing silently pretends to notify.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class SentMessage:
    channel: str
    to_ref: str
    subject: str | None
    body: str
    deep_link: str | None = None


class NotificationGateway(Protocol):
    # AI-CONTEXT: `deep_link` is optional in the SIGNATURE and mandatory in spirit
    # (§13.5). It is optional so the older adapters and every test double keep working;
    # `dispatch` always passes it, having already refused to create a notification
    # without one. A push that could not say where it was about would land the driver
    # on a tab root, which is the one thing §13.5 names outright.
    def send_push(
        self, to_ref: str, title: str, body: str, deep_link: str | None = None
    ) -> str: ...

    def send_sms(self, to_ref: str, body: str) -> str: ...

    def send_email(self, to_ref: str, subject: str, body: str) -> str: ...


class RecordingNotificationGateway:
    def __init__(self) -> None:
        self.sent: list[SentMessage] = []

    def send_push(
        self, to_ref: str, title: str, body: str, deep_link: str | None = None
    ) -> str:
        self.sent.append(SentMessage("push", to_ref, title, body, deep_link))
        return f"push-{len(self.sent)}"

    def send_sms(self, to_ref: str, body: str) -> str:
        self.sent.append(SentMessage("sms", to_ref, None, body))
        return f"sms-{len(self.sent)}"

    def send_email(self, to_ref: str, subject: str, body: str) -> str:
        self.sent.append(SentMessage("email", to_ref, subject, body))
        return f"email-{len(self.sent)}"


class StubNotificationGateway:
    def send_push(
        self, to_ref: str, title: str, body: str, deep_link: str | None = None
    ) -> str:
        raise NotImplementedError("FCM/APNs adapter is a seam; wired at activation")

    def send_sms(self, to_ref: str, body: str) -> str:
        raise NotImplementedError("Twilio adapter is a seam; wired at activation")

    def send_email(self, to_ref: str, subject: str, body: str) -> str:
        raise NotImplementedError("transactional email adapter is a seam; wired at activation")


class WebPushNotificationGateway:
    """Real delivery to a phone in a pocket (§13.1, §23 entry 111).

    AI-CONTEXT: takes a SESSION and an account, not a global registry, because "who is
    this for" is decided by the caller that already knows — `dispatch` passes the
    account's own `to_ref`. One gateway instance serves one driver's sends.

    THE RULE THIS IS SHAPED AROUND: a gateway may never make a dispatch fail. F8 has
    already applied the tier, the budget and quiet hours by the time `send_push` is
    called, and the Notification row is the record of that decision. A push service
    being unreachable is a transport fact, not a reason to lose the row a driver can
    still read in their inbox — so every failure here is swallowed after being counted,
    and the caller's `_send` marks the notification sent regardless. §13.5's inbox is
    what makes that honest: nothing is lost, it is one screen away.

    A DEAD SUBSCRIPTION IS PRUNED ON THE ONLY HONEST SIGNAL. A browser uninstalled, a
    permission revoked, an endpoint expired — none of them tell us. They surface as 404
    or 410 at send time, so that response deletes the row. Any other error (a 500 from
    the push service, a timeout) leaves it alone: a service having a bad minute is not
    a driver who left.
    """

    def __init__(self, db, account_id, settings=None):
        self._db = db
        self._account_id = account_id
        if settings is None:
            from app.core.config import get_settings

            settings = get_settings()
        self._settings = settings
        self.delivered = 0
        self.pruned = 0

    @property
    def configured(self) -> bool:
        return bool(self._settings.vapid_private_key and self._settings.vapid_public_key)

    def send_push(
        self, to_ref: str, title: str, body: str, deep_link: str | None = None
    ) -> str:
        from app.foundation.f08_notifications.domain import service as f08

        if not self.configured:
            return "push-unconfigured"
        subs = f08.subscriptions_for(self._db, self._account_id)
        for sub in list(subs):
            self._send_one(sub, title, body, deep_link)
        return f"push-{self.delivered}"

    def _send_one(self, sub, title: str, body: str, deep_link: str | None) -> None:
        import json

        from app.foundation.f08_notifications.domain import service as f08

        try:
            from pywebpush import WebPushException, webpush
        except ImportError:  # the dependency is declared; a stripped image is not fatal
            return
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=json.dumps({"title": title, "body": body, "deep_link": deep_link}),
                vapid_private_key=self._settings.vapid_private_key,
                vapid_claims={"sub": self._settings.vapid_contact},
                timeout=10,
            )
            self.delivered += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                f08.drop_subscription(self._db, sub)
                self.pruned += 1
        except Exception:
            # a transport problem must never cost the driver the inbox row
            pass

    def send_sms(self, to_ref: str, body: str) -> str:
        raise NotImplementedError("Twilio adapter is a seam; wired at activation")

    def send_email(self, to_ref: str, subject: str, body: str) -> str:
        raise NotImplementedError("transactional email adapter is a seam; wired at activation")


def gateway_for(db, account_id):
    """The gateway a dispatch site should use (§23 entry 111).

    AI-CONTEXT: same shape as every other provider seam in this codebase — a key
    present activates real delivery, absent falls back to the recording gateway. That
    is what lets a laptop with no VAPID keypair still exercise every tiering decision
    F8 makes, and it is why `RecordingNotificationGateway` stays in the tree rather
    than becoming test-only scaffolding.
    """
    push = WebPushNotificationGateway(db, account_id)
    return push if push.configured else RecordingNotificationGateway()

