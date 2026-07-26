import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from app.foundation.f01_identity import public as identity
from app.foundation.f04_evidence import public as evidence

T0 = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


def _log(db, email="driver@example.com"):
    account = identity.register_account(db, email, "pw-123456")
    return evidence.create_log(db, account.id, label="Stop @ Dock 7")


def test_records_are_hash_chained(db):
    log = _log(db)
    r0 = evidence.append_record(db, log, evidence.RecordType.GEOFENCE, {"event": "ENTER"}, T0)
    r1 = evidence.append_record(
        db, log, evidence.RecordType.USER_ACTION, {"action": "snap_bol"}, T0 + timedelta(minutes=1)
    )
    assert r0.seq == 0
    assert r1.seq == 1
    assert r1.prev_hash == r0.record_hash
    assert r0.prev_hash != r0.record_hash


def test_verify_chain_valid_for_untampered(db):
    log = _log(db)
    for i in range(4):
        evidence.append_record(
            db, log, evidence.RecordType.SYSTEM, {"i": i}, T0 + timedelta(minutes=i)
        )
    result = evidence.verify_chain(db, log)
    assert result.valid is True
    assert result.record_count == 4
    assert result.head_seq == 3


def test_empty_log_verifies_valid(db):
    log = _log(db)
    result = evidence.verify_chain(db, log)
    assert result.valid is True
    assert result.record_count == 0


def test_tampered_payload_breaks_chain(db):
    log = _log(db)
    evidence.append_record(db, log, evidence.RecordType.GEOFENCE, {"event": "ENTER"}, T0)
    r1 = evidence.append_record(
        db, log, evidence.RecordType.GEOFENCE, {"event": "EXIT"}, T0 + timedelta(hours=3)
    )
    r1.payload = {"event": "EXIT", "forged_minutes": 0}
    db.flush()

    result = evidence.verify_chain(db, log)
    assert result.valid is False
    assert result.reason == "tampered"
    assert result.broken_at == 1


def test_seq_gap_breaks_chain(db):
    log = _log(db)
    evidence.append_record(db, log, evidence.RecordType.SYSTEM, {"i": 0}, T0)
    r1 = evidence.append_record(
        db, log, evidence.RecordType.SYSTEM, {"i": 1}, T0 + timedelta(minutes=1)
    )
    r1.seq = 2
    db.flush()

    result = evidence.verify_chain(db, log)
    assert result.valid is False
    assert result.reason == "seq_gap"


def test_attach_artifact_binds_content_hash_into_chain(db):
    log = _log(db)
    photo_bytes = b"\xff\xd8\xff\xe0 fake jpeg bytes"
    artifact = evidence.attach_artifact(
        db,
        log,
        evidence.ArtifactType.photo,
        content=photo_bytes,
        exif={"Make": "Samsung", "DateTimeOriginal": "2026:07:20 12:00:00"},
        gps_lat=32.7767,
        gps_lon=-96.7970,
        captured_at=T0,
        storage_key="s3://evidence/photo1.jpg",
    )
    assert artifact.content_hash == hashlib.sha256(photo_bytes).hexdigest()
    assert artifact.exif["Make"] == "Samsung"
    assert artifact.gps_lat == 32.7767

    result = evidence.verify_chain(db, log)
    assert result.valid is True
    assert result.record_count == 1


def test_attach_artifact_requires_content_or_hash(db):
    log = _log(db)
    with pytest.raises(ValueError):
        evidence.attach_artifact(db, log, evidence.ArtifactType.document)


def test_compose_pack_structure_and_verification(db):
    log = _log(db)
    evidence.append_record(db, log, evidence.RecordType.GEOFENCE, {"event": "ENTER"}, T0)
    evidence.attach_artifact(
        db,
        log,
        evidence.ArtifactType.photo,
        content=b"bol-scan",
        captured_at=T0 + timedelta(minutes=2),
    )
    evidence.append_record(
        db, log, evidence.RecordType.GEOFENCE, {"event": "EXIT"}, T0 + timedelta(hours=3)
    )

    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)
    assert pack.template == evidence.PackTemplate.detention_claim
    assert [row["seq"] for row in pack.timeline] == [0, 1, 2]
    assert len(pack.artifacts) == 1
    assert pack.verification["chain_valid"] is True
    assert pack.verification["record_count"] == 3
    assert pack.verification["anchored"] is False


def test_compose_pack_reflects_tampering(db):
    log = _log(db)
    evidence.append_record(db, log, evidence.RecordType.GEOFENCE, {"event": "ENTER"}, T0)
    r1 = evidence.append_record(db, log, evidence.RecordType.SYSTEM, {"k": "v"}, T0)
    r1.payload = {"k": "tampered"}
    db.flush()

    pack = evidence.compose_pack(db, log, evidence.PackTemplate.on_time_proof)
    assert pack.verification["chain_valid"] is False
    assert pack.verification["reason"] == "tampered"


def test_anchor_chain_records_head_and_shows_in_pack(db):
    log = _log(db)
    evidence.append_record(db, log, evidence.RecordType.GEOFENCE, {"event": "ENTER"}, T0)
    head = evidence.append_record(
        db, log, evidence.RecordType.GEOFENCE, {"event": "EXIT"}, T0 + timedelta(hours=2)
    )
    anchor = evidence.anchor_chain(db, log, external_ref="tsa-receipt-abc123")
    assert anchor.head_seq == head.seq
    assert anchor.head_hash == head.record_hash

    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)
    assert pack.verification["anchored"] is True
    assert pack.verification["anchor_ref"] == "tsa-receipt-abc123"


def test_anchor_empty_log_raises(db):
    log = _log(db)
    with pytest.raises(ValueError):
        evidence.anchor_chain(db, log)


def test_pdf_render_is_no_longer_a_seam(db):
    """This test used to assert the OPPOSITE — that rendering raised
    `RenderNotEnabled` — which is how a seam quietly becomes permanent. PRD §7.16(b)
    has always required the Foundation e2e to produce an evidence pack PDF; the
    renderer now exists, so the test that documented its absence is inverted rather
    than deleted, leaving the record of what changed. Anatomy is covered in
    `test_render.py`."""
    log = _log(db)
    evidence.append_record(db, log, evidence.RecordType.SYSTEM, {"i": 0}, T0)
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.cargo_condition)
    assert evidence.render_pack_pdf(pack)[:5] == b"%PDF-"
