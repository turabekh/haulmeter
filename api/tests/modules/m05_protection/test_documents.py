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

    # AI-CONTEXT: asserts WHICH two survived the budget, not what order they came back
    # in. This read had no ORDER BY and asserted `delivered[0]`, so it depended on the
    # physical order Postgres happened to return three rows in; it passed until an
    # unrelated test started writing more notification rows and changed the heap.
    # Adding `ORDER BY dispatched_at` does not fix it either — both are dispatched at
    # the same instant, so that is a tie, and their relative order is simply not a fact
    # the data records. The scarce-slot RULE is asserted deterministically one test up,
    # against `expiry_reminders_due`, which is where the ordering actually lives.
    delivered = {
        n.title
        for n in db.query(notify.Notification).all()
        if n.status == notify.NotificationStatus.sent
    }
    assert len(delivered) == 2, "§13.1 — two unprompted per driver per day"
    assert any("med card" in t for t in delivered)  # the nearest deadline gets a slot
    assert any("insurance" in t for t in delivered)
    assert not any("permit" in t for t in delivered)  # ...and the furthest loses it


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


# --- replacing a credential: archived, never overwritten ---
def test_a_new_cdl_archives_the_old_one_and_keeps_it(db):
    """§17 Q16 forbids hard delete, and the old card is still the answer to "what
    were you carrying at that inspection in March". Destroying it would destroy
    evidence of a fact that was true."""
    account = _account(db, "renew@example.com")
    old = _doc(db, account, "cdl", 30)
    new = _doc(db, account, "cdl", 1500)

    assert old.archived_at is not None
    assert old.superseded_by_id == new.id
    # the wallet produces the current one, and only the current one
    shown = [d["id"] for d in m5.wallet(db, account.id, as_of=TODAY)["documents"]]
    assert shown == [str(new.id)]
    # ...but the old one is still there for anyone who asks
    kept = documents.documents_for_account(db, account.id, include_archived=True)
    assert len(kept) == 2


def test_a_driver_is_told_what_will_be_replaced_before_they_save(db):
    """The consequence is stated in advance. A driver should not learn their old CDL
    was replaced by noticing it is gone."""
    account = _account(db, "warned-first@example.com")
    old = _doc(db, account, "cdl", 30)

    assert m5.superseded_by_capturing(db, account.id, "cdl").id == old.id
    assert m5.superseded_by_capturing(db, account.id, "insurance") is None


def test_permits_do_not_supersede_each_other(db):
    """A driver carries several at once — IFTA, oversize, a state permit — and
    nothing we collect distinguishes them, so superseding on type alone would archive
    the wrong one."""
    account = _account(db, "permits@example.com")
    _doc(db, account, "permit", 100)
    _doc(db, account, "permit", 200)

    shown = m5.wallet(db, account.id, as_of=TODAY)["documents"]
    assert len(shown) == 2


def test_an_archived_credential_stops_nagging_about_its_expiry(db):
    """Warning about a superseded card would send a driver to renew something they
    have already renewed."""
    account = _account(db, "quiet@example.com")
    _doc(db, account, "med_card", 3)  # expiring, would fire today
    _doc(db, account, "med_card", 900)  # the renewal

    due = [d.doc_type.value for d, _ in m5.expiry_reminders_due(db, TODAY)]
    assert due == []


def test_correcting_an_expiry_reopens_the_reminder_ladder(db):
    """A mistyped date whose 30-day rung was already marked sent would go silent
    against the corrected one."""
    account = _account(db, "correct@example.com")
    doc = _doc(db, account, "cdl", 30)
    gateway = notify.RecordingNotificationGateway()
    m5.dispatch_expiry_reminders(db, gateway, as_of=TODAY, now=NOON)
    assert m5.expiry_reminders_due(db, TODAY) == []

    documents.update_document_meta(db, doc, expires_on=TODAY + timedelta(days=14))

    assert [off for _, off in m5.expiry_reminders_due(db, TODAY)] == [14]


# --- Removal, and why it is not a delete (§17 Q16 / §23) ---
def test_removing_a_document_takes_it_out_of_the_wallet_without_destroying_it(db):
    """What a driver means by "delete": it leaves the wallet. What the product may
    not do: destroy it. §17 Q16 forbids hard delete, and a CDL removed today is still
    the answer to what was carried at an inspection last March — so the row and the
    bytes stay exactly where they were."""
    account = _account(db, "remove@example.com")
    doc = _doc(db, account, "permit", 100)

    m5.archive_own_document(db, account.id, doc.id)

    assert m5.wallet(db, account.id, as_of=TODAY)["documents"] == []
    assert documents.get_document_bytes(db, doc) == b"%PDF-1.4 credential"
    assert db.get(documents.Document, doc.id) is not None


def test_a_removed_document_leaves_inspection_mode(db):
    """Inspection mode produces what the driver is carrying NOW. A credential they
    removed is not that, and an officer is the worst audience for the difference."""
    account = _account(db, "inspect-removed@example.com")
    doc = _doc(db, account, "cdl", 400)

    m5.archive_own_document(db, account.id, doc.id)

    assert m5.inspection_mode(db, account.id, as_of=TODAY) == []


def test_a_removed_credential_stops_the_expiry_ladder(db):
    """Same reasoning as a superseded one: warning about a document the driver has
    taken out of their wallet is a notification they can do nothing useful with."""
    account = _account(db, "removed-quiet@example.com")
    doc = _doc(db, account, "med_card", 3)
    assert [off for _, off in m5.expiry_reminders_due(db, TODAY)] == [3]

    m5.archive_own_document(db, account.id, doc.id)

    assert m5.expiry_reminders_due(db, TODAY) == []


def test_restoring_puts_it_back_and_reopens_the_reminder_ladder(db):
    """A reversible removal is a decision a driver can make with gloves on at a fuel
    desk. Rungs marked sent while the document was out of the wallet would otherwise
    keep a restored credential silent all the way to its expiry date."""
    account = _account(db, "restore@example.com")
    doc = _doc(db, account, "med_card", 3)
    gateway = notify.RecordingNotificationGateway()
    m5.dispatch_expiry_reminders(db, gateway, as_of=TODAY, now=NOON)
    m5.archive_own_document(db, account.id, doc.id)

    m5.restore_own_document(db, account.id, doc.id)

    assert [d["doc_type"] for d in m5.wallet(db, account.id, as_of=TODAY)["documents"]] == [
        "med_card"
    ]
    assert [off for _, off in m5.expiry_reminders_due(db, TODAY)] == [3]


def test_a_restore_is_refused_when_a_current_credential_holds_the_slot(db):
    """Restoring a superseded CDL beside its replacement would put two current
    licences in front of an officer — the exact confusion supersession exists to
    prevent. The refusal names the document in the way."""
    import pytest

    account = _account(db, "two-cdls@example.com")
    old = _doc(db, account, "cdl", 30)
    new = _doc(db, account, "cdl", 900)
    assert old.archived_at is not None  # superseded by the renewal

    with pytest.raises(m5.RestoreBlocked) as caught:
        m5.restore_own_document(db, account.id, old.id)

    assert caught.value.blocker.id == new.id


def test_removing_the_replacement_frees_the_slot_for_the_old_one(db):
    """The round trip that makes the refusal fair: a driver who filed the wrong CDL
    removes it, and the card it archived can come back."""
    account = _account(db, "undo-renewal@example.com")
    old = _doc(db, account, "cdl", 30)
    new = _doc(db, account, "cdl", 900)

    m5.archive_own_document(db, account.id, new.id)
    m5.restore_own_document(db, account.id, old.id)

    assert [d["id"] for d in m5.wallet(db, account.id, as_of=TODAY)["documents"]] == [str(old.id)]


def test_a_permit_never_blocks_a_restore(db):
    """A driver carries several at once — IFTA, oversize, a state permit — which is
    why permits do not supersede either. The two rules are the same rule."""
    account = _account(db, "permits@example.com")
    kept = _doc(db, account, "permit", 100)
    removed = _doc(db, account, "permit", 200)

    m5.archive_own_document(db, account.id, removed.id)
    m5.restore_own_document(db, account.id, removed.id)

    shown = {d["id"] for d in m5.wallet(db, account.id, as_of=TODAY)["documents"]}
    assert shown == {str(kept.id), str(removed.id)}


def test_a_replayed_removal_never_rewrites_why_a_document_was_archived(db):
    """A removal made in a dead zone replays on reconnect. A second archive must not
    fail, and must not relabel a supersession as something the driver did — the
    archive list would then state something untrue about how the row got there."""
    account = _account(db, "replay@example.com")
    old = _doc(db, account, "cdl", 30)
    _doc(db, account, "cdl", 900)

    m5.archive_own_document(db, account.id, old.id)  # the replay
    m5.archive_own_document(db, account.id, old.id)

    row = next(r for r in m5.archived_documents(db, account.id) if r["id"] == str(old.id))
    assert row["reason"] == "superseded"


def test_the_archive_says_why_each_document_is_in_it(db):
    """"Replaced by the CDL you filed" and "you removed this" are different facts and
    lead to different decisions, so the list states which."""
    account = _account(db, "why@example.com")
    superseded = _doc(db, account, "cdl", 30)
    replacement = _doc(db, account, "cdl", 900)
    removed = _doc(db, account, "permit", 100)
    m5.archive_own_document(db, account.id, removed.id)

    rows = {r["id"]: r for r in m5.archived_documents(db, account.id)}

    assert rows[str(superseded.id)]["reason"] == "superseded"
    assert rows[str(superseded.id)]["replaced_by"]["id"] == str(replacement.id)
    assert rows[str(removed.id)]["reason"] == "removed_by_driver"
    assert rows[str(removed.id)]["replaced_by"] is None


def test_the_archive_says_whether_a_restore_will_actually_work(db):
    """A Restore control that exists only to fail is the dead-control pattern this
    surface has already been caught by twice."""
    account = _account(db, "restorable@example.com")
    blocked = _doc(db, account, "cdl", 30)
    _doc(db, account, "cdl", 900)
    free = _doc(db, account, "permit", 100)
    m5.archive_own_document(db, account.id, free.id)

    rows = {r["id"]: r for r in m5.archived_documents(db, account.id)}

    assert rows[str(blocked.id)]["restorable"] is False
    assert rows[str(blocked.id)]["blocked_by_doc_type"] == "cdl"
    assert rows[str(free.id)]["restorable"] is True


def test_the_wallet_carries_the_archived_count(db):
    """So the archive control can say how many are in there without a second request
    on a fuel-desk connection."""
    account = _account(db, "count@example.com")
    doc = _doc(db, account, "permit", 100)
    assert m5.wallet(db, account.id, as_of=TODAY)["archived_count"] == 0

    m5.archive_own_document(db, account.id, doc.id)

    assert m5.wallet(db, account.id, as_of=TODAY)["archived_count"] == 1


def test_you_cannot_remove_a_document_that_is_not_yours(db):
    """A stranger's id must be indistinguishable from a missing one, exactly as the
    viewer route already treats it — otherwise ids can be probed for existence."""
    mine = _account(db, "mine-rm@example.com")
    theirs = _account(db, "theirs-rm@example.com")
    doc = _doc(db, mine, "cdl", 400)

    assert m5.archive_own_document(db, theirs.id, doc.id) is None
    assert m5.restore_own_document(db, theirs.id, doc.id) is None
    assert db.get(documents.Document, doc.id).archived_at is None
