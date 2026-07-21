"""AI-CONTEXT: Public interface for M5 Protection & Document Wallet.

The ONLY import surface other packages may use to reach M5 (import-linter
enforced). On-time proof, cargo-condition capture, document wallet + inspection
mode, incident capture, protection summary. Runs behind the F13 flag
m05_protection.
"""

from .domain.enums import CONDITION_SEQUENCE, INSPECTION_DOC_TYPES, CapturePhase
from .domain.models import ConditionCapture, Incident, OnTimeProof
from .domain.service import (
    FLAG_KEY,
    MODULE,
    add_condition_photo,
    add_incident_photo,
    capture_incident,
    condition_photo_count,
    condition_sequence,
    file_on_time_proof,
    incident_pack,
    inspection_mode,
    protection_summary,
    register_module,
    start_condition_capture,
    wallet,
)

__all__ = [
    "CONDITION_SEQUENCE",
    "INSPECTION_DOC_TYPES",
    "CapturePhase",
    "ConditionCapture",
    "Incident",
    "OnTimeProof",
    "FLAG_KEY",
    "MODULE",
    "add_condition_photo",
    "add_incident_photo",
    "capture_incident",
    "condition_photo_count",
    "condition_sequence",
    "file_on_time_proof",
    "incident_pack",
    "inspection_mode",
    "protection_summary",
    "register_module",
    "start_condition_capture",
    "wallet",
]
