"""AI-CONTEXT: Public interface for F10 Crowd Data Pipeline.

The ONLY import surface other packages may use to reach F10 (import-linter
enforced). Geofence-presence-gated submissions, trust scoring, per-signal time
decay, trust+decay-weighted "current best belief" aggregation, and points
issuance into the F7 closed-loop ledger. Consumed by M1, M2, M7, M10.
"""

from .domain.enums import SignalType
from .domain.models import Belief, ContributorTrust, Submission
from .domain.service import (
    CONFIG_AWARD_COOLDOWN_KEY,
    DEFAULT_AWARD_COOLDOWN_SECONDS,
    HALF_LIFE_SECONDS,
    POINTS_PER_SIGNAL,
    BeliefResult,
    FacilityNotFound,
    adjust_trust,
    aggregate_belief,
    get_belief,
    get_or_create_trust,
    issue_points,
    submit,
    submit_authoritative,
    update_belief,
)

__all__ = [
    "SignalType",
    "Belief",
    "ContributorTrust",
    "Submission",
    "CONFIG_AWARD_COOLDOWN_KEY",
    "DEFAULT_AWARD_COOLDOWN_SECONDS",
    "HALF_LIFE_SECONDS",
    "POINTS_PER_SIGNAL",
    "BeliefResult",
    "FacilityNotFound",
    "adjust_trust",
    "aggregate_belief",
    "get_belief",
    "get_or_create_trust",
    "issue_points",
    "submit",
    "submit_authoritative",
    "update_belief",
]
