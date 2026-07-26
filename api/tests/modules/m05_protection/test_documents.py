"""AI-CONTEXT: M5-FR3 — the wallet's writer, and the notifier that depends on it.

These shipped together on purpose. The Docs tab was a READER with no writer: both
driver-facing document endpoints were GETs, so a vendor could upload a business
licence through the portal while a driver could not upload their own CDL. The tab was
therefore empty, and F6's expiry engine — which counts down from `expires_on` — had
nothing to count. Building the notifier first would have shipped a dispatcher with
nothing to dispatch.

The load-bearing rule is the ORDERING. §13.1 allows two unprompted notifications per
driver per day; five credentials at 30/14/3 is fifteen events, so most of them lose.
When something has to lose, the survivor should be the most urgent.
"""

from datetime import UTC, date, datetime, timedelta

from app.foundation.f01_identity import public as identity
from app.foundation.f06_documents import public as documents
from app.foundation.f08_notifications import public as notify
from app.modules.m05_protection import public as m5

TODAY = date(2026, 7, 20)
NOON = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _account(db, email="wallet@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _doc(db, account, doc_type, days_out):
    return m5.capture_document(
        db,
        account.id,
        doc_type,
        b"%PDF-1.4 credential",
        filename=f"{doc_type}.pdf",
        content_type="application/pdf",
        expires_on=TODAY + timedelta(days=days_out),
    )


def test_a_driver_can_finally_file_their_own_credential(db):
    account = _account(db)
    doc = _doc(db, account, "cdl", 400)

    assert doc.doc_type == documents.DocType.cdl
    assert m5.wallet(db, account.id, as_of=TODAY)["documents"][0]["doc_type"] == "cdl"


def test_the_wallet_only_accepts_types_a_driver_actually_files(db):
    """A lumper receipt arrives from M4's claim flow and a settlement from M9.
    Offering them here would invite a driver to file a receipt in the wrong place."""
    import pytest

    account = _account(db, "types@example.com")
    with pytest.raises(ValueError):
        m5.capture_document(db, account.id, "settlement", b"x")


def test_a_captured_credential_becomes_something_to_warn_about(db):
    """The two halves meeting: before the writer existed, nothing a driver did could
    create a document with an expiry date, so the dispatcher had nothing to send."""
    account = _account(db, "warned@example.com")
    _doc(db, account, "med_card", 14)

    due = m5.expiry_reminders_due(db, TODAY)

    assert [(d.doc_type.value, offset) for d, offset in due] == [("med_card", 14)]


def test_when_the_cap_bites_the_nearest_expiry_wins(db):
    """§13.1 allows two a day. A driver with a full wallet generates more than that,
    so the order decides what a driver actually hears — and a medical card expiring
    in three days beats a permit expiring in thirty."""
    account = _account(db, "ordering@example.com")
    _doc(db, account, "permit", 30)
    _doc(db, account, "insurance", 14)
    _doc(db, account, "med_card", 3)

    ordered = [d.doc_type.value for d, _ in m5.expiry_reminders_due(db, TODAY)]

    assert ordered == ["med_card", "insurance", "permit"]


def test_the_budget_lets_the_two_most_urgent_through(db):
    account = _account(db, "budget@example.com")
    for doc_type, days in (("permit", 30), ("insurance", 14), ("med_card", 3)):
        _doc(db, account, doc_type, days)
    gateway = notify.RecordingNotificationGateway()

    m5.dispatch_expiry_reminders(db, gateway, as_of=TODAY, now=NOON)

    delivered = [
        n for n in db.query(notify.Notification).all() if n.status == notify.NotificationStatus.sent
    ]
    assert len(delivered) == 2, "§13.1 — two unprompted per driver per day"
    assert "med card" in delivered[0].title


def test_a_reminder_is_not_re_offered_every_morning(db):
    """Marked sent when DISPATCHED, not when delivered. F8 may suppress for quiet
    hours or budget, and re-offering the same 30-day warning daily until one gets
    through is the nagging §13 exists to prevent. The next rung still comes."""
    account = _account(db, "once@example.com")
    _doc(db, account, "cdl", 30)
    gateway = notify.RecordingNotificationGateway()

    m5.dispatch_expiry_reminders(db, gateway, as_of=TODAY, now=NOON)
    again = m5.dispatch_expiry_reminders(db, gateway, as_of=TODAY, now=NOON)

    assert again == []


def test_the_next_rung_still_arrives(db):
    account = _account(db, "rungs@example.com")
    _doc(db, account, "cdl", 30)
    gateway = notify.RecordingNotificationGateway()

    m5.dispatch_expiry_reminders(db, gateway, as_of=TODAY, now=NOON)
    # sixteen days later the 14-day rung is due and is a different offset
    later = TODAY + timedelta(days=16)
    due = [offset for _, offset in m5.expiry_reminders_due(db, later)]

    assert due == [14]


def test_expiry_needs_no_new_notification_class(db):
    """§13.2 names "doc expires this week" as a P1 example, so these ride the ordinary
    tier rules. A new opt-in class would be a §22.2 stop; this is not one."""
    assert notify.get_class("document_expiry") is None
