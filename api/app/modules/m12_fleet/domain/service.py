"""AI-CONTEXT: M12 Fleet & B2B Layer (PRD §8.12) — the multiplier: fleet accounts
that buy per-seat, and the aggregated data product the industry argues about.
Owns schema m12. The LAST module — it multiplies everything before it.

- Fleet workspace (M12-FR1): a fleet IS an F1 Organization (type=fleet); M12
  owns membership so it can require EXPLICIT consent before a driver's data
  enters any fleet view. Consent is the gate on every rollup below.
- Parking benefits (M12-FR2): monthly per-driver allowance + policy; usage
  tracked against it (completes M6-FR8).
- Fleet claims desk (M12-FR3): the M3/M4 receivable pipeline across members,
  plus counterparty analytics (which brokers actually pay).
- Fleet reporting (M12-FR4): recovered $, fuel savings, dwell exposure per
  driver and fleet-wide.
- Data product (M12-FR5): aggregate, anonymized facility dwell benchmarks —
  minimum-sample thresholds, NEVER identifiable driver data (hard policy §13).
- TMS/webhook (M12-FR6): load push into F5, claim status out — a surface, not
  a TMS.

Composes f01 + f05 + f07 + m02 + m04 + m07. Runs behind the F13 flag m12_fleet.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f01_identity import public as identity
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.modules.m02_facility_intel import public as m2
from app.modules.m04_accessorial import public as m4
from app.modules.m07_fuel import public as m7

from .enums import FleetRole, MembershipState
from .models import BenefitUsage, DataSubscription, FleetMembership, ParkingBenefit

FLAG_KEY = "m12_fleet"
MODULE = "m12"
# data-product privacy (M12-FR5 / §13): never publish a benchmark below this
MIN_BENCHMARK_SAMPLE = 5
_SETTLED = {"recovered", "written_off"}


class NotSubscribed(Exception):
    pass


class ConsentRequired(Exception):
    pass


@dataclass
class MemberReport:
    driver_account_id: object
    recovered_cents: int
    owed_cents: int
    fuel_saved_cents: int


@dataclass
class FleetReport:
    members: list[MemberReport]
    recovered_cents: int
    owed_cents: int
    fuel_saved_cents: int
    driver_count: int


@dataclass
class Benchmark:
    facility_id: object
    median_seconds: int
    p90_seconds: int
    sample_size: int
    basis: str = "aggregate"


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags
    from app.foundation.f14_admin import public as admin

    flags.register_flag(db, FLAG_KEY, description="M12 Fleet & B2B Layer", default_on=True)
    admin.register_admin_view(db, "m12.fleet", MODULE, "Fleet & Data", "/admin/m12/fleet")


# --- Fleet workspace + consent (M12-FR1) ---
def create_fleet(db: Session, owner_account_id, name: str, now: datetime | None = None):
    org = identity.create_organization(db, identity.OrgType.fleet, name)
    membership = FleetMembership(
        fleet_org_id=org.id,
        driver_account_id=owner_account_id,
        role=FleetRole.owner,
        consent=True,
        state=MembershipState.active,
        joined_at=now,
    )
    db.add(membership)
    db.flush()
    return org, membership


def invite_driver(
    db: Session, fleet_org_id, driver_account_id, role: FleetRole = FleetRole.driver
) -> FleetMembership:
    membership = FleetMembership(
        fleet_org_id=fleet_org_id,
        driver_account_id=driver_account_id,
        role=role,
        consent=False,
        state=MembershipState.invited,
    )
    db.add(membership)
    db.flush()
    return membership


def accept_invite(db: Session, membership: FleetMembership, now: datetime) -> FleetMembership:
    # explicit consent at join (M12-FR1) — before this, no fleet view sees them
    membership.consent = True
    membership.state = MembershipState.active
    membership.joined_at = now
    db.flush()
    return membership


def remove_member(db: Session, membership: FleetMembership) -> FleetMembership:
    membership.state = MembershipState.removed
    db.flush()
    return membership


def list_fleets_for(db: Session, account_id) -> list[dict]:
    # the fleets this account belongs to (owner/dispatcher/driver), with F1 names
    out = []
    for m in db.scalars(
        select(FleetMembership).where(
            FleetMembership.driver_account_id == account_id,
            FleetMembership.state == MembershipState.active,
        )
    ):
        org = db.get(identity.Organization, m.fleet_org_id)
        out.append(
            {"fleet_id": m.fleet_org_id, "name": org.name if org else None, "role": m.role.value}
        )
    return out


def member_role(db: Session, fleet_org_id, account_id) -> FleetRole | None:
    # the account's role in the fleet if an ACTIVE member, else None. Backs the
    # API authz gate: only management (owner/dispatcher) sees fleet-wide money.
    membership = db.scalars(
        select(FleetMembership).where(
            FleetMembership.fleet_org_id == fleet_org_id,
            FleetMembership.driver_account_id == account_id,
            FleetMembership.state == MembershipState.active,
        )
    ).first()
    return membership.role if membership else None


def list_members(db: Session, fleet_org_id, consented_only: bool = True) -> list[FleetMembership]:
    stmt = select(FleetMembership).where(FleetMembership.fleet_org_id == fleet_org_id)
    if consented_only:
        stmt = stmt.where(
            FleetMembership.state == MembershipState.active, FleetMembership.consent.is_(True)
        )
    return list(db.scalars(stmt))


def _member_ids(db: Session, fleet_org_id) -> list:
    # the ONLY driver ids whose data may enter a fleet view — consent-gated
    return [m.driver_account_id for m in list_members(db, fleet_org_id, consented_only=True)]


# --- Fleet reporting (M12-FR4) ---
def fleet_report(db: Session, fleet_org_id) -> FleetReport:
    members: list[MemberReport] = []
    for account_id in _member_ids(db, fleet_org_id):
        rows = m4.money_owed(db, account_id)
        recovered = sum(r["amount_cents"] for r in rows if r["state"] == "recovered")
        owed = sum(r["amount_cents"] for r in rows if r["state"] not in _SETTLED)
        fuel = m7.driver_analytics(db, account_id).savings_cents
        members.append(MemberReport(account_id, recovered, owed, fuel))
    return FleetReport(
        members=members,
        recovered_cents=sum(m.recovered_cents for m in members),
        owed_cents=sum(m.owed_cents for m in members),
        fuel_saved_cents=sum(m.fuel_saved_cents for m in members),
        driver_count=len(members),
    )


# --- Fleet claims desk + counterparty analytics (M12-FR3) ---
def fleet_claims_desk(db: Session, fleet_org_id) -> dict:
    owed = recovered = 0
    by_counterparty: dict[str, dict] = {}
    for account_id in _member_ids(db, fleet_org_id):
        for r in ledger.list_receivables(db, account_id):
            amount = r.amount_cents
            is_recovered = r.state == ledger.ReceivableState.recovered
            owed += (
                0
                if r.state in (ledger.ReceivableState.recovered, ledger.ReceivableState.written_off)
                else amount
            )
            recovered += amount if is_recovered else 0
            key = str(r.counterparty_ref) if r.counterparty_ref else "unknown"
            cp = by_counterparty.setdefault(
                key, {"name": None, "owed": 0, "recovered": 0, "total": 0}
            )
            cp["total"] += amount
            cp["recovered"] += amount if is_recovered else 0
            if not is_recovered and r.state != ledger.ReceivableState.written_off:
                cp["owed"] += amount
    for key, cp in by_counterparty.items():
        cp["recovery_rate"] = round(cp["recovered"] / cp["total"], 3) if cp["total"] else 0.0
        # resolve the F5 counterparty UUID to the broker's name (the desk shows
        # who actually pays — a UUID is useless to a fleet manager, M12-FR3)
        if key != "unknown":
            counterparty = loads.get_counterparty(db, uuid.UUID(key))
            cp["name"] = counterparty.name if counterparty is not None else None
    return {
        "owed_cents": owed,
        "recovered_cents": recovered,
        "by_counterparty": by_counterparty,
    }


# --- Parking benefits (M12-FR2) ---
def set_parking_benefit(
    db: Session, fleet_org_id, monthly_allowance_cents: int, policy: dict | None = None
) -> ParkingBenefit:
    benefit = db.scalar(select(ParkingBenefit).where(ParkingBenefit.fleet_org_id == fleet_org_id))
    if benefit is None:
        benefit = ParkingBenefit(fleet_org_id=fleet_org_id)
        db.add(benefit)
    benefit.monthly_allowance_cents = monthly_allowance_cents
    benefit.policy = policy or {}
    db.flush()
    return benefit


def record_benefit_usage(
    db: Session, fleet_org_id, driver_account_id, month: date, cents: int
) -> BenefitUsage:
    usage = db.scalar(
        select(BenefitUsage).where(
            BenefitUsage.fleet_org_id == fleet_org_id,
            BenefitUsage.driver_account_id == driver_account_id,
            BenefitUsage.month == month,
        )
    )
    if usage is None:
        usage = BenefitUsage(
            fleet_org_id=fleet_org_id,
            driver_account_id=driver_account_id,
            month=month,
            spent_cents=0,
        )
        db.add(usage)
    usage.spent_cents += cents
    db.flush()
    return usage


def benefit_remaining(db: Session, fleet_org_id, driver_account_id, month: date) -> int:
    benefit = db.scalar(select(ParkingBenefit).where(ParkingBenefit.fleet_org_id == fleet_org_id))
    allowance = benefit.monthly_allowance_cents if benefit else 0
    usage = db.scalar(
        select(BenefitUsage).where(
            BenefitUsage.fleet_org_id == fleet_org_id,
            BenefitUsage.driver_account_id == driver_account_id,
            BenefitUsage.month == month,
        )
    )
    spent = usage.spent_cents if usage else 0
    return max(0, allowance - spent)


# --- Data product (M12-FR5) — aggregate-only, min-sample, never identifiable ---
def subscribe_data(db: Session, subscriber_ref: str, tier: str = "standard") -> DataSubscription:
    sub = db.scalar(
        select(DataSubscription).where(DataSubscription.subscriber_ref == subscriber_ref)
    )
    if sub is None:
        sub = DataSubscription(subscriber_ref=subscriber_ref, tier=tier)
        db.add(sub)
    sub.active = True
    db.flush()
    return sub


def is_subscribed(db: Session, subscriber_ref: str) -> bool:
    sub = db.scalar(
        select(DataSubscription).where(DataSubscription.subscriber_ref == subscriber_ref)
    )
    return bool(sub and sub.active)


def dwell_benchmark(db: Session, facility_id, subscriber_ref: str) -> Benchmark | None:
    if not is_subscribed(db, subscriber_ref):
        raise NotSubscribed(subscriber_ref)
    stats = m2.dwell_stats(db, facility_id).overall
    # hard privacy floor: suppress anything that could expose a small sample
    if stats["sample_size"] < MIN_BENCHMARK_SAMPLE:
        return None
    return Benchmark(
        facility_id=facility_id,
        median_seconds=int(stats["median_seconds"]),
        p90_seconds=int(stats["p90_seconds"]),
        sample_size=stats["sample_size"],
    )


# --- TMS / webhook (M12-FR6) — integration surface, not a TMS ---
def push_load(
    db: Session,
    account_id,
    external_ref: str,
    rate_cents: int | None = None,
    detention_rate_cents_per_hour: int | None = None,
    free_time_minutes: int | None = None,
):
    return loads.create_load(
        db,
        account_id,
        reference_number=external_ref,
        rate_cents=rate_cents,
        detention_rate_cents_per_hour=detention_rate_cents_per_hour,
        free_time_minutes=free_time_minutes,
        source=loads.LoadSource.tms_push,
    )


def claim_status(db: Session, account_id) -> list[dict]:
    # claim status OUT: the M3/M4 receivable pipeline for a member
    return [
        {"kind": r["kind"], "state": r["state"], "amount_cents": r["amount_cents"]}
        for r in m4.money_owed(db, account_id)
    ]
