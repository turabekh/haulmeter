from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import hashing
from .enums import ArtifactType, PackTemplate, RecordType
from .models import ChainAnchor, EvidenceArtifact, EvidenceLog, EvidenceRecord


class RenderNotEnabled(Exception):
    pass


@dataclass
class ChainVerification:
    valid: bool
    record_count: int
    head_seq: int | None = None
    head_hash: str | None = None
    broken_at: int | None = None
    reason: str | None = None


@dataclass
class EvidencePack:
    template: PackTemplate
    log_id: Any
    label: str | None
    timeline: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    verification: dict = field(default_factory=dict)


def create_log(db: Session, account_id, stop_ref=None, label: str | None = None) -> EvidenceLog:
    log = EvidenceLog(account_id=account_id, stop_ref=stop_ref, label=label)
    db.add(log)
    db.flush()
    return log


def _last_record(db: Session, log_id) -> EvidenceRecord | None:
    return db.scalar(
        select(EvidenceRecord)
        .where(EvidenceRecord.log_id == log_id)
        .order_by(EvidenceRecord.seq.desc())
        .limit(1)
    )


def append_record(
    db: Session,
    log: EvidenceLog,
    record_type: RecordType,
    payload: dict,
    occurred_at: datetime | None = None,
) -> EvidenceRecord:
    occurred_at = occurred_at or datetime.now(UTC)
    last = _last_record(db, log.id)
    if last is None:
        seq = 0
        prev = hashing.genesis_hash(log.id)
    else:
        seq = last.seq + 1
        prev = last.record_hash
    record_hash = hashing.compute_record_hash(
        prev, seq, record_type.value, payload, occurred_at
    )
    record = EvidenceRecord(
        log_id=log.id,
        seq=seq,
        record_type=record_type,
        payload=payload,
        occurred_at=occurred_at,
        prev_hash=prev,
        record_hash=record_hash,
    )
    db.add(record)
    db.flush()
    return record


def attach_artifact(
    db: Session,
    log: EvidenceLog,
    artifact_type: ArtifactType,
    content: bytes | None = None,
    content_hash: str | None = None,
    exif: dict | None = None,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    captured_at: datetime | None = None,
    storage_key: str | None = None,
) -> EvidenceArtifact:
    if content is not None:
        content_hash = hashing.content_hash(content)
    if content_hash is None:
        raise ValueError("attach_artifact requires content bytes or a precomputed content_hash")

    record_type = RecordType.PHOTO if artifact_type == ArtifactType.photo else RecordType.DOCUMENT
    payload = {
        "artifact_type": artifact_type.value,
        "content_hash": content_hash,
        "storage_key": storage_key,
        "gps": [gps_lat, gps_lon] if gps_lat is not None else None,
    }
    record = append_record(db, log, record_type, payload, captured_at)
    artifact = EvidenceArtifact(
        log_id=log.id,
        record_id=record.id,
        artifact_type=artifact_type,
        storage_key=storage_key,
        content_hash=content_hash,
        exif=exif or {},
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        captured_at=captured_at,
    )
    db.add(artifact)
    db.flush()
    return artifact


def _ordered_records(db: Session, log_id) -> list[EvidenceRecord]:
    return list(
        db.scalars(
            select(EvidenceRecord)
            .where(EvidenceRecord.log_id == log_id)
            .order_by(EvidenceRecord.seq)
        )
    )


def verify_chain(db: Session, log: EvidenceLog) -> ChainVerification:
    records = _ordered_records(db, log.id)
    if not records:
        return ChainVerification(valid=True, record_count=0)

    expected_prev = hashing.genesis_hash(log.id)
    for index, record in enumerate(records):
        if record.seq != index:
            return ChainVerification(
                valid=False, record_count=len(records), broken_at=record.seq, reason="seq_gap"
            )
        if record.prev_hash != expected_prev:
            return ChainVerification(
                valid=False, record_count=len(records), broken_at=record.seq, reason="broken_link"
            )
        recomputed = hashing.compute_record_hash(
            record.prev_hash,
            record.seq,
            record.record_type.value,
            record.payload,
            record.occurred_at,
        )
        if recomputed != record.record_hash:
            return ChainVerification(
                valid=False, record_count=len(records), broken_at=record.seq, reason="tampered"
            )
        expected_prev = record.record_hash

    head = records[-1]
    return ChainVerification(
        valid=True,
        record_count=len(records),
        head_seq=head.seq,
        head_hash=head.record_hash,
    )


def anchor_chain(db: Session, log: EvidenceLog, external_ref: str | None = None) -> ChainAnchor:
    head = _last_record(db, log.id)
    if head is None:
        raise ValueError("cannot anchor an empty evidence log")
    anchor = ChainAnchor(
        log_id=log.id,
        head_seq=head.seq,
        head_hash=head.record_hash,
        external_ref=external_ref,
    )
    db.add(anchor)
    db.flush()
    return anchor


def _latest_anchor(db: Session, log_id) -> ChainAnchor | None:
    return db.scalar(
        select(ChainAnchor)
        .where(ChainAnchor.log_id == log_id)
        .order_by(ChainAnchor.anchored_at.desc())
        .limit(1)
    )


def compose_pack(db: Session, log: EvidenceLog, template: PackTemplate) -> EvidencePack:
    verification = verify_chain(db, log)
    records = _ordered_records(db, log.id)
    artifacts = list(
        db.scalars(
            select(EvidenceArtifact)
            .where(EvidenceArtifact.log_id == log.id)
            .order_by(EvidenceArtifact.received_at)
        )
    )
    anchor = _latest_anchor(db, log.id)

    return EvidencePack(
        template=template,
        log_id=log.id,
        label=log.label,
        timeline=[
            {
                "seq": r.seq,
                "type": r.record_type.value,
                "occurred_at": r.occurred_at,
                "payload": r.payload,
                "record_hash": r.record_hash,
            }
            for r in records
        ],
        artifacts=[
            {
                "artifact_type": a.artifact_type.value,
                "content_hash": a.content_hash,
                "storage_key": a.storage_key,
                "gps": [a.gps_lat, a.gps_lon] if a.gps_lat is not None else None,
                "captured_at": a.captured_at,
            }
            for a in artifacts
        ],
        verification={
            "chain_valid": verification.valid,
            "record_count": verification.record_count,
            "head_seq": verification.head_seq,
            "head_hash": verification.head_hash,
            "broken_at": verification.broken_at,
            "reason": verification.reason,
            "anchored": anchor is not None,
            "anchor_ref": anchor.external_ref if anchor is not None else None,
        },
    )


def render_pack_pdf(pack: EvidencePack) -> bytes:
    raise RenderNotEnabled(
        "PDF rendering is a seam: token-styled composer templates (design-prd §17) "
        "land with the F4 template set. compose_pack() provides the verified structure."
    )
