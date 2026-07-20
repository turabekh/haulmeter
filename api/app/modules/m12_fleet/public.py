"""AI-CONTEXT: Public interface for M12 Fleet & B2B Layer.

The ONLY import surface other packages may use to reach M12 (import-linter
enforced). Fleet workspace + consent-gated membership, parking benefits, the
fleet claims desk + counterparty analytics, fleet reporting rollups, the
aggregate-only data product (min-sample), and the TMS load-push/claim-status
surface. Runs behind the F13 flag m12_fleet.
"""

from .domain.enums import FleetRole, MembershipState
from .domain.models import BenefitUsage, DataSubscription, FleetMembership, ParkingBenefit
from .domain.service import (
    FLAG_KEY,
    MIN_BENCHMARK_SAMPLE,
    MODULE,
    Benchmark,
    ConsentRequired,
    FleetReport,
    MemberReport,
    NotSubscribed,
    accept_invite,
    benefit_remaining,
    claim_status,
    create_fleet,
    dwell_benchmark,
    fleet_claims_desk,
    fleet_report,
    invite_driver,
    is_subscribed,
    list_members,
    push_load,
    record_benefit_usage,
    register_module,
    remove_member,
    set_parking_benefit,
    subscribe_data,
)

__all__ = [
    "FleetRole",
    "MembershipState",
    "BenefitUsage",
    "DataSubscription",
    "FleetMembership",
    "ParkingBenefit",
    "FLAG_KEY",
    "MIN_BENCHMARK_SAMPLE",
    "MODULE",
    "Benchmark",
    "ConsentRequired",
    "FleetReport",
    "MemberReport",
    "NotSubscribed",
    "accept_invite",
    "benefit_remaining",
    "claim_status",
    "create_fleet",
    "dwell_benchmark",
    "fleet_claims_desk",
    "fleet_report",
    "invite_driver",
    "is_subscribed",
    "list_members",
    "push_load",
    "record_benefit_usage",
    "register_module",
    "remove_member",
    "set_parking_benefit",
    "subscribe_data",
]
