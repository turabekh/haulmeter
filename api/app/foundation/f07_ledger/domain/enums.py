import enum


class Currency(enum.Enum):
    usd = "usd"
    points = "points"


class LedgerAccountKind(enum.Enum):
    driver_cash = "driver_cash"
    driver_payable = "driver_payable"
    owner_payable = "owner_payable"
    claim_receivable = "claim_receivable"
    platform_revenue = "platform_revenue"
    contingency_revenue = "contingency_revenue"
    fuel_clearing = "fuel_clearing"
    cash_clearing = "cash_clearing"
    points_balance = "points_balance"
    points_pool = "points_pool"


class Direction(enum.Enum):
    debit = "debit"
    credit = "credit"


class EntryType(enum.Enum):
    booking_payment = "booking_payment"
    owner_payout = "owner_payout"
    claim_recovery = "claim_recovery"
    contingency_fee = "contingency_fee"
    fuel_txn = "fuel_txn"
    points_earn = "points_earn"
    points_redeem = "points_redeem"
    adjustment = "adjustment"


class ReceivableKind(enum.Enum):
    detention = "detention"
    tonu = "tonu"
    layover = "layover"
    lumper = "lumper"
    # AI-CONTEXT: the platform's contingency share (J1-R1, §23 entry 172). The first kind
    # that points the OTHER WAY — the four above are money a broker owes a driver, this is
    # money the driver owes the platform out of a recovery already in their own bank. The
    # direction lives in the kind rather than in a sign on the amount: a negative
    # receivable would make every existing sum quietly wrong.
    fee = "fee"


class ReceivableState(enum.Enum):
    invoiced = "invoiced"
    acknowledged = "acknowledged"
    disputed = "disputed"
    escalated = "escalated"
    recovered = "recovered"
    written_off = "written_off"
