import enum


class PriceSource(enum.Enum):
    feed = "feed"  # merchant-network feed / admin-set
    crowd = "crowd"  # F10 crowd-confirmed (keeps non-network honest, M7-FR5)


class FuelTxnState(enum.Enum):
    code_issued = "code_issued"  # pump code handed to the driver, awaiting the pump
    settled = "settled"  # merchant reconciled -> F7 spread entry posted
    canceled = "canceled"
