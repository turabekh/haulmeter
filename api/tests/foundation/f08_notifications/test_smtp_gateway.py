"""AI-CONTEXT: the counterparty transport that did not exist until 2026-08-02.

F8 modelled outbound counterparty mail correctly from the start — threads, messages,
provider refs, per-thread tracking — and every one of the seven send sites passed
`RecordingNotificationGateway`, whose `send_email` appends to a list. So the database
recorded that a notice was sent and nothing left the box: no Stop Packet reached a
dispatcher, no detention notice reached a broker, and Mailpit (in compose since session
0) had received zero messages in the life of the project.

These assert the two halves that make the difference honest: it actually speaks SMTP,
and it never makes the caller fail when the server is unreachable.
"""

import smtplib
from dataclasses import dataclass

from app.foundation.f08_notifications import public as notify


@dataclass
class FakeSettings:
    smtp_host: str = "mailpit"
    smtp_port: int = 1038
    smtp_from: str = "paperwork@haulmeter.online"
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False


class _CapturingSMTP:
    """Stands in for smtplib.SMTP: records the message instead of opening a socket."""

    sent: list = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        _CapturingSMTP.sent.append(("starttls", None))

    def login(self, user, pw):
        _CapturingSMTP.sent.append(("login", user))

    def send_message(self, msg):
        _CapturingSMTP.sent.append(("message", msg))


def test_it_actually_speaks_smtp(monkeypatch):
    _CapturingSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", _CapturingSMTP)
    gw = notify.SmtpNotificationGateway(FakeSettings())

    ref = gw.send_email("ap@bolt.example", "Stop paperwork · BL-77", "The paperwork is here: …")

    msgs = [m for kind, m in _CapturingSMTP.sent if kind == "message"]
    assert msgs, "nothing was handed to SMTP — this is the defect the class exists to fix"
    msg = msgs[0]
    assert msg["To"] == "ap@bolt.example"
    assert msg["Subject"] == "Stop paperwork · BL-77"
    assert msg["From"] == "paperwork@haulmeter.online"
    assert "paperwork is here" in msg.get_content()
    assert ref.startswith("smtp-"), "the provider ref must record that it went out"


def test_a_dead_server_never_fails_the_caller(monkeypatch):
    """The rule inherited from WebPushNotificationGateway: a gateway may never make the
    caller fail. The F8 row is the record that we decided to send; an SMTP server having
    a bad minute is a transport fact, not a reason to 500 a driver who just tapped Send.
    The ref says which happened, because a row claiming delivery it did not get is the
    exact lie this class was written to end."""

    def explode(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(smtplib, "SMTP", explode)
    gw = notify.SmtpNotificationGateway(FakeSettings())

    ref = gw.send_email("ap@bolt.example", "subject", "body")

    assert ref.startswith("smtp-failed-"), "a failure must be visible in the provider ref"
    assert gw.failed == 1


def test_starttls_and_credentials_are_used_when_configured(monkeypatch):
    _CapturingSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", _CapturingSMTP)
    gw = notify.SmtpNotificationGateway(
        FakeSettings(smtp_starttls=True, smtp_username="apikey", smtp_password="s3cret")
    )

    gw.send_email("ap@bolt.example", "s", "b")

    kinds = [k for k, _ in _CapturingSMTP.sent]
    assert kinds == ["starttls", "login", "message"], f"wrong order or missing step: {kinds}"


def test_no_host_means_no_smtp_and_no_pretending(monkeypatch):
    """Mailpit needs no credentials, so the switch is the HOST rather than a key. Blank it
    and the resolver falls back to recording — which is what the suite runs on."""
    gw = notify.SmtpNotificationGateway(FakeSettings(smtp_host=""))
    assert gw.configured is False
    assert gw.send_email("a@b.example", "s", "b") == "email-unconfigured"


def test_the_resolver_picks_smtp_when_configured_and_recording_when_not(monkeypatch):
    _CapturingSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", _CapturingSMTP)

    live = notify.counterparty_gateway(FakeSettings())
    dark = notify.counterparty_gateway(FakeSettings(smtp_host=""))

    assert live.send_email("a@b.example", "s", "b").startswith("smtp-")
    # unconfigured falls back to RECORDING, which answers "email-<n>" — the message is
    # captured in memory and nothing is transmitted. That is the suite's mode.
    assert dark.send_email("a@b.example", "s", "b").startswith("email-")
    assert len([k for k, _ in _CapturingSMTP.sent if k == "message"]) == 1, (
        "the unconfigured gateway reached an SMTP server"
    )


def test_the_choice_is_made_at_SEND_time_not_at_import(monkeypatch):
    """The API modules build one of these at module scope. Deciding at import would bake
    in whatever configuration the process started with — and the suite deliberately runs
    with SMTP off while the app runs with it on. One frozen choice cannot serve both."""
    _CapturingSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", _CapturingSMTP)
    settings = FakeSettings(smtp_host="")
    gw = notify.counterparty_gateway(settings)

    # unconfigured -> recording ("email-<n>"), nothing transmitted
    assert gw.send_email("a@b.example", "s", "b").startswith("email-")
    assert not [k for k, _ in _CapturingSMTP.sent if k == "message"]

    settings.smtp_host = "mailpit"  # configuration changes under a gateway already built
    assert gw.send_email("a@b.example", "s", "b").startswith("smtp-")
    assert [k for k, _ in _CapturingSMTP.sent if k == "message"], "the choice was frozen"
