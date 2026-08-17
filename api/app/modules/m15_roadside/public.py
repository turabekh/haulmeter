"""AI-CONTEXT: M15's public surface (PRD Extension E3, owner decision D14, Session A).

Everything outside this module reaches M15 through here. Two import-linter contracts hold
the boundary and they are not the same contract:

· the spine contract places `m15_roadside` above `m14_recovery`, so m15 may reach earlier
  modules' `.public` and nothing may reach back into m15;
· **`m15-does-not-import-m14`** forbids the whole `app.modules.m14_recovery` package, not
  merely its `.domain`. E3 states the general rule ("earlier modules' `.public` only") and
  then carves M14 out of it — "**M14 is not imported**" (§E3.1.4). A conventional
  domain-private contract would still have permitted `m14_recovery.public`, which is
  exactly what the document forbids.

M15 shares nothing with M14 beyond the platform. They are neighbours in the module list
and strangers in the import graph, deliberately.
"""

from .domain.content import (
    ContentNotReviewed,
    HoldoutLeak,
    mark_reviewed,
    reassessment_variants,
    release,
    teachable_variants,
)
from .domain.enums import (
    ContentStatus,
    Difficulty,
    EntitlementKind,
    EntitlementSource,
    SessionMode,
    Speaker,
    TurnReviewStatus,
)
from .domain.models import (
    CoachingContent,
    DrillPlan,
    Entitlement,
    Intent,
    ModelAnswer,
    OfficerAck,
    PhraseVariant,
    ReviewSample,
    ScenarioVersion,
    Session,
    SignItem,
    SkillState,
    TrainingRecord,
    Turn,
)
from .domain.service import (
    FLAG_KEY,
    MODULE,
    claim_guest_sessions,
    is_enabled,
    register_module,
)

__all__ = [
    "ContentNotReviewed",
    "HoldoutLeak",
    "mark_reviewed",
    "reassessment_variants",
    "release",
    "teachable_variants",
    "FLAG_KEY",
    "MODULE",
    "CoachingContent",
    "ModelAnswer",
    "OfficerAck",
    "ContentStatus",
    "Difficulty",
    "DrillPlan",
    "Entitlement",
    "EntitlementKind",
    "EntitlementSource",
    "Intent",
    "PhraseVariant",
    "ReviewSample",
    "ScenarioVersion",
    "Session",
    "SessionMode",
    "SignItem",
    "SkillState",
    "Speaker",
    "TrainingRecord",
    "Turn",
    "TurnReviewStatus",
    "claim_guest_sessions",
    "is_enabled",
    "register_module",
]
