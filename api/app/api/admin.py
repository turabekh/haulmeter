"""AI-CONTEXT: F14 Admin Console HTTP endpoints — the platform operator surface,
gated to `platform_admin` accounts. Composes F13 (feature flags + gates) + F14
(admin views, moderation, analytics) + F1 (the role check). Backs the web-first
admin portal (design-prd §18), not the driver app. Read-only where it can be;
the only mutations are flag toggles and moderation decisions.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f13_flags import public as flags
from app.foundation.f14_admin import public as admin
from app.modules.m13_vendor import public as m13

router = APIRouter(prefix="/admin", tags=["admin"])


def current_admin(account: identity.Account = Depends(current_account)) -> identity.Account:
    if not any(r.role == identity.Role.platform_admin for r in account.roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "platform admin only")
    return account


class DecideIn(BaseModel):
    approve: bool
    reason: str | None = None


class VendorDecisionIn(BaseModel):
    verify_status: str | None = None
    suspended: bool | None = None


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
    # Q-8: the 72h promise is only real if a moderator can SEE what is late, so age
    # and the overdue flag ride on every row, oldest first.
    return [
        {
            "id": str(q.item.id),
            "content_kind": q.item.content_kind,
            "content_ref": str(q.item.content_ref),
            "status": q.item.status.value,
            "age_hours": q.age_hours,
            "overdue": q.overdue,
            "sla_hours": admin.MODERATION_SLA_HOURS,
            "reports": m13.distinct_reporters(db, q.item.content_kind, q.item.content_ref),
        }
        for q in m13.queue_with_sla(db)
    ]


@router.post("/moderation/report/{content_kind}/{content_ref}/resolve")
def resolve_report(
    content_kind: str,
    content_ref: uuid.UUID,
    body: DecideIn,
    account: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    # `approve` here means the REPORT was upheld: the content stays down. Naming it
    # that way keeps one verb across the whole moderation surface.
    result = m13.resolve_report(
        db,
        content_kind,
        content_ref,
        uphold=body.approve,
        moderator_account_id=account.id,
        reason=body.reason,
    )
    admin.record_action(
        db,
        "report_resolve",
        actor_account_id=account.id,
        target_kind=content_kind,
        detail={"content_ref": str(content_ref), "upheld": body.approve},
    )
    return result


@router.get("/moderation/overdue")
def overdue_queue(
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    items = admin.overdue_moderation(db, datetime.now(UTC))
    return [
        {"id": str(i.id), "content_kind": i.content_kind, "content_ref": str(i.content_ref)}
        for i in items
    ]


@router.post("/claims/{claim_id}/decide")
def decide_claim(
    claim_id: uuid.UUID,
    body: DecideIn,
    account: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    claim = db.get(m13.FacilityClaim, claim_id)
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "claim not found")
    try:
        m13.decide_claim(
            db, claim, body.approve, moderator_account_id=account.id, reason=body.reason
        )
    except m13.AlreadyClaimed as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"error": "already_claimed", "claim_id": str(exc.claim.id)},
        ) from exc
    return {"claim_id": str(claim.id), "status": claim.status.value}


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


# --- M13 vendor moderation (the Session-A vendor management surface) ---
@router.get("/vendors")
def vendor_list(
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    # AI-CONTEXT: vendor management is API + this console only until the vendor
    # portal lands in Session B. The operator needs exactly three facts to act:
    # who they are, where they stand on the ladder, and whether the no-show
    # counter has suspended their publishing (Q-2).
    rows = db.scalars(select(m13.Vendor).order_by(m13.Vendor.created_at.desc()))
    out = []
    for vendor in rows:
        score = m13.reliability(db, vendor.id)
        out.append(
            {
                "vendor_id": str(vendor.id),
                "name": vendor.name,
                "vendor_type": vendor.vendor_type.value,
                "metro": vendor.metro,
                "verify_status": vendor.verify_status.value,
                "status": vendor.status.value,
                "publish_suspended": vendor.publish_suspended,
                "consecutive_no_shows": vendor.consecutive_no_shows,
                "shows_up": {"confirmed": score.confirmed, "published": score.published},
                "is_dev": vendor.is_dev,
                "documents": [
                    {"kind": d.doc_kind.value, "review_status": d.review_status.value}
                    for d in vendor.documents
                ],
            }
        )
    return out


@router.post("/vendors/{vendor_id}/decide")
def decide_vendor(
    vendor_id: uuid.UUID,
    body: VendorDecisionIn,
    account: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    vendor = m13.resolve_vendor(db, vendor_id)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    if body.verify_status is not None:
        try:
            m13.set_verification(
                db,
                vendor,
                m13.VendorVerifyStatus(body.verify_status),
                moderator_account_id=account.id,
            )
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown verify status"
            ) from exc
    if body.suspended is not None:
        m13.suspend_vendor(db, vendor, body.suspended, moderator_account_id=account.id)
    return {
        "vendor_id": str(vendor.id),
        "verify_status": vendor.verify_status.value,
        "status": vendor.status.value,
        "publish_suspended": vendor.publish_suspended,
    }
