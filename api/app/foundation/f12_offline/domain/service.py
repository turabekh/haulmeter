"""AI-CONTEXT: F12 Offline Sync & Outbox (PRD §7.12) — server side.

Trucking's default network condition is "none". Every capture is written to a
local client outbox first and synced later with an idempotency key. This is the
generic **idempotent ingest** primitive the whole platform routes through: the
same (account, idempotency_key) applied twice yields exactly one effect. Server
time is authoritative (`received_at`); the client's skew-corrected `occurred_at`
is preserved. The `handler` runs only on first apply, never on a duplicate —
that is what makes sync at-least-once delivery safe. Read-side offline caches
(last map region, active load, document wallet) are a client concern.
"""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import SyncEnvelope


@dataclass
class SyncReceipt:
    envelope: SyncEnvelope
    applied: bool  # True = newly applied this call; False = duplicate (no re-apply)


def get_receipt(db: Session, account_id, idempotency_key: str) -> SyncEnvelope | None:
    return db.scalar(
        select(SyncEnvelope).where(
            SyncEnvelope.account_id == account_id,
            SyncEnvelope.idempotency_key == idempotency_key,
        )
    )


def ingest(
    db: Session,
    account_id,
    idempotency_key: str,
    kind: str,
    payload: dict,
    occurred_at: datetime,
    client_skew_ms: int | None = None,
    handler: Callable[[SyncEnvelope], None] | None = None,
) -> SyncReceipt:
    existing = get_receipt(db, account_id, idempotency_key)
    if existing is not None:
        return SyncReceipt(envelope=existing, applied=False)

    envelope = SyncEnvelope(
        account_id=account_id,
        idempotency_key=idempotency_key,
        kind=kind,
        payload=payload,
        occurred_at=occurred_at,
        client_skew_ms=client_skew_ms,
    )
    db.add(envelope)
    db.flush()
    if handler is not None:
        handler(envelope)
    return SyncReceipt(envelope=envelope, applied=True)


def list_for_account(db: Session, account_id, kind: str | None = None) -> list[SyncEnvelope]:
    stmt = select(SyncEnvelope).where(SyncEnvelope.account_id == account_id)
    if kind is not None:
        stmt = stmt.where(SyncEnvelope.kind == kind)
    return list(db.scalars(stmt.order_by(SyncEnvelope.received_at)))
