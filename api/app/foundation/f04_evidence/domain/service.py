from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import hashing
from .enums import ArtifactType, PackTemplate, RecordType
from .models import ChainAnchor, EvidenceArtifact, EvidenceLog, EvidenceRecord


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
    record_hash = hashing.compute_record_hash(prev, seq, record_type.value, payload, occurred_at)
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
    # the capture PROMPT is what a guided sequence is for. It lived only in the
    # artifact's exif, so a rendered condition report read "Photo · Photo · Photo"
    # and a clerk could not tell whether the seals had been photographed at all.
    # It belongs in the chained record: the prompt is a claim about what the image
    # shows, and a claim about evidence should be hashed with it.
    if (exif or {}).get("prompt"):
        payload["prompt"] = exif["prompt"]
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


def stop_evidence(db: Session, stop_ref) -> dict:
    # aggregate EVERY evidence log tied to a stop (arrival, condition capture,
    # etc.) into one chronological view — the driver's "what have I got" for a load
    logs = list(db.scalars(select(EvidenceLog).where(EvidenceLog.stop_ref == stop_ref)))
    timeline: list[dict] = []
    photos: list[dict] = []
    all_valid = True
    for log in logs:
        if not verify_chain(db, log).valid:
            all_valid = False
        for record in _ordered_records(db, log.id):
            timeline.append(
                {
                    "type": record.record_type.value,
                    "occurred_at": record.occurred_at,
                    "log": log.label,
                }
            )
        for artifact in db.scalars(
            select(EvidenceArtifact).where(EvidenceArtifact.log_id == log.id)
        ):
            if artifact.artifact_type == ArtifactType.photo:
                photos.append(
                    {
                        "artifact_id": artifact.id,
                        "prompt": (artifact.exif or {}).get("prompt"),
                        "content_hash": artifact.content_hash,
                        "captured_at": artifact.captured_at or artifact.received_at,
                        "has_image": bool(artifact.storage_key),
                    }
                )
    timeline.sort(key=lambda t: t["occurred_at"] or datetime(1970, 1, 1, tzinfo=UTC))
    photos.sort(key=lambda p: p["captured_at"] or datetime(1970, 1, 1, tzinfo=UTC))
    return {
        "chain_valid": all_valid,
        "record_count": len(timeline),
        "photo_count": len(photos),
        "timeline": [
            {
                "type": t["type"],
                "occurred_at": t["occurred_at"].isoformat() if t["occurred_at"] else None,
            }
            for t in timeline
        ],
        "photos": [
            {
                "artifact_id": str(p["artifact_id"]),
                "prompt": p["prompt"],
                "content_hash": p["content_hash"][:12] if p["content_hash"] else None,
                "captured_at": p["captured_at"].isoformat() if p["captured_at"] else None,
                "has_image": p["has_image"],
            }
            for p in photos
        ],
    }


def get_artifact(db: Session, artifact_id) -> EvidenceArtifact | None:
    return db.get(EvidenceArtifact, artifact_id)


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
                # F12 records BOTH: `occurred_at` is the client's skew-corrected
                # time, `received_at` is when the server actually saw it. The pack
                # carried only the first, which threw the divergence away at the
                # composition boundary — and the divergence is the whole point of
                # recording two clocks (PRD §7.12).
                "received_at": r.received_at,
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


def render_pack_pdf(pack: EvidencePack, context=None) -> bytes:
    """The §17 artifact. `compose_pack` supplies the verified structure; this turns
    it into the thing a broker's AP clerk actually reads. `context` carries what F4
    cannot know — the parties, the references and the Meter figure — because the
    money is M3's arithmetic and the counterparties are F5's records."""
    from .render import render

    return render(pack, context)
