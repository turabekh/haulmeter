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


class NotificationGateway(Protocol):
    def send_push(self, to_ref: str, title: str, body: str) -> str: ...

    def send_sms(self, to_ref: str, body: str) -> str: ...

    def send_email(self, to_ref: str, subject: str, body: str) -> str: ...


class RecordingNotificationGateway:
    def __init__(self) -> None:
        self.sent: list[SentMessage] = []

    def send_push(self, to_ref: str, title: str, body: str) -> str:
        self.sent.append(SentMessage("push", to_ref, title, body))
        return f"push-{len(self.sent)}"

    def send_sms(self, to_ref: str, body: str) -> str:
        self.sent.append(SentMessage("sms", to_ref, None, body))
        return f"sms-{len(self.sent)}"

    def send_email(self, to_ref: str, subject: str, body: str) -> str:
        self.sent.append(SentMessage("email", to_ref, subject, body))
        return f"email-{len(self.sent)}"


class StubNotificationGateway:
    def send_push(self, to_ref: str, title: str, body: str) -> str:
        raise NotImplementedError("FCM/APNs adapter is a seam; wired at activation")

    def send_sms(self, to_ref: str, body: str) -> str:
        raise NotImplementedError("Twilio adapter is a seam; wired at activation")

    def send_email(self, to_ref: str, subject: str, body: str) -> str:
        raise NotImplementedError("transactional email adapter is a seam; wired at activation")
