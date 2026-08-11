"""Findings F4 and F5 — "sent" means the message row has `sent_at`, and nothing else.

The rule these tests exist to hold: a claim, a route and an evidence log may only assert a
delivery the F8 row can support. `send_counterparty_message` returns a message object for a
FAILED send too — that is the F-06 contract, a gateway may never fail its caller — so
"an object came back" was never evidence of anything, and three separate assertions were
built on it.
"""

import pathlib
import subprocess
from datetime import UTC, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f02_facility import public as facility
from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
from app.modules.m03_detention import public as m3

DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
ACCRUING = T0 + timedelta(minutes=180)


class FailingGateway:
    """The real gateway's failure contract: never raise, return a `smtp-failed-…` ref."""

    def __init__(self, kind="SMTPServerDisconnected"):
        self.kind = kind
        self.sent = []

    def send_email(self, to_ref, subject, body):
        self.sent.append(to_ref)
        return f"smtp-failed-{self.kind}"


def _claim(db, email="ap@acme.com", broker=True):
    account = identity.register_account(db, f"oo{email}@example.com", "pw-123456")
    identity.upsert_driver_profile(db, account, authority_type=identity.AuthorityType.own_mc)
    dock = facility.create_facility(db, facility.FacilityType.shipper_receiver, "Dock", *DALLAS)
    cp = (
        loads.create_counterparty(
            db, "Acme", loads.CounterpartyKind.broker, contact_email=email
        )
        if broker
        else None
    )
    load = loads.create_load(
        db, account.id, counterparty_id=cp.id if cp else None,
        detention_rate_cents_per_hour=7500, free_time_minutes=120,
    )
    stop = loads.add_stop(db, load, dock.id, loads.StopType.delivery, appointment_start=T0)
    claim = m3.start_claim(db, stop, started_at=T0)
    location.evaluate_ping(db, account.id, *DALLAS, occurred_at=T0)
    return account, claim


# --- F4: the literal is gone ---
def test_the_fake_recipient_does_not_exist_anywhere_in_the_tree():
    """A grep, deliberately. The string is the defect; its absence is the fix.

    Four call sites used `counterparty@unknown` as a fallback address. It is not an
    address: against real SMTP it is an `SMTPRecipientsRefused`, which is a PERMANENT
    failure the retry sweep will never re-present — so the notice was unrecoverable, while
    the driver's screen reported success over it.
    """
    root = pathlib.Path(__file__).resolve().parents[3]
    # Assembled at runtime so this file does not contain the thing it forbids — the first
    # version of this test failed on its own source, which is the correct answer to the
    # wrong question. Prose about the defect uses backticks and stays findable; what must
    # never come back is the literal as a VALUE.
    needle = '"counterparty@' + 'unknown"'
    found = subprocess.run(
        ["grep", "-rn", needle, "app", "tests"], cwd=root, capture_output=True, text=True
    )
    assert found.stdout.strip() == "", f"the fake recipient is back:\n{found.stdout}"


def test_a_claim_with_no_broker_email_sends_nothing_at_all(db):
    account, claim = _claim(db, broker=False)
    gateway = notify.RecordingNotificationGateway()

    message = m3.send_detention_start_notice(db, claim, gateway, ACCRUING)

    assert message is None
    assert gateway.sent == []  # not addressed to anything, real or invented
    assert claim.start_notice_message_ref is None
    assert claim.start_notice_sent_at is None
    assert m3.notice_delivery(db, claim) == m3.DELIVERY_NO_EMAIL


# --- F5: the five states ---
def test_a_claim_nobody_has_notified_yet_is_not_sent(db):
    _, claim = _claim(db)

    assert m3.notice_delivery(db, claim) == m3.DELIVERY_NOT_SENT


def test_a_successful_send_is_sent_and_stamps_the_claim(db):
    _, claim = _claim(db)
    gateway = notify.RecordingNotificationGateway()

    message = m3.send_detention_start_notice(db, claim, gateway, ACCRUING)

    assert message.sent_at is not None
    assert claim.start_notice_message_ref == message.id
    assert claim.start_notice_sent_at == ACCRUING
    assert m3.notice_delivery(db, claim) == m3.DELIVERY_SENT


def test_a_transient_failure_is_retrying_and_does_not_stamp_the_claim(db):
    _, claim = _claim(db)

    message = m3.send_detention_start_notice(db, claim, FailingGateway(), ACCRUING)

    assert message.sent_at is None
    # the ref IS recorded — we decided to send, and a retry needs to find the row
    assert claim.start_notice_message_ref == message.id
    # the TIMESTAMP is not: it means it went out, and it did not
    assert claim.start_notice_sent_at is None
    assert m3.notice_delivery(db, claim) == m3.DELIVERY_RETRYING


def test_a_permanent_failure_is_failed_not_retrying(db):
    _, claim = _claim(db)

    m3.send_detention_start_notice(db, claim, FailingGateway("SMTPAuthenticationError"), ACCRUING)

    assert m3.notice_delivery(db, claim) == m3.DELIVERY_FAILED


def test_an_exhausted_message_is_failed(db):
    _, claim = _claim(db)
    m3.send_detention_start_notice(db, claim, FailingGateway(), ACCRUING)
    message = db.get(notify.OutboundMessage, claim.start_notice_message_ref)

    message.attempts = notify.MAX_SEND_ATTEMPTS
    db.flush()

    assert m3.notice_delivery(db, claim) == m3.DELIVERY_FAILED


def test_tapping_send_again_while_retrying_does_not_queue_a_second_notice(db):
    """One stop, one notice. The retry sweep owns the row until it gives up."""
    _, claim = _claim(db)
    gateway = FailingGateway()
    first = m3.send_detention_start_notice(db, claim, gateway, ACCRUING)

    again = m3.send_detention_start_notice(db, claim, gateway, ACCRUING + timedelta(minutes=1))

    assert again.id == first.id
    assert len(gateway.sent) == 1
    assert len(notify.unsent_messages(db)) == 1


def test_the_retry_sweep_turns_retrying_into_sent_without_touching_the_claim(db):
    """The accepted asymmetry: delivery is derived live, the evidence pack is not."""
    _, claim = _claim(db)
    m3.send_detention_start_notice(db, claim, FailingGateway(), ACCRUING)
    assert m3.notice_delivery(db, claim) == m3.DELIVERY_RETRYING

    notify.retry_unsent_messages(db, notify.RecordingNotificationGateway(), now=ACCRUING)

    assert m3.notice_delivery(db, claim) == m3.DELIVERY_SENT
