"""AI-CONTEXT: M14 Fleet Recovery Overlay HTTP endpoints — slice 1 only (E2, D8).

The approvals queue and the two decisions a fleet admin can make. Nothing else from E2
exists: no connector-management routes (a key is pasted by a human during a concierge
call, per the kickoff's "build nothing you can fake with a pasted key"), no rules engine,
no dashboard.

**THE KEY IS NEVER IN A RESPONSE.** `key_last4` is the only part of a credential that
leaves this server, and no route here returns even that — connectors are not readable over
HTTP in slice 1 because nothing needs to read them yet.

AUTHORISATION IS THE FLEET'S, NOT THE DRIVER'S. Approving a claim invoices in the
carrier's name (D13), so it is management data and management action: the same
owner/dispatcher rule M12's report and claims desk already enforce, reached the same way.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import current_account, get_db, require_module
from app.foundation.f01_identity import public as identity
from app.foundation.f08_notifications import public as notify
from app.modules.m12_fleet import public as m12
from app.modules.m14_recovery import public as m14

router = APIRouter(
    prefix="/fleet",
    tags=["fleet-recovery"],
    # PRD §6: the module's own flag gates every route in it (§23 entry 105)
    dependencies=[Depends(require_module("m14_overlay"))],
)

_MANAGEMENT = (m12.FleetRole.owner, m12.FleetRole.dispatcher)


def _require_manager(db: Session, fleet_id: uuid.UUID, account: identity.Account) -> None:
    role = m12.member_role(db, fleet_id, account.id)
    if role not in _MANAGEMENT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "fleet management only")


def _serialize(held) -> dict:
    return {
        "hold_id": str(held.id),
        "claim_ref": str(held.claim_ref),
        "stop_ref": str(held.stop_ref),
        "account_id": str(held.account_id),
        # the pack's basis, DERIVED from the pings behind the claim — an admin approving
        # an `eld_derived` claim should know that is what they are sending
        "evidence_class": held.evidence_class,
        "state": held.state.value,
        # WHY it has not gone, when it has not gone. A queue that says "approved" while
        # nothing left is F-01's shape, and this is the field that prevents it.
        "send_blocked_by": held.send_blocked_by,
        "created_at": held.created_at,
    }


@router.get("/{fleet_id}/holds")
def list_holds(
    fleet_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_manager(db, fleet_id, account)
    holds = m14.held_claims(db, fleet_id)
    allowed, blocker = m14.can_send(db)
    return {
        "holds": [_serialize(h) for h in holds],
        # stated up front so the screen can warn BEFORE an admin approves, rather than
        # explaining afterwards why nothing happened
        "can_send": allowed,
        "send_blocked_by": blocker,
    }


@router.post("/{fleet_id}/holds/{hold_id}/approve")
def approve_hold(
    fleet_id: uuid.UUID,
    hold_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_manager(db, fleet_id, account)
    held = db.get(m14.HeldClaim, hold_id)
    if held is None or held.fleet_id != fleet_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "hold not found")
    try:
        m14.approve(db, held, account.id, gateway=notify.gateway_for(db, held.account_id))
    except m14.NotHeld as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _serialize(held)


@router.post("/{fleet_id}/holds/{hold_id}/reject")
def reject_hold(
    fleet_id: uuid.UUID,
    hold_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_manager(db, fleet_id, account)
    held = db.get(m14.HeldClaim, hold_id)
    if held is None or held.fleet_id != fleet_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "hold not found")
    try:
        m14.reject(db, held, account.id)
    except m14.NotHeld as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _serialize(held)
