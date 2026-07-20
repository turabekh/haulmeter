"""AI-CONTEXT: Hash-chain primitives for the Evidence Engine (F4, PRD §7.4).

Each record's hash includes the previous record's hash, making any later
tampering evident: mutate a payload, a timestamp, a seq, or a link and the
recomputation no longer matches. Serialization is canonical (sorted keys,
UTC-normalized timestamps) so verification is deterministic across DB
round-trips. Chain heads are periodically anchored to an external
timestamping service (adapter seam) — that binds the chain to wall-clock time
a third party attests, but the intra-chain integrity here stands on its own.
"""
import hashlib
import json
from datetime import UTC, datetime


def _as_utc_iso(value: datetime) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat()


def _canonical(material: dict) -> bytes:
    return json.dumps(material, sort_keys=True, separators=(",", ":"), default=str).encode()


def genesis_hash(log_id) -> str:
    return hashlib.sha256(f"longhaul-evidence:{log_id}".encode()).hexdigest()


def compute_record_hash(
    prev_hash: str,
    seq: int,
    record_type: str,
    payload: dict,
    occurred_at: datetime,
) -> str:
    material = {
        "prev": prev_hash,
        "seq": seq,
        "type": record_type,
        "payload": payload,
        "occurred_at": _as_utc_iso(occurred_at),
    }
    return hashlib.sha256(_canonical(material)).hexdigest()


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
