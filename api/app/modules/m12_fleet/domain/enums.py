import enum


class FleetRole(enum.Enum):
    owner = "owner"
    dispatcher = "dispatcher"
    driver = "driver"


class MembershipState(enum.Enum):
    invited = "invited"  # invite sent, awaiting the driver's explicit consent
    active = "active"  # consented — their data is in fleet views
    removed = "removed"
