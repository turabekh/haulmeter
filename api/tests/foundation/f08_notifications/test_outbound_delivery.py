"""F-03, F-04 and F-06 — one send path, three ways it was not telling the truth.

F-03: the provider ref was an instance counter, and `_LazyCounterpartyGateway._pick()`
builds a fresh instance per send — so every successful send in the product's life
returned `smtp-1`. A1 requirement 4 depends on per-thread tracking and a constant cannot
distinguish two sends.

F-04: `_LazyCounterpartyGateway` appeared NOWHERE in the tests. It is the object every
real send goes through; the suite exercised `SmtpNotificationGateway` directly, where the
counter increments correctly and F-03 is invisible. §23 entry 113's shape again — two
constructors for one behaviour, tests on the one production does not use.

F-06: one attempt, ten-second timeout, exception swallowed into a string nobody read,
and `sent_at` written anyway. A transient blip permanently lost a detention notice and
the row said it had been sent.
"""


import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify
from app.foundation.f08_notifications.domain import gateway as gw


class _Settings:
    """Enough of Settings for the gateway. Configured means host AND port."""

    def __init__(self, host="smtp.example", port=1025):
        self.smtp_host = host
        self.smtp_port = port
        self.smtp_from = "paperwork@haulmeter.online"
        self.smtp_username = ""
        self.smtp_password = ""
        self.smtp_starttls = False


class _FakeSmtp:
    """Stands in for smtplib.SMTP. Records what was actually handed to it."""

    sent: list = []
    raises: Exception | None = None

    def __init__(self, *_a, **_k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def starttls(self):
        pass

    def login(self, *_a):
        pass

    def send_message(self, msg):
        if _FakeSmtp.raises is not None:
            raise _FakeSmtp.raises
        _FakeSmtp.sent.append(msg)


@pytest.fixture(autouse=True)
def _smtp(monkeypatch):
    import smtplib

    _FakeSmtp.sent = []
    _FakeSmtp.raises = None
    monkeypatch.setattr(smtplib, "SMTP", _FakeSmtp)
    return _FakeSmtp


def _thread(db, subject="Detention notice"):
    account = identity.register_account(db, "driver@example.com", "pw-123456")
    return notify.create_thread(db, account.id, subject=subject)


# --- F-03 ---
def test_two_sends_do_not_share_a_provider_ref(db):
    gateway = gw.SmtpNotificationGateway(_Settings())
    first = gateway.send_email("ap@broker.example", "s", "b")
    second = gateway.send_email("ap@broker.example", "s", "b")
    assert first != second, "a constant ref cannot distinguish two sends"


def test_the_ref_is_the_message_id_the_receiving_server_will_log(db):
    gateway = gw.SmtpNotificationGateway(_Settings())
    ref = gateway.send_email("ap@broker.example", "s", "b")
    assert ref.startswith("smtp-<") and ref.endswith(">")
    # the ref in our database must be findable in a mail provider's trace, which means
    # it has to be the header we actually sent
    assert _FakeSmtp.sent[-1]["Message-ID"] == ref[len("smtp-") :]


# --- F-04: the gateway PRODUCTION uses, which nothing tested ---
def test_the_lazy_gateway_is_what_production_holds_and_it_gives_unique_refs(db):
    # THE test the audit says did not exist. `_pick()` builds a new SmtpNotificationGateway
    # per call, so an instance counter resets every time — this is the shape that made
    # every send return "smtp-1" while the direct-construction tests passed.
    lazy = gw._LazyCounterpartyGateway(_Settings())
    refs = {lazy.send_email("ap@broker.example", "s", "b") for _ in range(3)}
    assert len(refs) == 3, "every send through the production object must be distinguishable"


def test_the_lazy_gateway_falls_back_to_recording_when_smtp_is_unconfigured(db):
    lazy = gw._LazyCounterpartyGateway(_Settings(host=""))
    ref = lazy.send_email("ap@broker.example", "s", "b")
    assert not ref.startswith("smtp-")
    assert _FakeSmtp.sent == [], "nothing may reach an SMTP server when unconfigured"


# --- F-06 ---
def test_a_failed_send_does_not_claim_it_was_sent(db):
    _FakeSmtp.raises = TimeoutError("connection timed out")
    thread = _thread(db)
    message = notify.send_counterparty_message(
        db, thread, "body", gw.SmtpNotificationGateway(_Settings()), "ap@broker.example"
    )
    assert notify.is_failure(message.provider_ref)
    assert message.sent_at is None, "sent_at means it went out"
    assert message.attempts == 1


def test_a_successful_send_records_when_and_to_whom(db):
    thread = _thread(db)
    message = notify.send_counterparty_message(
        db, thread, "body", gw.SmtpNotificationGateway(_Settings()), "ap@broker.example"
    )
    assert message.sent_at is not None
    assert message.to_ref == "ap@broker.example", "the database recorded no recipient at all"


def test_a_transient_failure_is_retried_and_eventually_delivered(db):
    _FakeSmtp.raises = TimeoutError("connection timed out")
    thread = _thread(db)
    message = notify.send_counterparty_message(
        db, thread, "body", gw.SmtpNotificationGateway(_Settings()), "ap@broker.example"
    )
    assert notify.unsent_messages(db) == [message]

    _FakeSmtp.raises = None
    summary = notify.retry_unsent_messages(db, gw.SmtpNotificationGateway(_Settings()))

    assert summary == {"retried": 1, "sent": 1, "abandoned": 0}
    assert message.sent_at is not None
    assert message.attempts == 2
    assert _FakeSmtp.sent[-1]["To"] == "ap@broker.example"


def test_an_auth_failure_is_not_retried_at_all(db):
    # repeatedly presenting a bad App Password to Gmail is how an account gets locked,
    # which would turn one broken notice into every broken notice
    import smtplib

    _FakeSmtp.raises = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    thread = _thread(db)
    message = notify.send_counterparty_message(
        db, thread, "body", gw.SmtpNotificationGateway(_Settings()), "ap@broker.example"
    )
    _FakeSmtp.raises = None
    summary = notify.retry_unsent_messages(db, gw.SmtpNotificationGateway(_Settings()))

    assert summary == {"retried": 0, "sent": 0, "abandoned": 1}
    assert message.sent_at is None, "it stays visible rather than being quietly abandoned"


def test_retrying_is_bounded(db):
    _FakeSmtp.raises = TimeoutError("still down")
    thread = _thread(db)
    notify.send_counterparty_message(
        db, thread, "body", gw.SmtpNotificationGateway(_Settings()), "ap@broker.example"
    )
    for _ in range(notify.MAX_SEND_ATTEMPTS + 3):
        notify.retry_unsent_messages(db, gw.SmtpNotificationGateway(_Settings()))
    assert notify.unsent_messages(db) == [], "a dead address cannot be retried forever"


def test_a_delivered_message_is_never_swept_again(db):
    thread = _thread(db)
    notify.send_counterparty_message(
        db, thread, "body", gw.SmtpNotificationGateway(_Settings()), "ap@broker.example"
    )
    assert notify.retry_unsent_messages(db, gw.SmtpNotificationGateway(_Settings())) == {
        "retried": 0,
        "sent": 0,
        "abandoned": 0,
    }
    assert len(_FakeSmtp.sent) == 1, "a broker must not receive the same notice twice"


def test_the_failure_vocabulary_is_shared_rather_than_matched_by_hand(db):
    assert notify.is_failure("smtp-failed-TimeoutError") is True
    assert notify.is_failure("smtp-<abc@host>") is False
    assert notify.is_retryable("smtp-failed-TimeoutError") is True
    assert notify.is_retryable("smtp-failed-SMTPAuthenticationError") is False
    assert notify.is_retryable("smtp-<abc@host>") is False


def test_the_retry_sweep_is_wired_to_the_worker(db):
    # a sweep nothing calls is the built-and-inert shape this codebase keeps finding.
    # It runs UNFLAGGED on purpose: `is_enabled` answers False for an unregistered flag,
    # so gating a foundation safety net is how it becomes permanently idle.
    from app.worker import _jobs

    job = next(j for j in _jobs() if j.name == "outbound_retry")
    assert job.flag_key is None
    assert job.interval_seconds == 300
