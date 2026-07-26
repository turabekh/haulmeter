"""AI-CONTEXT: F4 pack sharing — "persist on share", and why that is a record.

Rendering is deterministic, so regenerating on demand is free and always current.
Sharing is a different act, and the difference is the whole design: **a pack shared
at 14:00 and regenerated at 16:00 after another photo lands is a different
document.** In a dispute the question is never "what does the pack say now" — it is
"what did we send them." So a share pins the exact bytes, hashes them, stores them,
and writes that hash into the chain. This is a record of an act, not a cache.

Three consequences follow, and each is deliberate:

· **The link serves the PINNED bytes, never a fresh render.** If it re-rendered, a
  counterparty refreshing an old link would silently see a document that had grown
  new evidence since they were sent it, and neither party could say which one the
  argument was about.
· **The token is opaque and random, not signed.** A signed token would be stateless,
  but revocation then needs a denylist — and we are storing a row anyway for the
  hash and the storage key, so a lookup costs nothing and revocation is one column.
  No signing secret to manage, which also keeps `.env` honest.
· **The first open is written into the chain.** "They opened it on the 12th" is
  itself evidence in a dispute. Only the FIRST: a clerk refreshing four times is not
  four facts, and an append-only log should not carry noise.

The chain grows after a share — which is exactly why the share was pinned.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f06_documents import public as documents
from app.foundation.f13_flags import public as flags

from .enums import RecordType
from .models import EvidenceLog, SharedPack

# A broker's AP cycle runs 30–60 days and a dispute can outlive it, so a link that
# dies at 30 would expire at exactly the wrong moment. 90 is F13-tunable.
CONFIG_SHARE_DAYS = "f04_share_link_days"
DEFAULT_SHARE_DAYS = 90


class ShareNotFound(Exception):
    """Unknown, revoked or expired — deliberately ONE exception. A caller must not
    be able to distinguish "never existed" from "revoked" by probing tokens."""


def _share_days(db: Session) -> int:
    return int(flags.get_config(db, CONFIG_SHARE_DAYS, DEFAULT_SHARE_DAYS))


def share_pack(
    db: Session,
    log: EvidenceLog,
    template,
    content: bytes,
    shared_by,
    recipient: str | None = None,
    now: datetime | None = None,
    storage=None,
) -> SharedPack:
    """Pin these bytes and hand back the record. The caller renders — F4 does not
    decide what a pack should contain — and this fixes what was sent."""
    now = now or datetime.now(UTC)
    storage = storage or documents.default_storage()
    content_hash = hashlib.sha256(content).hexdigest()
    key = f"packs/{log.id}/{content_hash}.pdf"
    storage.put(key, content, "application/pdf")

    shared = SharedPack(
        log_id=log.id,
        template=template.value if hasattr(template, "value") else str(template),
        content_hash=content_hash,
        storage_key=key,
        token=secrets.token_urlsafe(32),
        shared_by=shared_by,
        recipient=recipient,
        expires_at=now + timedelta(days=_share_days(db)),
    )
    db.add(shared)
    db.flush()

    # the act of sharing is itself an event in the life of this evidence
    from .service import append_record

    append_record(
        db,
        log,
        RecordType.SYSTEM,
        {
            "event": "pack_shared",
            "content_hash": content_hash,
            "template": shared.template,
            "recipient": recipient,
        },
        occurred_at=now,
    )
    return shared


def resolve_share(db: Session, token: str, now: datetime | None = None) -> SharedPack:
    now = now or datetime.now(UTC)
    shared = db.scalar(select(SharedPack).where(SharedPack.token == token))
    if shared is None or shared.revoked_at is not None:
        raise ShareNotFound(token[:8])
    expires = shared.expires_at
    if expires is not None and (expires if expires.tzinfo else expires.replace(tzinfo=UTC)) < now:
        raise ShareNotFound(token[:8])
    return shared


def open_share(db: Session, token: str, now: datetime | None = None, storage=None) -> bytes:
    """Resolve, record the open, and serve the PINNED bytes."""
    now = now or datetime.now(UTC)
    shared = resolve_share(db, token, now=now)
    storage = storage or documents.default_storage()

    first = shared.opened_count == 0
    shared.opened_count += 1
    shared.last_opened_at = now
    if first:
        shared.first_opened_at = now
        log = db.get(EvidenceLog, shared.log_id)
        if log is not None:
            from .service import append_record

            append_record(
                db,
                log,
                RecordType.SYSTEM,
                {"event": "pack_opened", "content_hash": shared.content_hash},
                occurred_at=now,
            )
    db.flush()
    return storage.get(shared.storage_key)


def revoke_share(db: Session, shared: SharedPack, now: datetime | None = None) -> SharedPack:
    """Closing a link does not unsend the document — a counterparty may already hold
    a copy — so the stored bytes and their hash SURVIVE revocation. What ends is our
    hosting of it, and the record of what was sent stays intact."""
    shared.revoked_at = now or datetime.now(UTC)
    db.flush()
    return shared


def shares_for_log(db: Session, log_id) -> list[SharedPack]:
    return list(
        db.scalars(
            select(SharedPack).where(SharedPack.log_id == log_id).order_by(SharedPack.created_at)
        )
    )
