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
    actions: list[dict] | None = None


class NotificationGateway(Protocol):
    # AI-CONTEXT: `deep_link` is optional in the SIGNATURE and mandatory in spirit
    # (§13.5). It is optional so the older adapters and every test double keep working;
    # `dispatch` always passes it, having already refused to create a notification
    # without one. A push that could not say where it was about would land the driver
    # on a tab root, which is the one thing §13.5 names outright.
    # AI-CONTEXT: `actions` are the tray buttons that make an answer one tap from a
    # LOCKED phone rather than a task (§23 entry 112). Server-driven rather than
    # inferred in the service worker, because sw.js is cached on the browser's own
    # schedule — a vocabulary hardcoded there can be stale on a driver's phone for days.
    def send_push(
        self,
        to_ref: str,
        title: str,
        body: str,
        deep_link: str | None = None,
        actions: list[dict] | None = None,
    ) -> str: ...

    def send_sms(self, to_ref: str, body: str) -> str: ...

    def send_email(
        self, to_ref: str, subject: str, body: str, attachments: list | None = None
    ) -> str: ...


class RecordingNotificationGateway:
    def __init__(self) -> None:
        self.sent: list[SentMessage] = []
        # one entry per email, so `attachments[i]` belongs to the i-th email sent
        self.attachments: list[list] = []

    def send_push(
        self,
        to_ref: str,
        title: str,
        body: str,
        deep_link: str | None = None,
        actions: list[dict] | None = None,
    ) -> str:
        self.sent.append(SentMessage("push", to_ref, title, body, deep_link, actions))
        return f"push-{len(self.sent)}"

    def send_sms(self, to_ref: str, body: str) -> str:
        self.sent.append(SentMessage("sms", to_ref, None, body))
        return f"sms-{len(self.sent)}"

    def send_email(
        self, to_ref: str, subject: str, body: str, attachments: list | None = None
    ) -> str:
        self.sent.append(SentMessage("email", to_ref, subject, body))
        # AI-CONTEXT: recorded, so a test can assert the PDF really rode along. A recording
        # gateway that silently dropped attachments would let "we attach the pack" pass
        # everywhere while nothing was ever attached.
        self.attachments.append(list(attachments or []))
        return f"email-{len(self.sent)}"


class StubNotificationGateway:
    def send_push(
        self,
        to_ref: str,
        title: str,
        body: str,
        deep_link: str | None = None,
        actions: list[dict] | None = None,
    ) -> str:
        raise NotImplementedError("FCM/APNs adapter is a seam; wired at activation")

    def send_sms(self, to_ref: str, body: str) -> str:
        raise NotImplementedError("Twilio adapter is a seam; wired at activation")

    def send_email(
        self, to_ref: str, subject: str, body: str, attachments: list | None = None
    ) -> str:
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
        self,
        to_ref: str,
        title: str,
        body: str,
        deep_link: str | None = None,
        actions: list[dict] | None = None,
    ) -> str:
        from app.foundation.f08_notifications.domain import service as f08

        if not self.configured:
            return "push-unconfigured"
        subs = f08.subscriptions_for(self._db, self._account_id)
        for sub in list(subs):
            self._send_one(sub, title, body, deep_link, actions)
        return f"push-{self.delivered}"

    def _send_one(
        self, sub, title: str, body: str, deep_link: str | None, actions: list[dict] | None = None
    ) -> None:
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
                data=json.dumps(
                    {
                        "title": title,
                        "body": body,
                        "deep_link": deep_link,
                        "actions": actions or [],
                    }
                ),
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

    def send_email(
        self, to_ref: str, subject: str, body: str, attachments: list | None = None
    ) -> str:
        raise NotImplementedError("transactional email adapter is a seam; wired at activation")


# AI-CONTEXT: what a provider ref MEANS, in one place (audit F-06).
#
# A gateway may never fail its caller — the F8 row is the record that we decided to send,
# and an SMTP server having a bad minute is a transport fact, not a reason to 500 a driver
# who just tapped Send. So the outcome travels back as the ref string, and until now every
# caller that wanted to know had to match on it by hand. Nobody did, which is why a
# `smtp-failed-…` row still recorded `sent_at` and claimed delivery it never got.
FAILED_PREFIX = "smtp-failed-"

# Retrying these is pointless and, for an auth error against Gmail, actively harmful:
# repeated bad logins are how an account gets locked. Everything else — a dropped
# connection, a timeout, a 4xx greylist, a rate limit — is a bad minute and worth another
# attempt. The default is RETRY, because the cost of retrying a permanent failure a few
# bounded times is noise and the cost of dropping a detention notice is a driver's money.
PERMANENT_FAILURES = frozenset(
    {
        "SMTPAuthenticationError",
        "SMTPRecipientsRefused",
        "SMTPNotSupportedError",
        "SMTPSenderRefused",
    }
)


def is_failure(provider_ref: str | None) -> bool:
    return bool(provider_ref) and provider_ref.startswith(FAILED_PREFIX)


def is_retryable(provider_ref: str | None) -> bool:
    if not is_failure(provider_ref):
        return False
    return provider_ref[len(FAILED_PREFIX) :] not in PERMANENT_FAILURES


class SmtpNotificationGateway:
    """The counterparty transport, and until 2026-08-02 it did not exist.

    AI-CONTEXT: F8 has always MODELLED outbound counterparty mail correctly — threads,
    messages, provider refs, per-thread tracking — and every caller passed
    `RecordingNotificationGateway`, whose `send_email` appends to a list. So the database
    said the notice was sent and nothing left the box: no Stop Packet reached a
    dispatcher, no detention notice reached a broker, and Mailpit (wired into compose
    since session 0) had received zero messages in the life of the project. That is why
    v2.0 Phase DoD item 1 was unreachable — the document was right and could not arrive.

    Shaped like every other provider seam here: configuration present activates real
    delivery, absent falls back to recording. Unlike VAPID or the AI gateway the switch
    is the HOST rather than a key, because the dev provider (Mailpit) needs no
    credentials — and a dev box that silently stopped sending would put us straight back
    where this started.

    THE RULE IT INHERITS FROM WebPushNotificationGateway: a gateway may never make the
    caller fail. The F8 message row is the record that we decided to send; an SMTP server
    having a bad minute is a transport fact, not a reason to lose the row or to 500 a
    driver who just tapped Send. Failures are counted and swallowed, and the returned
    provider ref SAYS which happened — `smtp-failed-…` is greppable, and a row claiming
    delivery it did not get is the lie this whole class exists to end.

    Plain text, deliberately. §17 and §12.1: the artifact is the PDF behind the link, the
    email is a covering note, and an AP clerk's filter is kinder to text than to HTML.
    """

    def __init__(self, settings=None):
        # AI-CONTEXT: settings are resolved LAZILY, at send time. The API modules build
        # this once at import, and reading configuration then would freeze whatever the
        # process happened to start with — which is exactly how a test that clears the
        # settings cache ends up asserting against a gateway that cannot see it.
        self._explicit = settings
        self.delivered = 0
        self.failed = 0

    @property
    def _s(self):
        if self._explicit is not None:
            return self._explicit
        from app.core.config import get_settings

        return get_settings()

    @property
    def configured(self) -> bool:
        return bool(self._s.smtp_host and self._s.smtp_port)

    def send_push(
        self,
        to_ref: str,
        title: str,
        body: str,
        deep_link: str | None = None,
        actions: list[dict] | None = None,
    ) -> str:
        raise NotImplementedError("SMTP is the counterparty seam; driver push is WebPush")

    def send_sms(self, to_ref: str, body: str) -> str:
        raise NotImplementedError("Twilio adapter is a seam; wired at activation")

    def send_email(
        self, to_ref: str, subject: str, body: str, attachments: list | None = None
    ) -> str:
        import smtplib
        from email.message import EmailMessage
        from email.utils import make_msgid

        if not self.configured:
            return "email-unconfigured"
        # AI-CONTEXT: the ref is the message's real RFC 5322 Message-ID (audit F-03).
        #
        # It used to be f"smtp-{self.delivered}", an instance counter — and
        # `_LazyCounterpartyGateway._pick()` builds a fresh instance per send, so the
        # counter never got past one and EVERY successful send in the product's life
        # returned `smtp-1`. A1 requirement 4 depends on F8 per-thread tracking, and a
        # constant cannot distinguish two sends.
        #
        # A Message-ID is the right answer rather than merely a unique one: it is what
        # the receiving server logs, so a ref in our database can be searched for in a
        # mail provider's trace when a broker says they never got it. The `smtp-` prefix
        # stays because it names the transport and callers already grep for it.
        message_id = make_msgid(domain=(self._s.smtp_from.split("@")[-1] or None))
        msg = EmailMessage()
        msg["From"] = self._s.smtp_from
        msg["To"] = to_ref
        msg["Subject"] = subject
        msg["Message-ID"] = message_id
        msg.set_content(body)
        # AI-CONTEXT: the pack itself, beside the link rather than instead of it (§23).
        # A clerk who can open the document from their inbox does not have to click
        # anything; the link survives because it is the half that records that they DID —
        # "they opened it on the 12th" is evidence, and an attachment produces none.
        #
        # `application/pdf` explicitly: a filename is a hint and some gateways will guess
        # `application/octet-stream`, which more filters quarantine than pass.
        for name, data in attachments or []:
            msg.add_attachment(
                data, maintype="application", subtype="pdf", filename=name
            )
        try:
            with smtplib.SMTP(
                self._s.smtp_host, self._s.smtp_port, timeout=10
            ) as smtp:
                if self._s.smtp_starttls:
                    smtp.starttls()
                if self._s.smtp_username:
                    smtp.login(self._s.smtp_username, self._s.smtp_password)
                smtp.send_message(msg)
            self.delivered += 1
            return f"smtp-{message_id}"
        except Exception as exc:
            # never fail the caller: the F8 row and the driver's confirmation both stand,
            # and the ref records that this one did not go out.
            self.failed += 1
            return f"{FAILED_PREFIX}{type(exc).__name__}"


class _LazyCounterpartyGateway:
    """Chooses SMTP-or-recording at SEND time, not at import.

    The API modules hold one of these at module scope. Deciding at import would bake in
    whatever configuration the process started with, and the suite deliberately runs with
    SMTP off (conftest) while the app runs with it on — one frozen choice cannot serve
    both, and freezing the wrong one is silent."""

    def __init__(self, settings=None):
        self._explicit = settings

    def _pick(self):
        smtp = SmtpNotificationGateway(self._explicit)
        return smtp if smtp.configured else RecordingNotificationGateway()

    def send_push(self, *a, **k):
        return self._pick().send_push(*a, **k)

    def send_sms(self, *a, **k):
        return self._pick().send_sms(*a, **k)

    def send_email(self, *a, **k):
        return self._pick().send_email(*a, **k)


def counterparty_gateway(settings=None):
    """The gateway a COUNTERPARTY-facing send should use.

    Separate from `gateway_for` because the two answer different questions: that one
    picks a channel to reach the DRIVER's own browsers, this one reaches a broker's
    inbox. Sharing a resolver would have to guess which, and the callers already know.
    """
    return _LazyCounterpartyGateway(settings)


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

