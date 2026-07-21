"""AI-CONTEXT: F14 Admin Console HTTP endpoints — the platform operator surface,
gated to `platform_admin` accounts. Composes F13 (feature flags + gates) + F14
(admin views, moderation, analytics) + F1 (the role check). Backs the web-first
admin portal (design-prd §18), not the driver app. Read-only where it can be;
the only mutations are flag toggles and moderation decisions.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f13_flags import public as flags
from app.foundation.f14_admin import public as admin

router = APIRouter(prefix="/admin", tags=["admin"])


def current_admin(account: identity.Account = Depends(current_account)) -> identity.Account:
    if not any(r.role == identity.Role.platform_admin for r in account.roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "platform admin only")
    return account


class DecideIn(BaseModel):
    approve: bool
    reason: str | None = None


class ConfigIn(BaseModel):
    key: str
    value: object
    scope: str = "global"


# AI-CONTEXT: the North Star funnel (PRD §1) — the detention value loop, from a
# live load to a filed GPS-backed claim. Steps are analytics event names emitted
# in app/api/load.py; the console renders per-step counts + conversion. Labels are
# i18n'd on the frontend, so only the event keys cross the wire.
_FUNNEL_STEPS = ["load_added", "arrived", "claim_sent"]
_FUNNEL_MODULE = "m03"


@router.get("/flags")
def list_flags(
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(select(flags.FeatureFlag).order_by(flags.FeatureFlag.key))
    return [
        {
            "key": f.key,
            "description": f.description,
            "enabled": f.enabled,
            "kill_switch": f.kill_switch,
            "can_activate": flags.can_activate(db, f.key),
            "gates": [{"name": g.name, "satisfied": g.satisfied} for g in f.gates],
        }
        for f in rows
    ]


@router.post("/flags/{key}/enable")
def enable_flag(
    key: str,
    account: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        flags.enable(db, key)
    except flags.FlagNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "flag not found") from exc
    except flags.GateNotSatisfied as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "activation gates not satisfied") from exc
    admin.record_action(
        db, "flag_enable", actor_account_id=account.id, target_kind="flag", detail={"key": key}
    )
    return {"key": key, "enabled": flags.is_enabled(db, key)}


@router.post("/flags/{key}/disable")
def disable_flag(
    key: str,
    account: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        flags.disable(db, key)
    except flags.FlagNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "flag not found") from exc
    admin.record_action(
        db, "flag_disable", actor_account_id=account.id, target_kind="flag", detail={"key": key}
    )
    return {"key": key, "enabled": flags.is_enabled(db, key)}


@router.get("/views")
def admin_views(
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {"key": v.key, "module": v.module, "title": v.title, "path": v.path}
        for v in admin.list_admin_views(db)
    ]


@router.get("/moderation")
def moderation_queue(
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {
            "id": str(i.id),
            "content_kind": i.content_kind,
            "content_ref": str(i.content_ref),
            "status": i.status.value,
        }
        for i in admin.list_pending_moderation(db)
    ]


@router.get("/analytics")
def analytics(
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    counts = admin.funnel(db, _FUNNEL_STEPS, module=_FUNNEL_MODULE)
    return {
        "funnel": {
            "module": _FUNNEL_MODULE,
            "steps": [
                {"event": step, "count": count}
                for step, count in zip(_FUNNEL_STEPS, counts, strict=True)
            ],
        },
        "totals": {
            "map_open": admin.count_events(db, "map_open"),
            "load_added": admin.count_events(db, "load_added"),
            "claim_sent": admin.count_events(db, "claim_sent"),
        },
    }


@router.get("/config")
def get_config(
    scope: str = "global",
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    return {"scope": scope, "entries": flags.get_scope(db, scope)}


@router.post("/config")
def set_config(
    body: ConfigIn,
    account: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    entry = flags.set_config(db, body.key, body.value, scope=body.scope)
    # F14 audit log: every config mutation is attributed (who set what, when)
    admin.record_action(
        db,
        "config_set",
        actor_account_id=account.id,
        target_kind="config",
        detail={"key": body.key, "scope": body.scope, "value": body.value},
    )
    return {"key": entry.key, "scope": entry.scope, "value": entry.value}


@router.get("/audit")
def audit_log(
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    # every operator mutation (flag toggle, config edit) is an F14 AdminAction;
    # newest first, actor resolved to an email (batched — no N+1 per row)
    actions = list(reversed(admin.list_actions(db)))
    actor_ids = {a.actor_account_id for a in actions if a.actor_account_id}
    emails = {aid: acct.email for aid in actor_ids if (acct := db.get(identity.Account, aid))}
    return [
        {
            "id": str(a.id),
            "action": a.action,
            "actor": emails.get(a.actor_account_id),
            "target_kind": a.target_kind,
            "detail": a.detail,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in actions
    ]


@router.post("/moderation/{item_id}/decide")
def decide(
    item_id: uuid.UUID,
    body: DecideIn,
    account: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    item = db.get(admin.ModerationItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "moderation item not found")
    decision = admin.ModerationStatus.approved if body.approve else admin.ModerationStatus.rejected
    admin.decide_moderation(db, item, decision, moderator_account_id=account.id, reason=body.reason)
    return {"id": str(item.id), "status": item.status.value}
