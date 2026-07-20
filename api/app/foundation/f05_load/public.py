"""AI-CONTEXT: Public interface for F5 Load & Stop Context.

The ONLY import surface other packages may use to reach F5 (import-linter
enforced). The Stop is the unit around which F3 geofencing arms and F4 evidence
accrues; arm_stop wires both. Claims are worthless without this contractual
context. Consumed by M3, M4, M5, M8, M9, M11, M12.
"""

from .domain.enums import (
    CounterpartyKind,
    LoadSource,
    LoadStatus,
    StopStatus,
    StopType,
)
from .domain.models import Counterparty, Load, Stop
from .domain.service import (
    FacilityNotFound,
    add_stop,
    arm_stop,
    create_counterparty,
    create_load,
    create_load_from_parsed_terms,
    disarm_stop,
    effective_detention_terms,
    get_counterparty,
    get_load,
    get_stop,
    list_stops,
    record_claim,
    record_payment_observation,
    set_load_status,
)

__all__ = [
    "Counterparty",
    "Load",
    "Stop",
    "CounterpartyKind",
    "LoadSource",
    "LoadStatus",
    "StopStatus",
    "StopType",
    "FacilityNotFound",
    "add_stop",
    "arm_stop",
    "create_counterparty",
    "create_load",
    "create_load_from_parsed_terms",
    "disarm_stop",
    "effective_detention_terms",
    "get_counterparty",
    "get_load",
    "get_stop",
    "list_stops",
    "record_claim",
    "record_payment_observation",
    "set_load_status",
]
