"""AI-CONTEXT: F14 Admin Console HTTP endpoints — the platform operator surface,
gated to `platform_admin` accounts. Composes F13 (feature flags + gates) + F14
(admin views, moderation, analytics) + F1 (the role check). Backs the web-first
admin portal (design-prd §18), not the driver app. Read-only where it can be;
the only mutations are flag toggles and moderation decisions.
"""

import math
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import canonical_facility_id, current_account, get_db
from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify
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
                # AI-CONTEXT: `enabled` is the EFFECTIVE state — what the product is doing
                # — and the two facts behind it are reported separately (audit F-02,
                # §23 entry 133). A console that showed only the raw column could not tell
                # an operator whether a capability is on because they decided so or because
                # it ships that way, and that is the distinction the whole fix rests on.
                "enabled": flags.is_enabled(db, f.key),
                "default_on": f.default_on,
                "operator_decision": f.enabled,  # None = nobody has decided
                "kill_switch": f.kill_switch,
                "can_activate": flags.can_activate(db, f.key),
                # the honest flag: live, with its own preconditions unmet
                "running_ahead_of_gates": flags.is_enabled(db, f.key)
                and not flags.can_activate(db, f.key),
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
    # AI-CONTEXT: DECLARED keys too — this endpoint listed only rows that exist, so a
    # key nobody had set yet appeared nowhere, and `/config/scopes` two lines down
    # promised an operator "never has to guess a scope name to discover what is
    # configurable" while guessing the KEY stayed the only way in. A1 req 1's capture
    # checklist is the first config any component reads, and it would have shipped as
    # configuration nobody could find.
    return {
        "scope": scope,
        "entries": entries,
        "provenance": provenance,
        "declared": flags.declared_configs(db, scope),
    }


@router.get("/config/scopes")
def config_scopes(
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[str]:
    # every scope that has entries OR declarations. Entries alone meant a box where
    # nothing had been configured yet returned an EMPTY list — so the console's scope
    # dropdown was empty, and the declared keys behind it were unreachable. The promise
    # in the line below was the one this endpoint was failing to keep.
    rows = db.execute(select(flags.ConfigEntry.scope).distinct())
    declared = db.execute(select(flags.ConfigDeclaration.scope).distinct())
    return sorted({row[0] for row in rows} | {row[0] for row in declared})


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
    except identity.VerifierBusy as exc:
        # this route hashes TWICE (register + reset), so it is the heaviest creation path
        # in the product. A busy pool is a 503, never a 500 (F1-6).
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "account creation is busy",
            headers={"Retry-After": "1"},
        ) from exc
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
    try:
        temporary = identity.reset_credential(db, account)
    except identity.VerifierBusy as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "account creation is busy",
            headers={"Retry-After": "1"},
        ) from exc
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


# --- Decision 7: facility manual management ---
# AI-CONTEXT: an admin edit is another SOURCE, not an overwrite. It goes through the
# same F2 pipeline every ingest uses, so what NTAD/OSM/TPIMS recorded keeps its
# provenance and the existing priority + union rules decide the canonical value. An
# operator correcting a name does not silently erase what a feed said.
class FacilityIn(BaseModel):
    name: str
    facility_type: str
    lat: float
    lon: float
    services: list[str] = []
    capacity: int | None = None
    address: str | None = None
    is_dev: bool = False


class FacilityPatchIn(BaseModel):
    name: str | None = None
    services: list[str] | None = None
    capacity: int | None = None
    address: str | None = None
    is_dev: bool | None = None


class MergeIn(BaseModel):
    duplicate_id: uuid.UUID


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _facility_out(db: Session, fac) -> dict:
    from app.foundation.f02_facility import public as facility

    lat, lon = facility.coordinates(db, fac)
    return {
        "facility_id": str(fac.id),
        "name": fac.name,
        "facility_type": fac.facility_type.value,
        "status": fac.status.value,
        "lat": lat,
        "lon": lon,
        "address": fac.address,
        "attributes": fac.attributes or {},
        "confidence": fac.confidence,
        "is_dev": fac.is_dev,
        # provenance is shown, always: an operator editing a facility should see
        # which feeds already have a claim on it
        "sources": sorted({s.source_kind.value for s in fac.sources}),
    }


def _admin_source(db: Session, fac, **attributes):
    """Write an admin's facts as an `admin` SOURCE record through the ingest
    pipeline. The pipeline's existing rules then merge it — union for services,
    priority elsewhere — so an admin edit adds to what is known without deleting
    another source's claim."""
    from app.foundation.f02_facility import public as facility

    lat, lon = facility.coordinates(db, fac)
    record = facility.StagedRecord(
        source_kind=facility.SourceKind.admin,
        external_ref=f"admin/{fac.id}",
        name=attributes.pop("name", None) or fac.name,
        lat=lat,
        lon=lon,
        facility_type=fac.facility_type,
        attributes={k: v for k, v in attributes.items() if v is not None},
    )
    merged, _ = facility.upsert_record(db, record, batch_id="admin-edit")
    return merged


@router.get("/facilities")
def list_facilities(
    q: str | None = None,
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    from app.foundation.f02_facility import public as facility

    stmt = select(facility.Facility).where(
        facility.Facility.status != facility.FacilityStatus.merged
    )
    if q:
        stmt = stmt.where(func.lower(facility.Facility.name).like(f"%{q.strip().lower()}%"))
    return [
        _facility_out(db, f) for f in db.scalars(stmt.order_by(facility.Facility.name).limit(50))
    ]


@router.post("/facilities", status_code=201)
def create_facility(
    body: FacilityIn,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    from app.foundation.f02_facility import public as facility

    try:
        kind = facility.FacilityType(body.facility_type)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown facility type") from exc
    attributes = {}
    if body.services:
        attributes["services"] = body.services
    if body.capacity is not None:
        attributes["capacity"] = body.capacity
    fac = facility.create_facility(
        db,
        kind,
        body.name,
        body.lat,
        body.lon,
        source_kind=facility.SourceKind.admin,
        address=body.address,
        attributes=attributes,
        is_dev=body.is_dev,
    )
    admin.record_action(
        db,
        "facility_create",
        actor_account_id=actor.id,
        target_kind="facility",
        target_ref=fac.id,
        target_key=fac.name,
        after={"name": fac.name, "type": kind.value, "is_dev": fac.is_dev},
    )
    return _facility_out(db, fac)


# AI-CONTEXT: `canonical_facility_id` resolves a merged id to the site it was merged
# INTO. It has been on every driver-facing route since §23's merged-id fix and was never
# carried across to these three — so an admin editing a merged id edited the SHADOW: the
# patch recorded, the audit log saying it happened, and the map showing the old value
# forever, because the row they edited is one nothing renders.
@router.patch("/facilities/{facility_id}")
def edit_facility(
    body: FacilityPatchIn,
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    from app.foundation.f02_facility import public as facility

    fac = facility.get_facility(db, facility_id)
    if fac is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "facility not found")
    before = _facility_out(db, fac)
    if body.is_dev is not None:
        fac.is_dev = body.is_dev
    _admin_source(
        db,
        fac,
        name=body.name,
        services=body.services,
        capacity=body.capacity,
    )
    if body.address is not None:
        fac.address = body.address
    if body.name is not None:
        # ATTRIBUTES are arbitrated by the pipeline (union for services, priority
        # elsewhere), but the canonical NAME has no such rule — the pipeline sets it
        # once at creation and never revisits it, so nothing would apply an admin's
        # correction. Setting it here is therefore the only way an operator can fix a
        # name, and it is safe: no ingest path renames an existing facility. The
        # admin source recorded above keeps the provenance visible either way.
        fac.name = body.name.strip()
    db.flush()
    after = _facility_out(db, fac)
    admin.record_action(
        db,
        "facility_edit",
        actor_account_id=actor.id,
        target_kind="facility",
        target_ref=fac.id,
        target_key=fac.name,
        before={"name": before["name"], "attributes": before["attributes"]},
        after={"name": after["name"], "attributes": after["attributes"]},
    )
    return after


@router.post("/facilities/{facility_id}/merge")
def merge_facility(
    body: MergeIn,
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """The duplicate's sources move to the canonical record and the duplicate is
    marked merged — it is never deleted, so a stale reference still resolves."""
    from app.foundation.f02_facility import public as facility

    canonical = facility.get_facility(db, facility_id)
    duplicate = facility.get_facility(db, body.duplicate_id)
    if canonical is None or duplicate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "facility not found")
    try:
        # the rule lives in `merge_facilities` so all four callers share it: a merge
        # always lands on the canonical row, and a cycle is refused rather than written
        canonical = facility.merge_facilities(db, canonical, duplicate)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    admin.record_action(
        db,
        "facility_merge",
        actor_account_id=actor.id,
        target_kind="facility",
        target_ref=canonical.id,
        target_key=canonical.name,
        detail={"duplicate_id": str(duplicate.id)},
        before={"duplicate": duplicate.name},
        after={"merged_into": canonical.name},
    )
    return _facility_out(db, canonical)


@router.get("/facilities/{facility_id}/duplicates")
def facility_duplicates(
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    # the same blocking + fuzzy match the ingest pipeline uses, so what an operator
    # is shown is what the pipeline itself would have considered a duplicate
    from app.foundation.f02_facility import public as facility

    fac = facility.get_facility(db, facility_id)
    if fac is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "facility not found")
    lat, lon = facility.coordinates(db, fac)
    out = []
    for candidate in facility.find_duplicate_candidates(db, fac.name, lat, lon):
        if candidate.id == fac.id:
            continue
        row = _facility_out(db, candidate)
        # §11.7 does not let a figure travel without what produced it, and a merge
        # SUGGESTION is a figure. The console rendered a candidate's name alone, so an
        # operator deciding "same place?" could not tell 5 m from 140 m — the difference
        # between one site mapped twice and the rest area on the other carriageway. This
        # is the evidence this session needed to judge 95 merges by hand, and a merge
        # cannot be undone from the console.
        c_lat, c_lon = facility.coordinates(db, candidate)
        row["distance_m"] = (
            round(_haversine_m(lat, lon, c_lat, c_lon))
            if None not in (lat, lon, c_lat, c_lon)
            else None
        )
        out.append(row)
    return out


# --- E-D5 mode (a): assisted edit from the console, attributed ---
# AI-CONTEXT: the SAME writes the vendor portal offers, made directly from the
# console without impersonating. Attribution is the point of the mode: each write
# records an `assisted_*` action naming the admin as actor and the vendor as target,
# which is exactly what the vendor's own portal reads to show "edited by Haulmeter
# support" — so a console edit surfaces to them with no extra plumbing.
#
# Every M13 law applies unchanged. `publish_appearance` runs the Q-4 floor and the
# suspension gate here as it does everywhere else: an admin editing on someone's
# behalf gets attribution, never exemption.
class VendorProfileIn(BaseModel):
    name: str | None = None
    metro: str | None = None
    contact_phone: str | None = None
    categories: list[str] | None = None
    languages: list[str] | None = None
    halal_disclosure: str | None = None
    halal_answered: bool | None = None


class AssistedOfferingIn(BaseModel):
    name: str
    price_cents: int
    portions: int | None = None


class AssistedAppearanceIn(BaseModel):
    facility_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    offerings: list[AssistedOfferingIn]
    property_approved: bool = False
    weekly: list[int] | None = None


class AssistedPromotionIn(BaseModel):
    text: str
    starts_at: datetime
    ends_at: datetime


def _load_vendor(db: Session, vendor_id: uuid.UUID):
    vendor = m13.resolve_vendor(db, vendor_id)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vendor not found")
    return vendor


def _record_assisted(db: Session, actor, vendor, action: str, before, after) -> None:
    admin.record_action(
        db,
        f"assisted_{action}",
        actor_account_id=actor.id,
        target_kind="vendor",
        target_ref=vendor.id,
        target_key=vendor.name,
        detail={"on_behalf_of": str(vendor.owner_account_id), "impersonated": False},
        before=before,
        after=after,
    )


def _vendor_profile_out(vendor) -> dict:
    return {
        "name": vendor.name,
        "metro": vendor.metro,
        "contact_phone": vendor.contact_phone,
        "categories": list(vendor.categories or []),
        "languages": list(vendor.languages or []),
        "halal_disclosure": vendor.halal_disclosure,
        "halal_answered": vendor.halal_answered,
    }


@router.patch("/vendors/{vendor_id}")
def edit_vendor_profile(
    vendor_id: uuid.UUID,
    body: VendorProfileIn,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    vendor = _load_vendor(db, vendor_id)
    before = _vendor_profile_out(vendor)
    if body.name is not None:
        vendor.name = body.name.strip()
    if body.metro is not None:
        vendor.metro = body.metro.strip()
    if body.contact_phone is not None:
        vendor.contact_phone = "".join(ch for ch in body.contact_phone if ch.isdigit())[-10:]
    if body.categories is not None:
        vendor.categories = body.categories
    if body.languages is not None:
        vendor.languages = body.languages
    if body.halal_disclosure is not None:
        vendor.halal_disclosure = body.halal_disclosure
    if body.halal_answered is not None:
        vendor.halal_answered = body.halal_answered
    db.flush()
    after = _vendor_profile_out(vendor)
    _record_assisted(db, actor, vendor, "profile_edit", before, after)
    # what still blocks publishing, so an operator fixing a profile by phone knows
    # when they are done rather than guessing
    return {**after, "profile_gaps": m13.profile_gaps(vendor)}


@router.post("/vendors/{vendor_id}/appearances", status_code=201)
def assist_publish_appearance(
    vendor_id: uuid.UUID,
    body: AssistedAppearanceIn,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    vendor = _load_vendor(db, vendor_id)
    try:
        created = m13.publish_appearance(
            db,
            vendor,
            body.facility_id,
            body.starts_at,
            body.ends_at,
            [m13.OfferingIn(o.name, o.price_cents, o.portions) for o in body.offerings],
            property_approved=body.property_approved,
            weekly=body.weekly,
        )
    except m13.ListingIncomplete as exc:
        # the Q-4 floor refuses an admin exactly as it refuses the vendor
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"error": "listing_incomplete", "missing": exc.missing},
        ) from exc
    except m13.PublishSuspended as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, {"error": "publish_suspended"}) from exc
    _record_assisted(
        db,
        actor,
        vendor,
        "appearance_publish",
        None,
        {"appearance_ids": [str(a.id) for a in created], "facility_id": str(body.facility_id)},
    )
    return {"appearance_ids": [str(a.id) for a in created]}


@router.delete("/vendors/{vendor_id}/appearances/{appearance_id}")
def assist_cancel_appearance(
    vendor_id: uuid.UUID,
    appearance_id: uuid.UUID,
    whole_series: bool = False,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    vendor = _load_vendor(db, vendor_id)
    appearance = db.get(m13.Appearance, appearance_id)
    if appearance is None or appearance.vendor_id != vendor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "appearance not found")
    gateway = notify.RecordingNotificationGateway()
    cancelled = m13.cancel_appearance(db, appearance, gateway=gateway, whole_series=whole_series)
    _record_assisted(
        db,
        actor,
        vendor,
        "appearance_cancel",
        {"status": "scheduled"},
        {"cancelled": [str(a.id) for a in cancelled]},
    )
    return {"cancelled": [str(a.id) for a in cancelled], "alerts_sent": len(gateway.sent)}


@router.post("/vendors/{vendor_id}/promotions", status_code=201)
def assist_create_promotion(
    vendor_id: uuid.UUID,
    body: AssistedPromotionIn,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    vendor = _load_vendor(db, vendor_id)
    try:
        promotion = m13.create_promotion(db, vendor, body.text, body.starts_at, body.ends_at)
    except m13.InvalidPromotion as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    _record_assisted(db, actor, vendor, "promotion_create", None, {"text": promotion.text})
    gateway = notify.RecordingNotificationGateway()
    sent = m13.notify_promotion(db, promotion, gateway)
    delivered = sum(1 for n in sent if n.status == notify.NotificationStatus.sent)
    return {
        "promotion_id": str(promotion.id),
        "alerts_delivered": delivered,
        "alerts_suppressed": len(sent) - delivered,
    }


@router.delete("/vendors/{vendor_id}/promotions/{promotion_id}")
def assist_cancel_promotion(
    vendor_id: uuid.UUID,
    promotion_id: uuid.UUID,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    vendor = _load_vendor(db, vendor_id)
    promotion = db.get(m13.Promotion, promotion_id)
    if promotion is None or promotion.vendor_id != vendor.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "promotion not found")
    m13.cancel_promotion(db, promotion)
    _record_assisted(
        db, actor, vendor, "promotion_cancel", {"status": "active"}, {"status": "cancelled"}
    )
    return {"promotion_id": str(promotion.id), "status": promotion.status.value}


# --- M15 content pipeline (E3 §E3.1.5) ------------------------------------------------
#
# AI-CONTEXT: Q-6's operator surface, and it did not exist. `mark_reviewed` and `release`
# lived in `m15_roadside/domain/content.py` with no caller anywhere in the product, so
# nothing could ever become `released` and every driver surface in M15 would have rendered
# its empty state permanently. The laws stay in the domain — these routes are a way for a
# named human to reach them, not a second place where the rules are decided.
#
# THE REVIEWER IS THE ADMIN'S OWN EMAIL, not a free-text field. `mark_reviewed` requires a
# named human because a blank reviewer is how "reviewed" silently becomes "generated"; a
# field the operator types into would let that name be anything, including nothing
# meaningful. The account that clicked is the one claim the server can actually make.


def _m15_variant(db: Session, item_id: uuid.UUID):
    from app.modules.m15_roadside.domain import models as m15m

    item = db.get(m15m.PhraseVariant, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such variant")
    return item


def _m15_model_answer(db: Session, item_id: uuid.UUID):
    from app.modules.m15_roadside.domain import models as m15m

    item = db.get(m15m.ModelAnswer, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such model answer")
    return item


def _m15_by_type(attr: str, label: str):
    """A resolver for one publishable kind, by model attribute name."""

    def _resolve(db: Session, item_id: uuid.UUID):
        from app.modules.m15_roadside.domain import models as m15m

        item = db.get(getattr(m15m, attr), item_id)
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"no such {label}")
        return item

    return _resolve


# AI-CONTEXT: ONE DISPATCH, and it was missing four of the seven publishable kinds — most
# importantly `coaching`, which is every driver's explanation in their own language. Q-6
# says content ships reviewed or not at all, and Q-9 says a driver never sees English in
# its place; both are enforced in the domain, and neither is reachable by a human if the
# review surface cannot open the row. The acknowledgements released earlier had to go out
# by script for exactly this reason, which is not a review path, it is a workaround.
_M15_KINDS = {
    "variant": _m15_variant,
    "model_answer": _m15_model_answer,
    "coaching": _m15_by_type("CoachingContent", "coaching explanation"),
    "ack": _m15_by_type("OfficerAck", "officer line"),
    "repair": _m15_by_type("RepairLine", "repair line"),
}


def _m15_item(db: Session, kind: str, item_id: uuid.UUID):
    return _M15_KINDS.get(kind, _m15_scenario)(db, item_id)


def _m15_scenario(db: Session, item_id: uuid.UUID):
    from app.modules.m15_roadside.domain import models as m15m

    item = db.get(m15m.ScenarioVersion, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such scenario")
    return item


@router.get("/roadside/content")
def roadside_content(
    _admin: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Everything in the pipeline, with its status. The review queue IS this list."""
    from app.modules.m15_roadside.domain import models as m15m

    scenarios = db.scalars(select(m15m.ScenarioVersion).order_by(m15m.ScenarioVersion.version))
    intents = db.scalars(select(m15m.Intent).order_by(m15m.Intent.key))
    variants = list(db.scalars(select(m15m.PhraseVariant)))
    by_intent: dict = {}
    for variant in variants:
        by_intent.setdefault(variant.intent_id, []).append(variant)

    model_answers = list(db.scalars(select(m15m.ModelAnswer)))
    by_intent_answers: dict = {}
    for answer in model_answers:
        by_intent_answers.setdefault(answer.intent_id, []).append(answer)

    # AI-CONTEXT: THE COACHING EXPLANATIONS, which a reviewer could not see at all. This is
    # the text a driver reads in their OWN language explaining why an answer missed — the
    # single place in the module where a mistranslation teaches something false rather than
    # merely reading badly. Q-9 keeps English out of that slot; Q-6 keeps unreviewed text
    # out of it; and neither is reachable by a human if the review queue does not list it.
    coaching = list(db.scalars(select(m15m.CoachingContent)))
    by_intent_coaching: dict = {}
    for row in coaching:
        by_intent_coaching.setdefault(row.intent_id, []).append(row)

    return {
        "scenarios": [
            {
                "id": str(s.id),
                "version": s.version,
                "status": s.status.value,
                "difficulty": s.difficulty.value,
                "intents": list(s.allowed_intents or []),
            }
            for s in scenarios
        ],
        "intents": [
            {
                "key": intent.key,
                "domain": intent.domain,
                "variants": [
                    {
                        "id": str(v.id),
                        "text": v.text,
                        "status": v.status.value,
                        "version": v.version,
                        # AI-CONTEXT: shown because a holdout must NEVER be released into
                        # the teaching pool by someone who could not see what it was. Q-5
                        # is enforced in the generators, but an operator releasing blind
                        # is how a reviewer becomes an accomplice to a leak.
                        "holdout": v.holdout,
                    }
                    for v in sorted(by_intent.get(intent.id, []), key=lambda v: v.version)
                ],
                # AI-CONTEXT: model answers ride the same row as the phrasings because a
                # reviewer needs to see them TOGETHER — an answer is only fit for shadowing
                # if it answers the question above it.
                "model_answers": [
                    {
                        "id": str(a.id),
                        "text": a.text,
                        "status": a.status.value,
                        "version": a.version,
                    }
                    for a in sorted(by_intent_answers.get(intent.id, []), key=lambda a: a.version)
                ],
                # the explanation a driver reads in their own language, per locale
                "coaching": [
                    {
                        "id": str(c.id),
                        "locale": c.locale,
                        "text": c.explanation,
                        "status": c.review_status.value,
                        "version": c.version,
                        # so a reviewer can tell "written but silent" from "spoken", which
                        # are different things to hand a driver
                        "has_audio": c.audio_ref is not None,
                    }
                    for c in sorted(
                        by_intent_coaching.get(intent.id, []), key=lambda c: (c.locale, c.version)
                    )
                ],
            }
            for intent in intents
        ],
    }


@router.post("/roadside/content/{kind}/{item_id}/review")
def roadside_review(
    kind: str,
    item_id: uuid.UUID,
    actor: identity.Account = Depends(current_admin),
    db: Session = Depends(get_db),
) -> dict:
    from app.modules.m15_roadside.domain import content as m15content

    item = _m15_item(db, kind, item_id)
    # AI-CONTEXT: through the module, not `item.status` — `CoachingContent` keeps its
    # status in `review_status`, and reading the wrong attribute raises on precisely the
    # kind that carries a driver's own language.
    was = m15content.status_of(item).value
    try:
        m15content.mark_reviewed(item, actor.email)
    except m15content.ContentNotReviewed as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    # AI-CONTEXT: the audit entry IS the review record. Q-6 wants a named human, and
    # `mark_reviewed` only checks that a name was supplied — this is where the name is
    # kept, against the item, with a timestamp. Without it "who said this was fit for a
    # driver" is answerable only until the next release overwrites the status.
    admin.record_action(
        db,
        "roadside_content_review",
        actor_account_id=actor.id,
        target_kind=f"m15_{kind}",
        target_key=str(item.id),
        detail={"kind": kind, "reviewer": actor.email},
        before={"status": was},
        after={"status": m15content.status_of(item).value},
    )
    db.commit()
    return {
        "id": str(item.id),
        "status": m15content.status_of(item).value,
        "reviewer": actor.email,
    }


@router.post("/roadside/content/{kind}/{item_id}/release")
def roadside_release(
    kind: str,
    item_id: uuid.UUID,
    _admin: identity.Account = Depends(current_admin),  # noqa: ARG001 — the actor, audited
    db: Session = Depends(get_db),
) -> dict:
    """Promote reviewed -> released.

    AI-CONTEXT: `previous_version` IS 0 HERE, and that is a limitation stated rather than
    disguised.

    The domain's bump rule is about SUPERSESSION — a version 2 replacing the version 1 a
    driver was previously scored against, so "which text did they hear" stays answerable.
    The schema records no supersession link: variants are independent rows, and an intent
    is MEANT to hold several at once (`teachable_variants` returns a pool, and Q-5 needs
    holdouts sitting beside taught lines). Computing the bump from the highest released
    SIBLING — which this endpoint did first — makes two alternative phrasings of one
    question mutually exclusive at version 1, which breaks the pool the module is built on.
    Found by trying to release the seeded scenario, not by reading the code.

    So this surface releases items that have never been released, and 0 is the honest
    predecessor for that. `content.release` still refuses anything not `reviewed`, and no
    route moves a released item back — so re-releasing an edited text is not reachable from
    here at all. A real supersession path needs a schema link and is not this session's.
    """
    from app.modules.m15_roadside.domain import content as m15content

    item = _m15_item(db, kind, item_id)
    # AI-CONTEXT: through the module, not `item.status` — `CoachingContent` keeps its
    # status in `review_status`, and reading the wrong attribute raises on precisely the
    # kind that carries a driver's own language.
    was = m15content.status_of(item).value
    try:
        m15content.release(item, previous_version=0)
    except m15content.ContentNotReviewed as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    admin.record_action(
        db,
        "roadside_content_release",
        actor_account_id=_admin.id,
        target_kind=f"m15_{kind}",
        target_key=str(item.id),
        detail={"kind": kind},
        before={"status": was},
        after={"status": m15content.status_of(item).value, "version": item.version},
    )
    db.commit()
    return {
        "id": str(item.id),
        "status": m15content.status_of(item).value,
        "version": item.version,
    }
