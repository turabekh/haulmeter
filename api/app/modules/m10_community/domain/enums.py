import enum


class HandoffState(enum.Enum):
    open = "open"  # broadcast, awaiting a claimer
    claimed = "claimed"  # one nearby driver claimed it, en route
    confirmed = "confirmed"  # claimer's ENTER proved the handoff — both earn
    expired = "expired"  # nobody claimed / arrived in time
    canceled = "canceled"
