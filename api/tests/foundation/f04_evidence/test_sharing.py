"""AI-CONTEXT: "persist on share" — a record of an act, not a cache.

Rendering is deterministic, so regenerating a pack on demand is free and always
current. Sharing is a different act, and the difference is the whole point: **a pack
shared at 14:00 and regenerated at 16:00 after another photo lands is a different
document.** In a dispute nobody asks what the pack says now; they ask what was sent.

What these defend:

· the link serves the PINNED bytes, forever, even as the chain grows underneath it
· revocation stops the hosting and does NOT erase the record of what was sent
· unknown, revoked and expired are indistinguishable from outside — a caller must
  not be able to probe tokens and learn which
· the first open lands in the chain, because "they opened it on the 12th" is
  evidence; the fourth refresh is not a fourth fact
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f04_evidence import public as evidence
from app.foundation.f06_documents import public as documents

T0 = datetime(2026, 7, 20, 7, 58, tzinfo=UTC)


@pytest.fixture
def storage():
    return documents.InMemoryObjectStorage()


def _account(db, email="share@example.com"):
    return identity.register_account(db, email, "pw-123456")


def _log_with_pack(db, account, label="Load 4471"):
    log = evidence.create_log(db, account.id, label=label)
    evidence.append_record(
        db, log, evidence.RecordType.GEOFENCE, {"event": "enter", "lat": 32.7, "lon": -96.8}, T0
    )
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.cargo_condition)
    return log, pack


def test_sharing_pins_the_bytes_that_were_sent(db, storage):
    account = _account(db)
    log, pack = _log_with_pack(db, account)
    sent = evidence.render_pack_pdf(pack)

    shared = evidence.share_pack(
        db, log, pack.template, sent, account.id, recipient="ap@acme.example", storage=storage
    )

    assert shared.content_hash and len(shared.content_hash) == 64
    assert evidence.open_share(db, shared.token, storage=storage) == sent


def test_the_link_keeps_serving_the_sent_document_after_the_chain_grows(db, storage):
    """The reason this table exists. A photo landing at 16:00 must not change what
    the counterparty sees when they open the link they were given at 14:00."""
    account = _account(db, "grows@example.com")
    log, pack = _log_with_pack(db, account)
    sent = evidence.render_pack_pdf(pack)
    shared = evidence.share_pack(db, log, pack.template, sent, account.id, storage=storage)

    # more evidence arrives afterwards
    evidence.attach_artifact(
        db, log, evidence.ArtifactType.photo, content=b"late-photo", captured_at=T0
    )
    regenerated = evidence.render_pack_pdf(
        evidence.compose_pack(db, log, evidence.PackTemplate.cargo_condition)
    )

    assert regenerated != sent, "the chain really did change"
    assert evidence.open_share(db, shared.token, storage=storage) == sent


def test_revoking_ends_the_hosting_and_keeps_the_record(db, storage):
    """Closing a link does not unsend a document — the counterparty may already hold
    a copy — so what was sent stays on the record."""
    account = _account(db, "revoke@example.com")
    log, pack = _log_with_pack(db, account)
    shared = evidence.share_pack(
        db, log, pack.template, evidence.render_pack_pdf(pack), account.id, storage=storage
    )
    original_hash = shared.content_hash

    evidence.revoke_share(db, shared)

    with pytest.raises(evidence.ShareNotFound):
        evidence.open_share(db, shared.token, storage=storage)
    assert shared.content_hash == original_hash
    assert shared.storage_key
    assert evidence.shares_for_log(db, log.id) == [shared]


def test_an_expired_link_closes_itself(db, storage):
    account = _account(db, "expiry@example.com")
    log, pack = _log_with_pack(db, account)
    shared = evidence.share_pack(
        db, log, pack.template, evidence.render_pack_pdf(pack), account.id, storage=storage
    )

    later = shared.expires_at + timedelta(days=1)
    with pytest.raises(evidence.ShareNotFound):
        evidence.open_share(db, shared.token, now=later, storage=storage)


def test_unknown_revoked_and_expired_are_indistinguishable(db, storage):
    """A caller must not be able to learn which by probing."""
    account = _account(db, "probe@example.com")
    log, pack = _log_with_pack(db, account)
    shared = evidence.share_pack(
        db, log, pack.template, evidence.render_pack_pdf(pack), account.id, storage=storage
    )
    evidence.revoke_share(db, shared)

    for token in (shared.token, "a-token-that-never-existed"):
        with pytest.raises(evidence.ShareNotFound):
            evidence.resolve_share(db, token)


def test_the_share_and_the_first_open_are_written_into_the_chain(db, storage):
    """Sharing is an event in the life of the evidence, and so is the counterparty
    receiving it. Only the FIRST open: a clerk refreshing is not new information."""
    account = _account(db, "chained@example.com")
    log, pack = _log_with_pack(db, account)
    shared = evidence.share_pack(
        db, log, pack.template, evidence.render_pack_pdf(pack), account.id, storage=storage
    )

    evidence.open_share(db, shared.token, storage=storage)
    evidence.open_share(db, shared.token, storage=storage)
    evidence.open_share(db, shared.token, storage=storage)

    after = evidence.compose_pack(db, log, evidence.PackTemplate.cargo_condition)
    events = [r["payload"].get("event") for r in after.timeline]
    assert events.count("pack_shared") == 1
    assert events.count("pack_opened") == 1
    assert shared.opened_count == 3
    assert shared.first_opened_at is not None
    # and the chain still verifies with those records in it
    assert after.verification["chain_valid"] is True


def test_two_shares_of_the_same_unchanged_pack_have_the_same_hash(db, storage):
    """Determinism carries through: the same evidence produces the same document, so
    sharing it twice is provably the same artifact under two links."""
    account = _account(db, "twice@example.com")
    log, pack = _log_with_pack(db, account)
    content = evidence.render_pack_pdf(pack)

    first = evidence.share_pack(db, log, pack.template, content, account.id, storage=storage)
    second = evidence.share_pack(db, log, pack.template, content, account.id, storage=storage)

    assert first.content_hash == second.content_hash
    assert first.token != second.token


def test_a_link_can_be_extended_because_disputes_outlive_ap_cycles(db, storage):
    """M3's dunning runs to day 21 and that is only the escalation OFFER; partner
    collection follows and PRD §8.3 prices it for aged accounts. A link dying
    mid-collection makes the driver look like they withdrew their evidence."""
    account = _account(db, "extend@example.com")
    log, pack = _log_with_pack(db, account)
    shared = evidence.share_pack(
        db, log, pack.template, evidence.render_pack_pdf(pack), account.id, storage=storage
    )
    original = shared.expires_at

    evidence.extend_share(db, shared, days=500)

    assert shared.expires_at > original
    assert evidence.open_share(db, shared.token, storage=storage)


def test_extend_never_shortens_a_link(db, storage):
    """Caught by a failing test: with the default at a year, extend(days=180) moved
    the expiry CLOSER. A function called extend that can cut a link short is a trap
    for its next caller."""
    account = _account(db, "noshorten@example.com")
    log, pack = _log_with_pack(db, account)
    shared = evidence.share_pack(
        db, log, pack.template, evidence.render_pack_pdf(pack), account.id, storage=storage
    )
    original = shared.expires_at

    evidence.extend_share(db, shared, days=1)

    assert shared.expires_at == original


def test_extending_counts_from_now_not_from_a_date_already_past(db, storage):
    account = _account(db, "lapsed@example.com")
    log, pack = _log_with_pack(db, account)
    shared = evidence.share_pack(
        db, log, pack.template, evidence.render_pack_pdf(pack), account.id, storage=storage
    )
    shared.expires_at = datetime(2020, 1, 1, tzinfo=UTC)  # long lapsed
    db.flush()

    evidence.extend_share(db, shared, days=30)

    # "keep it alive" must mean 30 days from today, not 30 days from 2020
    assert shared.expires_at > datetime.now(UTC)


def test_extending_does_not_resurrect_a_revoked_link(db, storage):
    """Revocation was about intent; extension is about time. One must not undo the
    other by accident."""
    account = _account(db, "revoked-extend@example.com")
    log, pack = _log_with_pack(db, account)
    shared = evidence.share_pack(
        db, log, pack.template, evidence.render_pack_pdf(pack), account.id, storage=storage
    )
    evidence.revoke_share(db, shared)

    evidence.extend_share(db, shared, days=90)

    with pytest.raises(evidence.ShareNotFound):
        evidence.open_share(db, shared.token, storage=storage)
