"""AI-CONTEXT: Public interface for M10 Community & Points Economy.

The ONLY import surface other packages may use to reach M10 (import-linter
enforced). The points economy (earn/redeem on the F7 points currency, funded
against the M6 take), the free-lot spot-handoff relay (geofence-proven both
ends), contributor reputation, and moderated facility Q&A. Runs behind the F13
flag m10_community.
"""

from .domain.enums import HandoffState
from .domain.models import ContributionLog, FacilityAnswer, FacilityQuestion, Handoff
from .domain.service import (
    CONFIG_EARN_PREFIX,
    EARN_RULES,
    FLAG_KEY,
    MODULE,
    RATE_LIMIT_PER_DAY,
    REDEEM_CENTS_PER_POINT,
    HandoffNotClaimable,
    InsufficientPoints,
    NotFreeLot,
    NotPresent,
    RateLimited,
    Reputation,
    answer_question,
    ask_question,
    award_contribution,
    book_with_points,
    broadcast_handoff,
    claim_handoff,
    confirm_handoff,
    leaderboard,
    list_questions,
    nearby_handoffs,
    points_balance,
    redeem_points,
    register_module,
    reputation,
)

__all__ = [
    "HandoffState",
    "ContributionLog",
    "FacilityAnswer",
    "FacilityQuestion",
    "Handoff",
    "CONFIG_EARN_PREFIX",
    "EARN_RULES",
    "FLAG_KEY",
    "MODULE",
    "RATE_LIMIT_PER_DAY",
    "REDEEM_CENTS_PER_POINT",
    "HandoffNotClaimable",
    "InsufficientPoints",
    "NotFreeLot",
    "NotPresent",
    "RateLimited",
    "Reputation",
    "answer_question",
    "ask_question",
    "award_contribution",
    "book_with_points",
    "broadcast_handoff",
    "claim_handoff",
    "confirm_handoff",
    "leaderboard",
    "list_questions",
    "nearby_handoffs",
    "points_balance",
    "redeem_points",
    "register_module",
    "reputation",
]
