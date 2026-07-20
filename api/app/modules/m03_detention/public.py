"""AI-CONTEXT: Public interface for M3 Detention Tracker & Recovery.

The ONLY import surface other packages may use to reach M3 (import-linter
enforced). GPS-verified detention: clock math, evidence accrual, claim pack +
invoice + counterparty notices, dunning, escalation seam. Runs behind the F13
flag m03_detention (legal + collection-partner validation gates).
"""

from .domain.enums import ClaimMode, ClaimState, DetentionPhase, DetentionTrigger
from .domain.models import DetentionClaim
from .domain.service import (
    DUNNING_DAYS,
    FLAG_KEY,
    GATES,
    MODULE,
    PRE_DETENTION_THRESHOLD,
    DetentionState,
    accrue_events,
    claim_for_stop,
    clock,
    compute_detention,
    dunning_schedule,
    escalate,
    generate_pack,
    get_claim,
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
    "DUNNING_DAYS",
    "FLAG_KEY",
    "GATES",
    "MODULE",
    "PRE_DETENTION_THRESHOLD",
    "DetentionState",
    "accrue_events",
    "claim_for_stop",
    "clock",
    "compute_detention",
    "dunning_schedule",
    "escalate",
    "generate_pack",
    "get_claim",
    "register_module",
    "send_detention_start_notice",
    "send_pre_detention_notice",
    "start_claim",
]
