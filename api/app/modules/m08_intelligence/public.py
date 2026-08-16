"""AI-CONTEXT: Public interface for M8 Decision Intelligence.

The ONLY import surface other packages may use to reach M8 (import-linter
enforced). A schema-less serving layer that composes F3 + m01/m02/m03/m06/m07:
the true-profit calculator, appointment-hour optimizer, "where do I sleep
tonight" solver, parking-fill forecast, and detention-risk flag — every output
carries its basis. Runs behind the F13 flag m08_intelligence.
"""

from .domain.enums import Confidence, confidence_for
from .domain.service import (
    FLAG_KEY,
    MIN_SAMPLE,
    MODULE,
    PREACCEPT_FLAG,
    HourRec,
    ParkingForecast,
    ProfitResult,
    RiskFlag,
    SleepPlan,
    StopRec,
    appointment_hours,
    detention_risk_flag,
    expected_detention_cost,
    pre_acceptance,
    predict_parking,
    register_module,
    route_fuel_cost,
    true_profit,
    where_to_sleep,
)

__all__ = [
    "Confidence",
    "confidence_for",
    "FLAG_KEY",
    "MODULE",
    "HourRec",
    "ParkingForecast",
    "ProfitResult",
    "RiskFlag",
    "SleepPlan",
    "StopRec",
    "appointment_hours",
    "detention_risk_flag",
    "pre_acceptance",
    "PREACCEPT_FLAG",
    "MIN_SAMPLE",
    "expected_detention_cost",
    "predict_parking",
    "register_module",
    "route_fuel_cost",
    "true_profit",
    "where_to_sleep",
]
