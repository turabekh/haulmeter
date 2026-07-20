import enum


class DiscrepancyStatus(enum.Enum):
    flagged = "flagged"  # auditor found missed pay, driver hasn't acted
    submitted = "submitted"  # sent to the carrier for review
    resolved = "resolved"  # carrier paid or driver dismissed
