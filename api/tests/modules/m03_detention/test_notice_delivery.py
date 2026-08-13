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
from app.foundation.f04_evidence import public as evidence
from app.foundation.f05_load import public as loads
from app.foundation.f08_notifications import public as notify
from app.modules.m03_detention import public as m3

# the gateway handed to a SEND is ignored now — the transport lives in the sweep — so
# tests name it once rather than spelling it out at every call site
RECORDING = notify.RecordingNotificationGateway
DALLAS = (32.7767, -96.7970)
FAR = (32.9000, -96.8000)
T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
ACCRUING = T0 + timedelta(minutes=180)


class FailingGateway:
    """The real gateway's failure contract: never raise, return a `smtp-failed-…` ref."""

    def __init__(self, kind="SMTPServerDisconnected"):
        self.kind = kind
        self.sent = []

    def send_email(self, to_ref, subject, body, attachments=None):
        self.sent.append(to_ref)
        return f"smtp-failed-{self.kind}"


def flush_gateway_delivery(db, gateway, now):
    """The `outbound_mail` job, as the worker runs it: deliver, then reconcile.

    Spelled out here rather than taken from the `flush_outbox` fixture because these tests
    swap the gateway per case, and the gateway is the thing under test."""
    summary = notify.retry_unsent_messages(db, gateway, now=now)
    m3.reconcile_delivered_notices(db, summary.pop("delivered", []))
    db.flush()
    return summary


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


def test_a_recorded_notice_is_QUEUED_not_failed(db):
    """AI-CONTEXT: the sixth state, and the reason it had to exist.

    Sending is asynchronous now, so between the tap and the `outbound_mail` sweep the row
    has `provider_ref` NULL — never attempted. `is_retryable(None)` is False, because it
    asks "is this FAILURE worth another go?" of something nothing has tried, so the ladder
    fell straight through to FAILED and a driver who had just tapped Send would have read
    **"Notice failed — broker not reached"** about a notice sitting correctly in the
    outbox, seconds before it went.
    """
    _, claim = _claim(db)

    recording = notify.RecordingNotificationGateway()
    message = m3.send_detention_start_notice(db, claim, recording, ACCRUING)

    assert message.sent_at is None, "nothing has gone out yet"
    assert claim.start_notice_message_ref == message.id, "we decided to send; the ref says so"
    assert claim.start_notice_sent_at is None, "the timestamp means it WENT, and it has not"
    assert m3.notice_delivery(db, claim) == m3.DELIVERY_QUEUED


def test_a_delivered_notice_is_sent_and_stamps_the_claim(db):
    _, claim = _claim(db)
    gateway = notify.RecordingNotificationGateway()

    message = m3.send_detention_start_notice(db, claim, gateway, ACCRUING)
    flush_gateway_delivery(db, gateway, ACCRUING)

    assert message.sent_at is not None
    assert claim.start_notice_message_ref == message.id
    assert claim.start_notice_sent_at == ACCRUING
    assert m3.notice_delivery(db, claim) == m3.DELIVERY_SENT


def test_a_transient_failure_is_retrying_and_does_not_stamp_the_claim(db):
    _, claim = _claim(db)

    recording = notify.RecordingNotificationGateway()
    message = m3.send_detention_start_notice(db, claim, recording, ACCRUING)
    # the gateway that matters is the SWEEP's now — that is where the transport lives
    flush_gateway_delivery(db, FailingGateway(), ACCRUING)

    assert message.sent_at is None
    # the ref IS recorded — we decided to send, and a retry needs to find the row
    assert claim.start_notice_message_ref == message.id
    # the TIMESTAMP is not: it means it went out, and it did not
    assert claim.start_notice_sent_at is None
    assert m3.notice_delivery(db, claim) == m3.DELIVERY_RETRYING


def test_a_permanent_failure_is_failed_not_retrying(db):
    _, claim = _claim(db)

    m3.send_detention_start_notice(db, claim, RECORDING(), ACCRUING)
    flush_gateway_delivery(db, FailingGateway("SMTPAuthenticationError"), ACCRUING)

    assert m3.notice_delivery(db, claim) == m3.DELIVERY_FAILED


def test_an_exhausted_message_is_failed(db):
    _, claim = _claim(db)
    m3.send_detention_start_notice(db, claim, FailingGateway(), ACCRUING)
    message = db.get(notify.OutboundMessage, claim.start_notice_message_ref)

    message.attempts = notify.MAX_SEND_ATTEMPTS
    db.flush()

    assert m3.notice_delivery(db, claim) == m3.DELIVERY_FAILED


def test_tapping_send_again_while_QUEUED_does_not_queue_a_second_notice(db):
    """AI-CONTEXT: the window this defect lives in got much wider, so this matters more.

    §23 entry 136 fixed a double-send at the UI — `onSendNotice` had no in-flight guard
    and "genuinely sent a broker two emails on a double tap". That guard covered one round
    trip. A queued notice is un-sent for a whole sweep interval, and a replayed offline
    write or a driver returning to the screen reaches straight past any client-side guard.
    A queued row is therefore an EXISTING notice, and `_existing_start_notice` says so.
    """
    _, claim = _claim(db)
    first = m3.send_detention_start_notice(db, claim, RECORDING(), ACCRUING)

    again = m3.send_detention_start_notice(
        db, claim, notify.RecordingNotificationGateway(), ACCRUING + timedelta(minutes=1)
    )

    assert again.id == first.id
    assert len(notify.unsent_messages(db)) == 1, "one stop, one notice"


def test_tapping_send_again_while_retrying_does_not_queue_a_second_notice(db):
    """One stop, one notice. The retry sweep owns the row until it gives up."""
    _, claim = _claim(db)
    gateway = FailingGateway()
    first = m3.send_detention_start_notice(db, claim, RECORDING(), ACCRUING)
    flush_gateway_delivery(db, gateway, ACCRUING)

    again = m3.send_detention_start_notice(db, claim, gateway, ACCRUING + timedelta(minutes=1))

    assert again.id == first.id
    assert len(gateway.sent) == 1
    assert len(notify.unsent_messages(db)) == 1


def test_the_sweep_turns_retrying_into_sent_AND_stamps_the_claim(db):
    """AI-CONTEXT: the accepted asymmetry is CLOSED, and it had to be.

    `notice_delivery`'s docstring recorded it: a notice that failed and later succeeded on
    the sweep read `sent` — that is computed live — but gained no `notice_sent` evidence
    record, because nothing re-entered M3's code path. So the pack UNDERSTATED, which was
    the right direction to be wrong in and a rare case besides.

    Asynchronous sending makes it EVERY case. Every notice is delivered by the sweep, so
    every detention pack would have lost "we notified the broker at 10:05" — the fact a
    dispute turns on. `reconcile_delivered_notices` runs in the same job and closes it.
    """
    _, claim = _claim(db)
    m3.send_detention_start_notice(db, claim, RECORDING(), ACCRUING)
    flush_gateway_delivery(db, FailingGateway(), ACCRUING)
    assert m3.notice_delivery(db, claim) == m3.DELIVERY_RETRYING

    flush_gateway_delivery(db, notify.RecordingNotificationGateway(), ACCRUING)

    assert m3.notice_delivery(db, claim) == m3.DELIVERY_SENT
    assert claim.start_notice_sent_at == ACCRUING, "the claim must be stamped, not only derived"


def test_the_reconcile_writes_the_evidence_record_the_pack_argues_from(db):
    _, claim = _claim(db)
    stop = loads.get_stop(db, claim.stop_ref)
    m3.send_detention_start_notice(db, claim, RECORDING(), ACCRUING)

    flush_gateway_delivery(db, notify.RecordingNotificationGateway(), ACCRUING)

    # read through the same seam the pack composes from, so this cannot pass against a
    # record the pack itself would not see
    timeline = evidence.stop_evidence(db, stop.id)["timeline"]
    assert any(e.get("event") == loads.EVENT_NOTICE_SENT for e in timeline), (
        "without this line a detention pack cannot say the broker was ever told"
    )


def test_the_reconcile_does_not_append_the_record_twice(db):
    # a hash-chained evidence log: a second entry for one stop is not a cosmetic problem
    _, claim = _claim(db)
    stop = loads.get_stop(db, claim.stop_ref)
    m3.send_detention_start_notice(db, claim, RECORDING(), ACCRUING)

    flush_gateway_delivery(db, notify.RecordingNotificationGateway(), ACCRUING)
    flush_gateway_delivery(db, notify.RecordingNotificationGateway(), ACCRUING)

    timeline = evidence.stop_evidence(db, stop.id)["timeline"]
    notices = [e for e in timeline if e.get("event") == loads.EVENT_NOTICE_SENT]
    assert len(notices) == 1
