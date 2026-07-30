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
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.core.config import get_settings
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


# --- Opt-in classes (E-D1, §23 entry 114) ---
#
# AI-CONTEXT: the routes that made an opt-in class reachable at all.
#
# `dispatch` gates on `is_opted_in` BEFORE any tier logic, and an opt-in class defaults
# to off — so a class with no way to switch it on is not "off by default", it is dead.
# `set_class_opt_in` had exactly one caller in the whole tree: the vendor-alerts route,
# hardcoded to VENDOR_ALERT. `lot_status_prompt` therefore suppressed `not_opted_in` for
# every driver, always, while its own tests opted in by calling the service function.
# Third occurrence of that shape in one feature — see
# tests/api/test_prompt_reachability_api.py, which asserts through routes only.
#
# Generic rather than a route per class: NOTIFICATION_CLASSES is already the registry
# and `get_class` is already the validator, so a new class needs no new endpoint. The
# registry is code-defined, so an unknown key is a client bug and gets a 404 rather than
# a preference row that governs nothing.
class ClassOptInIn(BaseModel):
    opted_in: bool


@router.get("/classes")
def list_classes(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """What the driver has chosen, and what the class would do — so a screen can render
    the switch in its real state instead of guessing.

    `opted_in` is `is_opted_in`, which reads the DEFAULT when no row exists. The absence
    of a preference is an answer (silence is never consent), not missing data.
    """
    return {
        "classes": [
            {
                "key": spec.key,
                "opted_in": notify.is_opted_in(db, account.id, spec.key),
                "opt_in_default": spec.opt_in_default,
                "max_per_day": spec.max_per_day,
                "tier": spec.tier.value,
            }
            for spec in notify.NOTIFICATION_CLASSES.values()
        ]
    }


@router.put("/classes/{class_key}/opt-in")
def set_class_opt_in(
    class_key: str,
    body: ClassOptInIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """Turning it on, and off, through the same route — §21.8's symmetry is why this is
    one PUT with a boolean rather than a subscribe/unsubscribe pair."""
    if notify.get_class(class_key) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown notification class")
    pref = notify.set_class_opt_in(db, account.id, class_key, body.opted_in)
    return {"class": class_key, "opted_in": pref.opted_in}


# --- Web Push registration (§13.1, §23 entry 111) ---
class PushSubscriptionIn(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


@router.get("/push/key")
def push_key() -> dict:
    """The VAPID PUBLIC key, which is public by definition — the browser needs it to
    build a subscription, and it identifies this sender to the push service.

    AI-CONTEXT: `enabled` is what the client branches on. An unconfigured deployment
    answers honestly rather than handing back an empty string the browser would fail
    on in a way no one could read (§12.4).
    """
    settings = get_settings()
    return {
        "enabled": bool(settings.vapid_public_key),
        "public_key": settings.vapid_public_key,
    }


@router.post("/push/subscribe", status_code=201)
def push_subscribe(
    body: PushSubscriptionIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """Register this browser for push. Idempotent by endpoint — see `save_subscription`."""
    sub = notify.save_subscription(db, account.id, body.endpoint, body.p256dh, body.auth)
    return {"id": str(sub.id)}


@router.post("/push/unsubscribe", status_code=200)
def push_unsubscribe(
    body: PushSubscriptionIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    """Turning alerts off must be as easy as turning them on (§21.8).

    AI-CONTEXT: answers 200 whether or not a row was there. A driver who has already
    unsubscribed, or whose browser dropped the subscription on its own, asked for a
    state and is now in it — reporting 404 would make an achieved outcome read as a
    failure. The boolean says which happened for anyone who cares.
    """
    removed = notify.drop_subscription_by_endpoint(db, account.id, body.endpoint)
    return {"removed": removed}
