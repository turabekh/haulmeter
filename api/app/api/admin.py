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
from sqlalchemy import func, select
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


class ResolveReportIn(BaseModel):
    # `approve` means the REPORT was upheld — the content stays down. `frivolous` is
    # the third verdict: the report itself was the abuse (Admin Console 2.0 dec. 4c).
    approve: bool
    reason: str | None = None
    frivolous: bool = False


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
    out = []
    for f in rows:
        last = admin.last_action_for(db, "flag_disable", f.key) or admin.last_action_for(
            db, "flag_enable", f.key
        )
        actor = (
            db.get(identity.Account, last.actor_account_id)
            if last and last.actor_account_id
            else None
        )
        out.append(
            {
                "key": f.key,
                "description": f.description,
                "enabled": f.enabled,
                "kill_switch": f.kill_switch,
                "can_activate": flags.can_activate(db, f.key),
                "gates": [{"name": g.name, "satisfied": g.satisfied} for g in f.gates],
                # grouping is server-side so every client groups identically
                "family": _flag_family(f.key),
                # a module flag gates a whole surface; disabling one is the change an
                # operator most needs a confirm step for (decision 3)
                "gates_a_module": _flag_family(f.key) == "modules",
                "last_changed_at": last.created_at.isoformat() if last else None,
                "last_changed_by": actor.email if actor else None,
            }
        )
    return out


@router.post("/flags/{key}/enable")
def enable_flag(
    key: str,
    account: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    was = flags.is_enabled(db, key)
    try:
        flags.enable(db, key)
    except flags.FlagNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "flag not found") from exc
    except flags.GateNotSatisfied as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "activation gates not satisfied") from exc
    admin.record_action(
        db,
        "flag_enable",
        actor_account_id=account.id,
        target_kind="flag",
        target_key=key,
        detail={"key": key},
        before={"enabled": was},
        after={"enabled": True},
    )
    return {"key": key, "enabled": flags.is_enabled(db, key)}


@router.post("/flags/{key}/disable")
def disable_flag(
    key: str,
    account: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    was = flags.is_enabled(db, key)
    try:
        flags.disable(db, key)
    except flags.FlagNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "flag not found") from exc
    admin.record_action(
        db,
        "flag_disable",
        actor_account_id=account.id,
        target_kind="flag",
        target_key=key,
        detail={"key": key},
        before={"enabled": was},
        after={"enabled": False},
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
    body: ResolveReportIn,
    account: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    # `approve` here means the REPORT was upheld: the content stays down. Naming it
    # that way keeps one verb across the whole moderation surface.
    try:
        result = m13.resolve_report(
            db,
            content_kind,
            content_ref,
            uphold=body.approve,
            moderator_account_id=account.id,
            reason=body.reason,
            frivolous=body.frivolous,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    admin.record_action(
        db,
        "report_resolve",
        actor_account_id=account.id,
        target_kind=content_kind,
        target_ref=content_ref,
        detail={"reason": body.reason},
        before={"status": "pending"},
        after={"upheld": body.approve, "frivolous": body.frivolous},
    )
    result["discredited"] = [
        {**d, "account_id": str(d["account_id"])} for d in result.get("discredited", [])
    ]
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
    """Values plus provenance. The actor comes from the audit log rather than a
    column on ConfigEntry — no table has to carry an actor it does not otherwise
    need, and the log is already the record of who changed what."""
    entries = flags.get_scope(db, scope)
    provenance = {}
    for key in entries:
        last = admin.last_action_for(db, "config_set", key)
        actor = (
            db.get(identity.Account, last.actor_account_id)
            if last and last.actor_account_id
            else None
        )
        provenance[key] = {
            "set_at": last.created_at.isoformat() if last else None,
            "set_by": actor.email if actor else None,
            "previous": (last.before or {}).get("value") if last else None,
        }
    return {"scope": scope, "entries": entries, "provenance": provenance}


@router.get("/config/scopes")
def config_scopes(
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[str]:
    # every scope that actually has entries, so an operator never has to guess a
    # scope name to discover what is configurable
    rows = db.execute(select(flags.ConfigEntry.scope).distinct().order_by(flags.ConfigEntry.scope))
    return [row[0] for row in rows]


@router.post("/config")
def set_config(
    body: ConfigIn,
    account: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    previous = flags.get_config(db, body.key)
    entry = flags.set_config(db, body.key, body.value, scope=body.scope)
    # F14 audit log: every config mutation is attributed, WITH the value it replaced
    admin.record_action(
        db,
        "config_set",
        actor_account_id=account.id,
        target_kind="config",
        target_key=body.key,
        detail={"key": body.key, "scope": body.scope, "value": body.value},
        before={"value": previous},
        after={"value": body.value},
    )
    return {"key": entry.key, "scope": entry.scope, "value": entry.value}


@router.get("/audit")
def audit_log(
    action: str | None = None,
    target_kind: str | None = None,
    target_key: str | None = None,
    limit: int | None = None,
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    # every operator mutation is an F14 AdminAction; newest first, actor resolved to
    # an email (batched — no N+1 per row)
    actions = admin.list_actions(
        db,
        action=action,
        target_kind=target_kind,
        target_key=target_key,
        limit=limit,
    )
    if limit is None:
        actions = list(reversed(actions))
    actor_ids = {a.actor_account_id for a in actions if a.actor_account_id}
    emails = {aid: acct.email for aid in actor_ids if (acct := db.get(identity.Account, aid))}
    return [
        {
            "id": str(a.id),
            "action": a.action,
            "actor": emails.get(a.actor_account_id),
            "target_kind": a.target_kind,
            "target_key": a.target_key,
            "target_ref": str(a.target_ref) if a.target_ref else None,
            "detail": a.detail,
            # what it was, and what it became — the question actually asked after
            # an incident
            "before": a.before,
            "after": a.after,
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
    was = item.status.value
    decision = admin.ModerationStatus.approved if body.approve else admin.ModerationStatus.rejected
    admin.decide_moderation(db, item, decision, moderator_account_id=account.id, reason=body.reason)
    admin.record_action(
        db,
        "moderation_decide",
        actor_account_id=account.id,
        target_kind=item.content_kind,
        target_ref=item.content_ref,
        detail={"reason": body.reason},
        before={"status": was},
        after={"status": item.status.value},
    )
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
    was = {"verify_status": vendor.verify_status.value, "status": vendor.status.value}
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
    admin.record_action(
        db,
        "vendor_decide",
        actor_account_id=account.id,
        target_kind="vendor",
        target_ref=vendor.id,
        target_key=vendor.name,
        before=was,
        after={"verify_status": vendor.verify_status.value, "status": vendor.status.value},
    )
    return {
        "vendor_id": str(vendor.id),
        "verify_status": vendor.verify_status.value,
        "status": vendor.status.value,
        "publish_suspended": vendor.publish_suspended,
    }


# --- Admin Console 2.0 sections ---
# AI-CONTEXT: module-specific numbers are composed HERE, not in F14. F14 is
# foundation and importing `app.modules.*` would break the architecture-spine
# contract; this router already legally imports both, so the aggregation belongs
# at this seam. F14 owns only the generic ops primitives (job runs, audit).

# job name -> the F13 flag that gates it, so the Overview can distinguish "failing"
# from "switched off" — an idle job is not a broken one.
_JOB_FLAGS = {
    "tpims_dynamic": "f02_ingest_tpims_dynamic",
    "tpims_static": "f02_ingest_tpims_static",
    "eia_regional": "m07_ingest_eia",
}

# flag family grouping for the Flags section. Derived from the key, with an
# explicit fallback so an unrecognised key is never silently hidden from an operator.
_FLAG_FAMILIES = (
    ("f02_ingest_", "ingest"),
    ("m07_ingest_", "ingest"),
    ("f", "foundation"),
    ("m", "modules"),
)


def _flag_family(key: str) -> str:
    for prefix, family in _FLAG_FAMILIES:
        if key.startswith(prefix):
            return family
    return "other"


def _job_health(db: Session) -> list[dict]:
    latest = admin.latest_job_runs(db)
    out = []
    for name, flag_key in _JOB_FLAGS.items():
        run = latest.get(name)
        out.append(
            {
                "job": name,
                "flag": flag_key,
                "enabled": flags.is_enabled(db, flag_key),
                # never-ran is reported as null rather than a fabricated zero row:
                # "ran and did nothing" and "never ran" are different facts
                "last_run_at": run.started_at.isoformat() if run else None,
                "ok": run.ok if run else None,
                "summary": run.summary if run else None,
                "error": run.error if run else None,
                "consecutive_failures": run.consecutive_failures if run else 0,
                "next_run_at": run.next_run_at.isoformat() if run and run.next_run_at else None,
            }
        )
    return out


def _facility_counts(db: Session) -> dict:
    from app.foundation.f02_facility import public as facility

    rows = db.execute(
        select(
            facility.FacilitySource.source_kind,
            func.count(func.distinct(facility.FacilitySource.facility_id)),
        ).group_by(facility.FacilitySource.source_kind)
    ).all()
    total = db.scalar(select(func.count()).select_from(facility.Facility)) or 0
    return {"total": int(total), "by_source": {kind.value: int(n) for kind, n in rows}}


def _ingest_freshness(db: Session) -> dict:
    from app.foundation.f02_facility import public as facility

    rows = db.execute(
        select(
            facility.SourceRecord.source_kind,
            func.max(facility.SourceRecord.ingested_at),
            func.count(),
        ).group_by(facility.SourceRecord.source_kind)
    ).all()
    return {
        kind.value: {"last_ingested_at": ts.isoformat() if ts else None, "records": int(n)}
        for kind, ts, n in rows
    }


def _vendor_funnel(db: Session) -> dict:
    # M13 appearance -> confirmation, computed from the module's own tables rather
    # than from events: the appearance rows ARE the record, and an event stream
    # would be a second source of truth that could drift from them.
    published = (
        db.scalar(
            select(func.count())
            .select_from(m13.Appearance)
            .where(
                m13.Appearance.status.in_((m13.AppearanceStatus.done, m13.AppearanceStatus.lapsed))
            )
        )
        or 0
    )
    confirmed = (
        db.scalar(
            select(func.count())
            .select_from(m13.Appearance)
            .where(m13.Appearance.confirmed.is_(True))
        )
        or 0
    )
    return {"published": int(published), "confirmed": int(confirmed)}


@router.get("/overview")
def overview(
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """The operator's morning glance: did the machinery run, what is waiting for a
    human, and are the two value loops converting."""
    now = datetime.now(UTC)
    queue = m13.queue_with_sla(db, now=now)
    pending_vendors = [
        v
        for v in db.scalars(select(m13.Vendor).where(m13.Vendor.status == m13.VendorStatus.active))
        if v.verify_status == m13.VendorVerifyStatus.documents_on_file
    ]
    funnel_counts = admin.funnel(db, _FUNNEL_STEPS, module=_FUNNEL_MODULE)
    return {
        "jobs": _job_health(db),
        "facilities": _facility_counts(db),
        "ingest": _ingest_freshness(db),
        "eia_week_of": flags.get_config(db, "m07_eia_week_of"),
        "pending": {
            "vendor_verification": len(pending_vendors),
            "moderation": len(queue),
            # the number that should make an operator act first, so it is carried
            # separately rather than left to be counted client-side
            "moderation_overdue": sum(1 for q in queue if q.overdue),
            "claim_disputes": int(
                db.scalar(
                    select(func.count())
                    .select_from(m13.FacilityClaim)
                    .where(m13.FacilityClaim.status == m13.ClaimStatus.disputed)
                )
                or 0
            ),
        },
        "funnels": {
            "detention": [
                {"event": step, "count": count}
                for step, count in zip(_FUNNEL_STEPS, funnel_counts, strict=True)
            ],
            "vendor_appearances": _vendor_funnel(db),
        },
    }


@router.get("/ingest")
def ingest_state(
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    from app.ingest import sources

    return {
        "facilities": _facility_counts(db),
        "freshness": _ingest_freshness(db),
        "jobs": _job_health(db),
        "sources": {key: sources.source_url(db, key) for key in sources.DEFAULTS},
    }


@router.get("/jobs/{job_name}")
def job_history(
    job_name: str,
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {
            "started_at": r.started_at.isoformat(),
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "ok": r.ok,
            "summary": r.summary,
            "error": r.error,
            "consecutive_failures": r.consecutive_failures,
        }
        for r in admin.job_history(db, job_name)
    ]


@router.get("/vendors/{vendor_id}/documents")
def vendor_documents(
    vendor_id: uuid.UUID,
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    vendor = m13.resolve_vendor(db, vendor_id)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    return [
        {
            "document_id": str(d.id),
            "kind": d.doc_kind.value,
            "review_status": d.review_status.value,
            "created_at": d.created_at.isoformat(),
        }
        for d in vendor.documents
    ]


@router.get("/claims")
def claims(
    disputed_only: bool = False,
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = select(m13.FacilityClaim).order_by(m13.FacilityClaim.created_at.desc())
    if disputed_only:
        stmt = stmt.where(m13.FacilityClaim.status == m13.ClaimStatus.disputed)
    out = []
    for claim in db.scalars(stmt):
        vendor = db.get(m13.Vendor, claim.vendor_id)
        out.append(
            {
                "claim_id": str(claim.id),
                "facility_id": str(claim.facility_id),
                "vendor_id": str(claim.vendor_id),
                "vendor_name": vendor.name if vendor else None,
                "claimed_name": claim.claimed_name,
                "name_match_score": claim.name_match_score,
                "status": claim.status.value,
                "has_document": claim.document_id is not None,
            }
        )
    return out


@router.get("/reporters/{account_id}")
def reporter_record(
    account_id: uuid.UUID,
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    # decision 4c: a moderator ruling on a report should see whether this reporter
    # has a history, so a pattern is visible rather than rediscovered each time
    account = db.get(identity.Account, account_id)
    return {
        "account_id": str(account_id),
        "email": account.email if account else None,
        "frivolous_strikes": m13.frivolous_strikes(db, account_id),
        "credible": m13.reporter_credible(db, account_id),
    }


# --- E-D6: account management ---
# AI-CONTEXT: the operator's account powers and their deliberate limits. Create,
# edit, reset a credential, deactivate. Never read a password, never set a permanent
# one, never delete. Every mutation is audited with before->after, and the
# platform_admin grant is the loudest entry in the log.
class AccountIn(BaseModel):
    email: str
    role: str = identity.Role.driver.value
    display_name: str | None = None


class AccountPatchIn(BaseModel):
    display_name: str | None = None
    locale: str | None = None
    legal_name: str | None = None
    mc_number: str | None = None
    dot_number: str | None = None
    plate_state: str | None = None
    plate_number: str | None = None
    unit_number: str | None = None


class RoleIn(BaseModel):
    role: str
    grant: bool = True
    # granting platform_admin hands over every power in this file; the console
    # requires an explicit confirmation and the API refuses without it
    confirm: bool = False


def _account_out(db: Session, account: identity.Account) -> dict:
    profile = db.get(identity.DriverProfile, account.id)
    return {
        "account_id": str(account.id),
        "email": account.email,
        "display_name": account.display_name,
        "active": account.active,
        "deactivated_at": account.deactivated_at.isoformat() if account.deactivated_at else None,
        "must_change_credential": identity.must_change_credential(db, account),
        "roles": sorted(r.role.value for r in account.roles),
        "created_at": account.created_at.isoformat() if account.created_at else None,
        "profile": None
        if profile is None
        else {
            "legal_name": profile.legal_name,
            "locale": profile.locale,
            "mc_number": profile.mc_number,
            "dot_number": profile.dot_number,
            "authority": profile.authority_type.value if profile.authority_type else None,
            "verify_status": profile.authority_verify_status.value,
            "plate_state": profile.plate_state,
            "plate_number": profile.plate_number,
            "unit_number": profile.unit_number,
            "vin": profile.vin,
        },
    }


def _load_account(db: Session, account_id: uuid.UUID) -> identity.Account:
    account = db.get(identity.Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    return account


@router.get("/accounts")
def list_accounts(
    q: str | None = None,
    role: str | None = None,
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    # one search box over the facts an operator actually has on the phone: an email,
    # a name, an MC/DOT number or a plate
    try:
        role_filter = identity.Role(role) if role else None
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown role") from exc
    return [_account_out(db, a) for a in identity.search_accounts(db, q, role_filter)]


@router.get("/accounts/{account_id}")
def account_detail(
    account_id: uuid.UUID,
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    account = _load_account(db, account_id)
    body = _account_out(db, account)
    # the account's own audit trail, so "what has support done to this person" is
    # answerable from the page where it matters
    body["audit"] = [
        {
            "action": a.action,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "before": a.before,
            "after": a.after,
        }
        for a in admin.list_actions(db, target_ref=account.id, limit=25)
    ]
    return body


@router.post("/accounts", status_code=201)
def create_account(
    body: AccountIn,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        role = identity.Role(body.role)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown role") from exc
    if role == identity.Role.platform_admin:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "grant platform_admin explicitly after creation, never at creation",
        )
    try:
        account, temporary = identity.admin_create_account(db, body.email, role, body.display_name)
    except identity.EmailAlreadyRegistered as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered") from exc
    admin.record_action(
        db,
        "account_create",
        actor_account_id=actor.id,
        target_kind="account",
        target_ref=account.id,
        target_key=account.email,
        after={"email": account.email, "role": role.value},
    )
    # the temporary password is returned ONCE, at creation, and never retrievable
    # again — there is no endpoint that reads it back
    return {**_account_out(db, account), "temporary_password": temporary}


@router.patch("/accounts/{account_id}")
def edit_account(
    account_id: uuid.UUID,
    body: AccountPatchIn,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    account = _load_account(db, account_id)
    before = _account_out(db, account)
    if body.display_name is not None:
        identity.set_display_name(db, account, body.display_name)
    profile_fields = {
        key: value
        for key, value in body.model_dump(exclude={"display_name"}).items()
        if value is not None
    }
    if profile_fields:
        identity.upsert_driver_profile(db, account, **profile_fields)
    after = _account_out(db, account)
    admin.record_action(
        db,
        "account_edit",
        actor_account_id=actor.id,
        target_kind="account",
        target_ref=account.id,
        target_key=account.email,
        before={"display_name": before["display_name"], "profile": before["profile"]},
        after={"display_name": after["display_name"], "profile": after["profile"]},
    )
    return after


@router.post("/accounts/{account_id}/reset-credential")
def reset_credential(
    account_id: uuid.UUID,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    account = _load_account(db, account_id)
    temporary = identity.reset_credential(db, account)
    admin.record_action(
        db,
        "account_credential_reset",
        actor_account_id=actor.id,
        target_kind="account",
        target_ref=account.id,
        target_key=account.email,
        after={"must_change": True},
    )
    # the audit records THAT a reset happened, never the credential itself
    return {"account_id": str(account.id), "temporary_password": temporary}


@router.post("/accounts/{account_id}/deactivate")
def deactivate_account(
    account_id: uuid.UUID,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    account = _load_account(db, account_id)
    if account.id == actor.id:
        # an operator locking themselves out mid-incident helps nobody
        raise HTTPException(status.HTTP_409_CONFLICT, "an admin cannot deactivate themselves")
    identity.deactivate_account(db, account)
    admin.record_action(
        db,
        "account_deactivate",
        actor_account_id=actor.id,
        target_kind="account",
        target_ref=account.id,
        target_key=account.email,
        before={"active": True},
        after={"active": False},
    )
    return _account_out(db, account)


@router.post("/accounts/{account_id}/reactivate")
def reactivate_account(
    account_id: uuid.UUID,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    account = _load_account(db, account_id)
    identity.reactivate_account(db, account)
    admin.record_action(
        db,
        "account_reactivate",
        actor_account_id=actor.id,
        target_kind="account",
        target_ref=account.id,
        target_key=account.email,
        before={"active": False},
        after={"active": True},
    )
    return _account_out(db, account)


@router.post("/accounts/{account_id}/roles")
def change_role(
    account_id: uuid.UUID,
    body: RoleIn,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    account = _load_account(db, account_id)
    try:
        role = identity.Role(body.role)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown role") from exc

    # granting platform_admin hands over every power in this file, including the
    # ability to grant it onward; it never happens on a mis-click
    if role == identity.Role.platform_admin and not body.confirm:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"error": "confirm_required", "role": role.value},
        )
    if role == identity.Role.platform_admin and not body.grant and account.id == actor.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "an admin cannot revoke their own admin role")

    before = sorted(r.role.value for r in account.roles)
    if body.grant:
        if not identity.has_role(db, account, role):
            identity.attach_role(db, account, role)
            db.expire(account, ["roles"])
    else:
        identity.revoke_role(db, account, role)
    after = sorted(r.role.value for r in account.roles)
    admin.record_action(
        db,
        "account_role_admin" if role == identity.Role.platform_admin else "account_role",
        actor_account_id=actor.id,
        target_kind="account",
        target_ref=account.id,
        target_key=account.email,
        detail={"role": role.value, "granted": body.grant},
        before={"roles": before},
        after={"roles": after},
    )
    return _account_out(db, account)


# --- F13 activation gates (manual-settability principle) ---
class GateIn(BaseModel):
    name: str
    satisfied: bool
    note: str | None = None


@router.post("/flags/{key}/gates")
def set_gate(
    key: str,
    body: GateIn,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """A gate can be withdrawn as well as met. An activation precondition that could
    only ever be ticked is a one-way ratchet — if a legal review lapses, the gate
    must be able to go back, and enabling then refuses until it is met again."""
    gate = flags.get_gate(db, key, body.name)
    if gate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "gate not found")
    was = gate.satisfied
    if body.satisfied:
        flags.satisfy_gate(db, gate, body.note)
    else:
        flags.unsatisfy_gate(db, gate, body.note)
    admin.record_action(
        db,
        "flag_gate",
        actor_account_id=actor.id,
        target_kind="flag",
        target_key=key,
        detail={"gate": body.name},
        before={"satisfied": was},
        after={"satisfied": gate.satisfied},
    )
    return {
        "key": key,
        "gate": gate.name,
        "satisfied": gate.satisfied,
        "can_activate": flags.can_activate(db, key),
    }


# --- admin-initiated vendor registration (founding-vendor onboarding) ---
class VendorRegisterIn(BaseModel):
    owner_account_id: uuid.UUID
    name: str
    vendor_type: str = "food_mobile"
    metro: str = ""
    contact_phone: str | None = None
    languages: list[str] = []
    halal_disclosure: str | None = None
    halal_answered: bool = False


@router.post("/vendors", status_code=201)
def register_vendor(
    body: VendorRegisterIn,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Console-native vendor registration — the phone-onboarding path. Every M13 law
    applies unchanged: Q-5 dedupe still blocks a second profile for the same cook,
    and the Q-4 publish floor still governs what they can publish afterwards. An
    admin creating the record is not an admin bypassing the rules."""
    _load_account(db, body.owner_account_id)
    try:
        vendor = m13.register_vendor(
            db,
            body.owner_account_id,
            body.name,
            m13.VendorType(body.vendor_type),
            metro=body.metro,
            contact_phone=body.contact_phone,
            languages=body.languages,
            halal_disclosure=body.halal_disclosure,
            halal_answered=body.halal_answered,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown vendor type") from exc
    except m13.DuplicateVendor as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"error": "duplicate_vendor", "existing_vendor_id": str(exc.existing.id)},
        ) from exc
    admin.record_action(
        db,
        "vendor_register",
        actor_account_id=actor.id,
        target_kind="vendor",
        target_ref=vendor.id,
        target_key=vendor.name,
        after={"name": vendor.name, "metro": vendor.metro, "type": vendor.vendor_type.value},
    )
    return {
        "vendor_id": str(vendor.id),
        "name": vendor.name,
        "verify_status": vendor.verify_status.value,
        "profile_gaps": m13.profile_gaps(vendor),
    }


# --- E-D5: scoped impersonation ("view as vendor") ---
@router.post("/vendors/{vendor_id}/impersonate")
def impersonate_vendor(
    vendor_id: uuid.UUID,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Open the vendor portal exactly as this vendor sees it. The returned token is
    an ADMIN session that names the vendor — so every write it makes attributes to
    the admin — and it is refused by ordinary authentication, so it can never reach
    a driver endpoint. Time-boxed: a support session left open is an unlocked door."""
    vendor = m13.resolve_vendor(db, vendor_id)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    owner = db.get(identity.Account, vendor.owner_account_id)
    if owner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor has no owner account")
    try:
        session = identity.start_impersonation(
            db, actor, owner, is_vendor=m13.is_member(db, vendor.id, owner.id)
        )
    except identity.ImpersonationNotPermitted as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "vendors only") from exc
    except identity.AccountInactive as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "account is deactivated") from exc
    admin.record_action(
        db,
        "impersonation_start",
        actor_account_id=actor.id,
        target_kind="vendor",
        target_ref=vendor.id,
        target_key=vendor.name,
        after={"expires_at": session.expires_at.isoformat(), "subject": str(owner.id)},
    )
    return {
        "token": session.token,
        "vendor_id": str(vendor.id),
        "vendor_name": vendor.name,
        "expires_at": session.expires_at.isoformat(),
        "ttl_minutes": int(identity.IMPERSONATION_TTL.total_seconds() // 60),
    }


class EndImpersonationIn(BaseModel):
    token: str


@router.post("/impersonation/end")
def end_impersonation(
    body: EndImpersonationIn,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    session = identity.end_impersonation(db, body.token)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not an impersonation session")
    admin.record_action(
        db,
        "impersonation_end",
        actor_account_id=actor.id,
        target_kind="account",
        target_ref=session.impersonating_account_id,
        after={"ended_at": session.ended_at.isoformat()},
    )
    return {"ended": True}


@router.get("/vendors/{vendor_id}/detail")
def vendor_detail(
    vendor_id: uuid.UUID,
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Everything about one vendor on one page — profile, schedule, promotions,
    reviews, strikes, documents, and what support has already done here."""
    vendor = m13.resolve_vendor(db, vendor_id)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    score = m13.reliability(db, vendor.id)
    reviews = m13.review_summary(db, vendor.id)
    return {
        "vendor_id": str(vendor.id),
        "name": vendor.name,
        "vendor_type": vendor.vendor_type.value,
        "metro": vendor.metro,
        "contact_phone": vendor.contact_phone,
        "languages": vendor.languages,
        "halal_disclosure": vendor.halal_disclosure,
        "verify_status": vendor.verify_status.value,
        "status": vendor.status.value,
        "publish_suspended": vendor.publish_suspended,
        "consecutive_no_shows": vendor.consecutive_no_shows,
        "profile_gaps": m13.profile_gaps(vendor),
        "owner_account_id": str(vendor.owner_account_id),
        "shows_up": {"confirmed": score.confirmed, "published": score.published},
        "reviews": {"average": reviews.average, "reviewers": reviews.reviewers},
        "upheld_reports": m13.upheld_report_count(db, vendor.id),
        "documents": [
            {"kind": d.doc_kind.value, "review_status": d.review_status.value}
            for d in vendor.documents
        ],
        "appearances": [
            {
                "appearance_id": str(a.id),
                "facility_id": str(a.facility_id),
                "starts_at": a.starts_at.isoformat(),
                "status": a.status.value,
                "confirmed": a.confirmed,
            }
            for a in db.scalars(
                select(m13.Appearance)
                .where(m13.Appearance.vendor_id == vendor.id)
                .order_by(m13.Appearance.starts_at.desc())
                .limit(20)
            )
        ],
        "promotions": [
            {"promotion_id": str(p.id), "text": p.text, "status": p.status.value}
            for p in db.scalars(select(m13.Promotion).where(m13.Promotion.vendor_id == vendor.id))
        ],
        "audit": [
            {
                "action": a.action,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "before": a.before,
                "after": a.after,
            }
            for a in admin.list_actions(db, target_ref=vendor.id, limit=25)
        ],
    }
