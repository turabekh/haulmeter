"""AI-CONTEXT: Public interface for M7 Fuel Savings Network.

The ONLY import surface other packages may use to reach M7 (import-linter
enforced). Merchant network + per-station net pricing, the net-price corridor
(imports m01), in-app pump code + F7 spread settlement (payment-partner seam),
crowd price confirmation (F10), and driver savings analytics. Runs behind the
F13 flag m07_fuel (merchant-agreement + payment-partner gates).
"""

from .domain.enums import FuelTxnState, PriceSource
from .domain.models import FuelTransaction, Merchant, StationPricing
from .domain.service import (
    DEFAULT_GALLONS,
    FLAG_KEY,
    GATES,
    MODULE,
    DriverFuelAnalytics,
    FuelStop,
    NotAFuelPartner,
    confirm_price,
    corridor_fuel,
    driver_analytics,
    issue_pump_code,
    net_cents_per_gal,
    register_merchant,
    register_module,
    set_station_pricing,
    settle,
)

__all__ = [
    "FuelTxnState",
    "PriceSource",
    "FuelTransaction",
    "Merchant",
    "StationPricing",
    "DEFAULT_GALLONS",
    "FLAG_KEY",
    "GATES",
    "MODULE",
    "DriverFuelAnalytics",
    "FuelStop",
    "NotAFuelPartner",
    "confirm_price",
    "corridor_fuel",
    "driver_analytics",
    "issue_pump_code",
    "net_cents_per_gal",
    "register_merchant",
    "register_module",
    "set_station_pricing",
    "settle",
]
