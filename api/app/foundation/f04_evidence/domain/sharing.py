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

# AI-CONTEXT: how long a shared pack stays reachable, and why 90 was not enough.
#
# Measured against what actually happens to a claim: M3's own dunning runs day 3,
# day 10, day 21 — and day 21 is only the ESCALATION OFFER, after which M3-FR7 hands
# the claim to a licensed collection partner. PRD §8.3 prices partner work at
# "25–30% … higher for aged/complex accounts", so the business model itself assumes
# escalated claims run long. A link dying at 90 days can therefore expire in the
# middle of partner collection — and when it does, the counterparty's copy of the
# evidence evaporates and the driver looks like they withdrew it.
#
# So the default covers a realistic dispute rather than an AP cycle, and the driver
# can EXTEND. Extension is deliberately the driver's act, not an automatic one: F4 is
# foundation and cannot ask M3 whether a claim is still live, and a seam built for a
# caller that does not exist yet is the bug class this project keeps producing.
CONFIG_SHARE_DAYS = "f04_share_link_days"
DEFAULT_SHARE_DAYS = 365


class ShareNotFound(Exception):
    """Unknown, revoked or expired — deliberately ONE exception. A caller must not
    be able to distinguish "never existed" from "revoked" by probing tokens."""


def _share_days(db: Session) -> int:
    return int(flags.get_config(db, CONFIG_SHARE_DAYS, DEFAULT_SHARE_DAYS))


# AI-CONTEXT: ONE definition of "where does a counterparty open this pack".
#
# F4 issues the token, so F4 answers where it lives. M3's detention notice needed it
# first and A1's Stop Packet needs the identical thing, with M5's on-time proof a third
# caller waiting. Three modules building the same URL from the same token is the shape of
# §23 entry 94's regression, and this session found nine mechanisms fixed in one place
# and not the others before writing this line.
#
# Returns None rather than a half-formed URL. A deployment with no PUBLIC_BASE_URL cannot
# address itself, and a broken link in an email to a broker is worse than an honest
# sentence saying the evidence is available on request (§12.4). The caller writes the
# sentence, because only the caller knows the document.
def share_link(shared) -> str | None:
    from app.core.config import get_settings

    base = (get_settings().public_base_url or "").rstrip("/")
    return f"{base}/pack/s/{shared.token}" if base else None


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


def extend_share(db: Session, shared: SharedPack, days: int | None = None, now=None) -> SharedPack:
    """Push the expiry out from NOW, not from the old date — a driver extending a link
    that lapsed yesterday means "keep it alive", and counting from a date already past
    would grant less time than they asked for.

    It also never SHORTENS, which a first draft of this did: with the default at a
    year, `extend(days=180)` moved the expiry closer and a test caught it. A function
    called extend that can cut a link short is a trap for its next caller, so the
    later of the two dates wins.

    Revoked links stay revoked: extending is about time, revocation was about intent,
    and one must not quietly undo the other."""
    now = now or datetime.now(UTC)
    if shared.revoked_at is not None:
        return shared
    proposed = now + timedelta(days=days or _share_days(db))
    current = shared.expires_at
    if current is not None and current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    shared.expires_at = proposed if current is None or proposed > current else current
    db.flush()
    return shared


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
