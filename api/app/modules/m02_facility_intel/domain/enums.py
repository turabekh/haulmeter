import enum


class ReviewStatus(enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# design/PRD M2-FR1: structured 10-aspect driver ratings
RATING_ASPECTS = [
    "check_in_speed",
    "staff_courtesy",
    "cleanliness",
    "restrooms",
    "overnight_parking",
    "backing_difficulty",
    "dock_availability",
    "safety",
    "amenities",
    "would_return",
]
