from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import hashing
from .enums import ArtifactType, PackTemplate, RecordType
from .models import ChainAnchor, EvidenceArtifact, EvidenceLog, EvidenceRecord
from .ordering import timeline_key


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
    """Append to the chain, retrying once if a concurrent append took our seq.

    AI-CONTEXT: finding F4-4. Reading the head and inserting `seq + 1` is check-then-act,
    and `uq_evidence_record_log_seq` is what makes the chain trustworthy under it — the
    loser of a race is REFUSED rather than allowed to fork the chain. That part was right.
    What was missing is the other half: the loser got an unhandled `IntegrityError`, so a
    driver uploading a photo at the moment the worker recorded a departure on the same
    stop's log saw a 500 and lost the upload.

    The constraint stays the invariant; this only recovers from it. One retry, because the
    second attempt reads a head that the winning transaction has already committed — a
    third collision would mean sustained parallel writers on one stop's log, which is not
    a thing this product does, and a loop would hide that if it ever became one.
    """
    occurred_at = occurred_at or datetime.now(UTC)
    for attempt in (1, 2):
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
        try:
            # SAVEPOINT, so a lost race does not poison the caller's transaction — the
            # photo upload this is protecting has already written rows of its own
            with db.begin_nested():
                db.add(record)
                db.flush()
        except IntegrityError:
            if record in db:
                db.expunge(record)
            if attempt == 2:
                raise
            db.expire_all()  # the winner's head is committed; read it, do not reuse ours
            continue
        return record
    raise AssertionError("unreachable")


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
                    # AI-CONTEXT: WHAT happened, not merely that something did
                    # (§23 entry 70). Every record's payload names its event and this
                    # view dropped it, so the timeline could only be labelled by
                    # RecordType — and a driver disputing detention was handed a pack
                    # reading "Event recorded 03:14". The payload itself stays out:
                    # a timeline is a sequence of facts, not a dump of internals.
                    "event": (record.payload or {}).get("event"),
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
                "event": t["event"],
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


def _latest_anchor(db: Session, log_id) -> ChainAnchor | None:
    return db.scalar(
        select(ChainAnchor)
        .where(ChainAnchor.log_id == log_id)
        .order_by(ChainAnchor.anchored_at.desc())
        .limit(1)
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

    # AI-CONTEXT: the chain checks itself against its ANCHORS (finding F4-2).
    #
    # Everything above recomputes hashes from the records, which makes the chain
    # self-consistent — and self-consistency is exactly what a competent rewrite produces.
    # Re-hash a doctored payload, re-link every record after it, and every check above
    # passes. The anchor is the one thing a rewriter cannot fix from inside the table: it
    # was written at a moment in the past and says what the head WAS then.
    #
    # Reported as its own reason rather than folded into `tampered`, because the two mean
    # different things to whoever reads the PDF: `tampered` says a record does not match
    # its own hash; `anchor_mismatch` says the records agree with each other and disagree
    # with what we recorded earlier — which is the signature of a rewrite, not a bit flip.
    #
    # Only the LATEST anchor is checked. An older anchor legitimately describes a shorter
    # chain, and treating a chain that has since grown as a mismatch would fail every log
    # that was anchored and then appended to — which is every log this product makes.
    anchor = _latest_anchor(db, log.id)
    if anchor is not None:
        anchored = next((r for r in records if r.seq == anchor.head_seq), None)
        if anchored is None or anchored.record_hash != anchor.head_hash:
            return ChainVerification(
                valid=False,
                record_count=len(records),
                broken_at=anchor.head_seq,
                reason="anchor_mismatch",
                head_seq=head.seq,
                head_hash=head.record_hash,
            )

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


def compose_grouped_pack(
    db: Session, groups, template: PackTemplate, label: str | None = None
) -> EvidencePack | None:
    """Several stops' records as ONE document, each section labelled (§23 entry 78).

    AI-CONTEXT: entry 71 found that a per-LOG export could only ever show a fragment
    of a stop. This is the same sentence one layer up: a per-STOP export can only show
    a fragment of a ROUTE. A driver who ran a pickup and a delivery and photographed
    both had eight photos in the system and no document that contained more than four
    — and the four they could reach were whichever stop the row happened to link to.

    `groups` is [(label, stop_ref)] and F4 does not know what a label MEANS. "Pickup ·
    Harvest Foods DC" is F5's sentence about F5's objects; this file merges chains and
    refuses to learn what a stop type is.

    Chains are verified per LOG and the pack is valid only if every one of them is:
    merging the views must not merge the guarantees.
    """
    timeline: list[dict] = []
    artifacts: list[dict] = []
    parts: list[dict] = []
    logs: list[EvidenceLog] = []
    all_valid = True
    for order, (group_label, stop_ref) in enumerate(groups):
        for log in db.scalars(select(EvidenceLog).where(EvidenceLog.stop_ref == stop_ref)):
            logs.append(log)
            pack = compose_pack(db, log, template)
            v = pack.verification
            if not v.get("chain_valid", False):
                all_valid = False
            parts.append(v)
            for record in pack.timeline:
                # the section this row belongs to, and its place in the route. A pack
                # sorted by time alone would interleave two docks the moment a driver
                # doubles back, and read as one confused visit.
                timeline.append({**record, "group": group_label, "group_order": order})
            for artifact in pack.artifacts:
                artifacts.append({**artifact, "group": group_label, "group_order": order})
    if not logs:
        return None
    # the server's clock, within each stop's section — see `ordering.timeline_key`
    timeline.sort(key=timeline_key)
    artifacts.sort(
        key=lambda a: (a["group_order"], a.get("received_at") is None, a.get("received_at"))
    )
    first_broken = next((v for v in parts if not v.get("chain_valid", False)), None)
    head = first_broken or parts[0]
    return EvidencePack(
        template=template,
        log_id=logs[0].id,
        # a document about a ROUTE must not be captioned with one stop's log label:
        # "stop-0" in the corner of a load record is a smaller lie than a wrong number
        # and reads the same way — as a document that does not know what it is about
        label=label,
        timeline=timeline,
        artifacts=artifacts,
        verification={
            "chain_valid": all_valid,
            "record_count": len(timeline),
            "head_seq": head.get("head_seq"),
            "head_hash": head.get("head_hash"),
            "broken_at": head.get("broken_at"),
            "reason": head.get("reason"),
            "anchored": any(v.get("anchored") for v in parts),
            "anchor_recorded": any(v.get("anchor_recorded") for v in parts),
            "anchor_ref": next((v.get("anchor_ref") for v in parts if v.get("anchor_ref")), None),
            "log_count": len(logs),
        },
    )


def compose_stop_pack(db: Session, stop_ref, template: PackTemplate) -> EvidencePack | None:
    """Every log tied to a stop, as one document (§23 entry 71).

    AI-CONTEXT: `compose_pack` renders ONE log, and a stop has several — its own
    (arrival, notice, departure), M5's on-time proof, and a log per condition capture.
    The only export a driver could reach composed the condition capture alone, so a
    stop without photos 404'd and the detention argument could not leave the phone.

    Chains are verified per LOG and the pack is valid only if all of them are: merging
    the views must not merge the guarantees, because each chain proves its own records
    and nothing about its neighbours.
    """
    logs = list(db.scalars(select(EvidenceLog).where(EvidenceLog.stop_ref == stop_ref)))
    if not logs:
        return None
    timeline: list[dict] = []
    artifacts: list[dict] = []
    parts: list[dict] = []
    all_valid = True
    for log in logs:
        pack = compose_pack(db, log, template)
        v = pack.verification
        if not v.get("chain_valid", False):
            all_valid = False
        parts.append(v)
        timeline.extend(pack.timeline)
        artifacts.extend(pack.artifacts)
    # the server's clock, and the SAME key the renderer uses — see `ordering.timeline_key`
    timeline.sort(key=timeline_key)
    artifacts.sort(key=lambda a: (a.get("received_at") is None, a.get("received_at")))
    # AI-CONTEXT: the verification block must speak the SAME dict a single-log pack
    # does, or the renderer reads nothing and prints "HASH CHAIN BROKEN — do not rely
    # on this pack" over evidence whose chains are all intact. That is worse than the
    # missing export it replaced: it tells a broker the driver's proof is worthless.
    # Caught by rendering the PDF and looking at it, not by the suite.
    #
    # `head_seq`/`head_hash`/`broken_at` stay per-log and are reported for the FIRST
    # broken chain, or the primary log when all are sound — a merged head hash would
    # be a number that verifies nothing.
    first_broken = next((v for v in parts if not v.get("chain_valid", False)), None)
    head = first_broken or parts[0]
    return EvidencePack(
        template=template,
        log_id=logs[0].id,
        label=logs[0].label,
        timeline=timeline,
        artifacts=artifacts,
        verification={
            "chain_valid": all_valid,
            "record_count": len(timeline),
            "head_seq": head.get("head_seq"),
            "head_hash": head.get("head_hash"),
            "broken_at": head.get("broken_at"),
            "reason": head.get("reason"),
            "anchored": any(v.get("anchored") for v in parts),
            "anchor_recorded": any(v.get("anchor_recorded") for v in parts),
            "anchor_ref": next((v.get("anchor_ref") for v in parts if v.get("anchor_ref")), None),
            "log_count": len(logs),
        },
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
            # AI-CONTEXT: "anchored" means an EXTERNAL party attested the head (F4-2).
            # It used to mean "a row exists in our own table", and the PDF printed
            # "Anchored: yes" for it — a claim of third-party timestamping that nothing
            # outside this database supported. An internal-only anchor is still worth
            # stating, so it is reported separately and rendered as what it is.
            "anchored": anchor is not None and anchor.external_ref is not None,
            "anchor_recorded": anchor is not None,
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
