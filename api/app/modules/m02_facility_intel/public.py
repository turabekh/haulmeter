"""AI-CONTEXT: Public interface for M2 Facility Intelligence & Scorecard.

The ONLY import surface other packages may use to reach M2 (import-linter
enforced). Facility profiles, objective dwell stats, moderated structured
reviews, semantic search. Runs behind the F13 flag m02_facility_intel.
"""

from .domain.enums import RATING_ASPECTS, ReviewStatus
from .domain.models import FacilityProfile, FacilityReview
from .domain.service import (
    FLAG_KEY,
    MODULE,
    REVIEW_POINTS,
    FacilityNotFound,
    InvalidRatings,
    NotFactualField,
    ParsedDwell,
    aggregate_ratings,
    dwell_stats,
    get_or_create_profile,
    list_reviews,
    moderate_review,
    register_module,
    search_reviews,
    submit_review,
    update_factual_attributes,
)

__all__ = [
    "RATING_ASPECTS",
    "ReviewStatus",
    "FacilityProfile",
    "FacilityReview",
    "FLAG_KEY",
    "MODULE",
    "REVIEW_POINTS",
    "FacilityNotFound",
    "InvalidRatings",
    "NotFactualField",
    "ParsedDwell",
    "aggregate_ratings",
    "dwell_stats",
    "get_or_create_profile",
    "list_reviews",
    "moderate_review",
    "register_module",
    "search_reviews",
    "submit_review",
    "update_factual_attributes",
]
