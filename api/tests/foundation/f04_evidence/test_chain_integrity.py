"""F4-2 and F4-4 — the chain checks its anchors, and a race no longer 500s.

Self-consistency is what a competent rewrite produces, so a check that only recomputes
hashes cannot detect one. The anchor is the one record a rewriter cannot fix from inside
the table: it was written earlier and says what the head WAS.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.foundation.f01_identity import public as identity
from app.foundation.f04_evidence import public as evidence
from app.foundation.f04_evidence.domain import hashing
from app.foundation.f04_evidence.domain.models import EvidenceRecord

T0 = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


def _log(db, label="chain"):
    account = identity.register_account(db, f"{label}@example.com", "pw-123456")
    return evidence.create_log(db, account.id, label=label)


def _filled(db, label="chain", n=3):
    log = _log(db, label)
    for i in range(n):
        evidence.append_record(
            db, log, evidence.RecordType.SYSTEM, {"event": f"e{i}"}, occurred_at=T0
        )
    return log


# --- F4-2: the cross-check ---
def test_a_consistently_rewritten_chain_no_longer_passes(db):
    """The attack the old check could not see.

    Doctor a payload, then re-hash that record AND every record after it so the links all
    agree again. Every hash recomputation passes — the chain is perfectly self-consistent.
    Only the anchor, written before the rewrite, still remembers the real head.
    """
    log = _filled(db, "rewrite")
    evidence.anchor_chain(db, log)
    records = db.query(EvidenceRecord).filter_by(log_id=log.id).order_by(EvidenceRecord.seq).all()

    records[1].payload = {"event": "something else entirely"}
    prev = records[0].record_hash
    for record in records[1:]:
        record.prev_hash = prev
        record.record_hash = hashing.compute_record_hash(
            prev, record.seq, record.record_type.value, record.payload, record.occurred_at
        )
        prev = record.record_hash
    db.flush()

    result = evidence.verify_chain(db, log)

    assert result.valid is False
    assert result.reason == "anchor_mismatch"
    assert result.broken_at == records[-1].seq  # the anchored head is where it disagrees


def test_an_unanchored_chain_still_verifies_on_its_own(db):
    """The cross-check must not turn "never anchored" into "broken"."""
    log = _filled(db, "unanchored")

    assert evidence.verify_chain(db, log).valid is True


def test_appending_after_an_anchor_is_not_a_mismatch(db):
    """Every log this product makes is anchored and then appended to."""
    log = _filled(db, "grown")
    evidence.anchor_chain(db, log)

    evidence.append_record(db, log, evidence.RecordType.SYSTEM, {"event": "later"})

    assert evidence.verify_chain(db, log).valid is True


def test_only_the_latest_anchor_is_consulted(db):
    """An older anchor legitimately describes a shorter chain."""
    log = _filled(db, "twice")
    evidence.anchor_chain(db, log)
    evidence.append_record(db, log, evidence.RecordType.SYSTEM, {"event": "more"})
    evidence.anchor_chain(db, log)

    assert evidence.verify_chain(db, log).valid is True


def test_a_tampered_record_is_still_reported_as_tampered(db):
    """The two failures mean different things to whoever reads the PDF."""
    log = _filled(db, "tampered")
    evidence.anchor_chain(db, log)
    record = db.query(EvidenceRecord).filter_by(log_id=log.id, seq=1).one()

    record.payload = {"event": "doctored"}  # hash NOT recomputed
    db.flush()

    result = evidence.verify_chain(db, log)
    assert result.valid is False
    assert result.reason == "tampered"


# --- F4-2: provenance in the render ---
def test_an_internal_only_anchor_does_not_claim_an_external_timestamp(db):
    log = _filled(db, "internal")
    evidence.anchor_chain(db, log)  # no external_ref — every anchor this product writes

    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)

    assert pack.verification["anchored"] is False
    assert pack.verification["anchor_recorded"] is True


def test_an_externally_anchored_chain_says_so(db):
    log = _filled(db, "external")
    evidence.anchor_chain(db, log, external_ref="ots:deadbeef")

    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)

    assert pack.verification["anchored"] is True
    assert pack.verification["anchor_ref"] == "ots:deadbeef"


def test_the_rendered_line_distinguishes_the_three_states():
    from app.foundation.f04_evidence.domain.render import _anchor_line

    assert _anchor_line({"anchored": True, "anchor_recorded": True}).startswith("yes")
    internal = _anchor_line({"anchored": False, "anchor_recorded": True})
    assert "internal" in internal and "no external timestamp" in internal
    assert _anchor_line({}) == "not yet anchored"


# --- F4-4: the race ---
def _plant_winner(db, log, head):
    """A row at the seq the caller is about to claim — a concurrent commit, from here."""
    payload = {"event": "the winner"}
    db.add(
        EvidenceRecord(
            log_id=log.id,
            seq=head.seq + 1,
            record_type=evidence.RecordType.SYSTEM,
            payload=payload,
            occurred_at=T0,
            prev_hash=head.record_hash,
            record_hash=hashing.compute_record_hash(
                head.record_hash, head.seq + 1, "SYSTEM", payload, T0
            ),
        )
    )
    db.flush()


def test_two_racing_appends_both_survive_with_consecutive_seqs(db, monkeypatch):
    """The pre-fix behaviour was an unhandled IntegrityError — a 500 and a lost upload.

    THE STALE READ IS THE WHOLE TEST, and the first version of it did not have one:
    planting the winner and then calling `append_record` in the same session meant the
    head read already SAW the winner, so no collision ever happened and the retry was
    never entered — the test passed with the retry deleted. A real race is a head read
    that is already out of date by the time the insert lands, so that is what is forced:
    `_last_record` returns the stale head once, then tells the truth.
    """
    from app.foundation.f04_evidence.domain import service

    log = _filled(db, "race", n=1)
    head = db.query(EvidenceRecord).filter_by(log_id=log.id).order_by(EvidenceRecord.seq).all()[-1]
    _plant_winner(db, log, head)

    real_last_record = service._last_record
    calls = {"n": 0}

    def stale_once(session, log_id):
        calls["n"] += 1
        return head if calls["n"] == 1 else real_last_record(session, log_id)

    monkeypatch.setattr(service, "_last_record", stale_once)

    loser = evidence.append_record(
        db, log, evidence.RecordType.PHOTO, {"event": "the driver's photo"}, occurred_at=T0
    )

    assert calls["n"] == 2  # it collided and re-read, rather than sailing past
    assert loser.seq == head.seq + 2
    seqs = [
        r.seq
        for r in db.query(EvidenceRecord).filter_by(log_id=log.id).order_by(EvidenceRecord.seq)
    ]
    assert seqs == list(range(len(seqs)))  # consecutive, no gap, no fork


def test_a_sustained_collision_still_raises_rather_than_looping(db, monkeypatch):
    """One retry, not a loop. Two writers on one stop's log is not a thing this does."""
    from app.foundation.f04_evidence.domain import service

    log = _filled(db, "race-forever", n=1)
    head = db.query(EvidenceRecord).filter_by(log_id=log.id).order_by(EvidenceRecord.seq).all()[-1]
    _plant_winner(db, log, head)
    monkeypatch.setattr(service, "_last_record", lambda session, log_id: head)

    with pytest.raises(IntegrityError):
        evidence.append_record(db, log, evidence.RecordType.PHOTO, {"e": "x"}, occurred_at=T0)


def test_the_chain_still_verifies_after_a_recovered_race(db):
    log = _filled(db, "race-valid", n=1)
    head = db.query(EvidenceRecord).filter_by(log_id=log.id).order_by(EvidenceRecord.seq).all()[-1]
    db.add(
        EvidenceRecord(
            log_id=log.id,
            seq=head.seq + 1,
            record_type=evidence.RecordType.SYSTEM,
            payload={"event": "winner"},
            occurred_at=T0,
            prev_hash=head.record_hash,
            record_hash=hashing.compute_record_hash(
                head.record_hash, head.seq + 1, "SYSTEM", {"event": "winner"}, T0
            ),
        )
    )
    db.flush()

    evidence.append_record(db, log, evidence.RecordType.PHOTO, {"event": "photo"}, occurred_at=T0)

    assert evidence.verify_chain(db, log).valid is True


def test_the_unique_constraint_is_still_the_invariant(db):
    """The retry recovers from the constraint; it does not replace it."""
    log = _filled(db, "invariant", n=1)
    head = db.query(EvidenceRecord).filter_by(log_id=log.id).order_by(EvidenceRecord.seq).all()[-1]

    db.add(
        EvidenceRecord(
            log_id=log.id,
            seq=head.seq,  # a duplicate seq, inserted directly
            record_type=evidence.RecordType.SYSTEM,
            payload={"event": "fork"},
            occurred_at=T0,
            prev_hash=head.prev_hash,
            record_hash="whatever",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()
