import enum


class ModerationStatus(enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
