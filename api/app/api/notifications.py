"""AI-CONTEXT: the driver's notification inbox — F8's first delivery path.

F8 has decided tiers, budgets, quiet hours and classes since it shipped, and until now
every decision it made ended in a row nobody could read. There was **no notification
endpoint in the schema at all**, no service worker or push registration in the client,
and the only gateway wired in application code is the RECORDING one used by tests.
§23 entry 429 caught the miniature of this — "nothing may be filed P2 until a surface
renders the digest" — and the general case was larger: nothing rendered any of it.

This is the pull half, and it is deliberately the half built first. A pull inbox needs
no credentials, no background permission and no provider, so it makes the §13
machinery real today rather than after an FCM account exists. The PUSH half stays the
seam it already is (`gateway.py`); §13's unprompted delivery to a phone in a pocket is
push and cannot be anything else — an open socket reaches only an app the driver is
already looking at.

The budget is NOT applied here. §13.1 caps unprompted INTERRUPTIONS at two a day; a
driver who opens a list is asking, not being interrupted, so the inbox shows what the
quiet-hours and budget rules suppressed as well. Deferring a notification is
considerate; destroying it is lossy, and the two must not be confused.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _serialize(n) -> dict:
    return {
        "id": str(n.id),
        "tier": n.tier.value,
        "category": n.category,
        "title": n.title,
        "body": n.body,
        # §13.5: every notification deep-links to the exact screen and state it
        # describes. It is carried to the client rather than re-derived there, so one
        # definition of "where this is about" serves push and inbox alike.
        "deep_link": n.deep_link,
        "status": n.status.value,
        "channel": n.channel.value if n.channel else None,
        # why the driver did NOT get interrupted, when that is the case. §11.7's
        # honesty rule applied to our own machinery: "we held this until morning" and
        # "we sent this" are different facts and the surface may need to say which.
        "suppressed_reason": n.suppress_reason.value if n.suppress_reason else None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "read_at": n.read_at.isoformat() if n.read_at else None,
    }


@router.get("")
def list_notifications(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    rows = notify.inbox(db, account.id)
    return {
        "notifications": [_serialize(n) for n in rows],
        "unread": len([n for n in rows if n.read_at is None]),
    }


@router.post("/{notification_id}/read", status_code=200)
def mark_read(
    notification_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    notification = notify.get_notification(db, notification_id)
    # a notification addressed to someone else is NOT FOUND rather than forbidden:
    # confirming that an id exists would leak that another driver was told something
    if notification is None or notification.account_id != account.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "notification not found")
    notify.mark_notification_read(db, notification)
    return _serialize(notification)
