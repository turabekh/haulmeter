"""AI-CONTEXT: M12 Fleet & B2B HTTP endpoints — thin over m12_fleet.public. The
fleet workspace (consent-gated), reporting rollups + claims desk, and the
aggregate-only data product. These back the web-first Fleet Workspace portal
(design-prd §18), not the driver phone app.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import canonical_facility_id, current_account, get_db
from app.foundation.f01_identity import public as identity
from app.modules.m12_fleet import public as m12

router = APIRouter(prefix="/fleet", tags=["fleet"])

_MANAGEMENT = (m12.FleetRole.owner, m12.FleetRole.dispatcher)


def _require_manager(db: Session, fleet_id: uuid.UUID, account: identity.Account) -> None:
    # fleet-wide money + roster is management data: only an active owner/dispatcher
    # of THIS fleet may read the report/claims or invite (403 for anyone else)
    role = m12.member_role(db, fleet_id, account.id)
    if role not in _MANAGEMENT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "fleet management only")


class CreateFleetIn(BaseModel):
    name: str


class InviteIn(BaseModel):
    driver_account_id: uuid.UUID


@router.post("", status_code=201)
def create_fleet(
    body: CreateFleetIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    org, membership = m12.create_fleet(db, account.id, body.name, now=datetime.now(UTC))
    return {"fleet_id": str(org.id), "role": membership.role.value}


@router.get("/mine")
def my_fleets(
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> list[dict]:
    return [
        {"fleet_id": str(f["fleet_id"]), "name": f["name"], "role": f["role"]}
        for f in m12.list_fleets_for(db, account.id)
    ]


@router.post("/{fleet_id}/invite", status_code=201)
def invite(
    fleet_id: uuid.UUID,
    body: InviteIn,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_manager(db, fleet_id, account)
    m = m12.invite_driver(db, fleet_id, body.driver_account_id)
    return {"membership_id": str(m.id), "state": m.state.value}


@router.get("/{fleet_id}/report")
def report(
    fleet_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_manager(db, fleet_id, account)
    r = m12.fleet_report(db, fleet_id)
    return {
        "driver_count": r.driver_count,
        "recovered_cents": r.recovered_cents,
        "owed_cents": r.owed_cents,
        "fuel_saved_cents": r.fuel_saved_cents,
        "members": [
            {
                "driver_account_id": str(m.driver_account_id),
                "recovered_cents": m.recovered_cents,
                "owed_cents": m.owed_cents,
                "fuel_saved_cents": m.fuel_saved_cents,
            }
            for m in r.members
        ],
    }


@router.get("/{fleet_id}/claims")
def claims_desk(
    fleet_id: uuid.UUID,
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    _require_manager(db, fleet_id, account)
    return m12.fleet_claims_desk(db, fleet_id)


@router.get("/benchmark/{facility_id}")
def benchmark(
    subscriber_ref: str,
    facility_id: uuid.UUID = Depends(canonical_facility_id),
    account: identity.Account = Depends(current_account),
    db: Session = Depends(get_db),
) -> dict:
    try:
        bench = m12.dwell_benchmark(db, facility_id, subscriber_ref)
    except m12.NotSubscribed as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "data subscription required") from exc
    if bench is None:
        # suppressed below the minimum sample — never expose a small sample (§13)
        return {"facility_id": str(facility_id), "suppressed": True, "reason": "min_sample"}
    return {
        "facility_id": str(bench.facility_id),
        "median_seconds": bench.median_seconds,
        "p90_seconds": bench.p90_seconds,
        "sample_size": bench.sample_size,
        "basis": bench.basis,
    }
