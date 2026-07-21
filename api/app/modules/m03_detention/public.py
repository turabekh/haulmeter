"""AI-CONTEXT: Public interface for M3 Detention Tracker & Recovery.

The ONLY import surface other packages may use to reach M3 (import-linter
enforced). GPS-verified detention: clock math, evidence accrual, claim pack +
invoice + counterparty notices, dunning, escalation seam. Runs behind the F13
flag m03_detention (legal + collection-partner validation gates).
"""

from .domain.enums import ClaimMode, ClaimState, DetentionPhase, DetentionTrigger
from .domain.models import DetentionClaim
from .domain.service import (
    CONFIG_FREE_TIME_KEY,
    CONFIG_RATE_KEY,
    DEFAULT_FREE_TIME_MINUTES,
    DEFAULT_RATE_CENTS_PER_HOUR,
    DUNNING_DAYS,
    FLAG_KEY,
    GATES,
    MODULE,
    PRE_DETENTION_THRESHOLD,
    DetentionState,
    accrue_events,
    claim_evidence,
    claim_for_stop,
    clock,
    compute_detention,
    default_free_time_minutes,
    default_rate_cents_per_hour,
    dunning_schedule,
    escalate,
    generate_pack,
    get_claim,
    open_receivable,
    register_module,
    send_detention_start_notice,
    send_pre_detention_notice,
    start_claim,
)

__all__ = [
    "ClaimMode",
    "ClaimState",
    "DetentionPhase",
    "DetentionTrigger",
    "DetentionClaim",
    "CONFIG_FREE_TIME_KEY",
    "CONFIG_RATE_KEY",
    "DEFAULT_FREE_TIME_MINUTES",
    "DEFAULT_RATE_CENTS_PER_HOUR",
    "default_free_time_minutes",
    "default_rate_cents_per_hour",
    "DUNNING_DAYS",
    "FLAG_KEY",
    "GATES",
    "MODULE",
    "PRE_DETENTION_THRESHOLD",
    "DetentionState",
    "accrue_events",
    "claim_evidence",
    "claim_for_stop",
    "clock",
    "compute_detention",
    "dunning_schedule",
    "escalate",
    "generate_pack",
    "get_claim",
    "open_receivable",
    "register_module",
    "send_detention_start_notice",
    "send_pre_detention_notice",
    "start_claim",
]
