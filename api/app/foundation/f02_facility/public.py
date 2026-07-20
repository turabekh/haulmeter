"""AI-CONTEXT: Public interface for F2 Canonical Facility Registry (keystone).

The ONLY import surface other packages may use to reach F2 (import-linter
enforced). Every module keys off facility_id; one physical location = one
canonical record forever. Consumed by every module.
"""
from .domain.enums import FacilityStatus, FacilityType, SourceKind
from .domain.models import Facility, FacilitySource
from .domain.service import (
    add_source,
    confirm_with_second_signal,
    coordinates,
    create_candidate_from_checkin,
    create_facility,
    find_duplicate_candidates,
    get_facility,
    merge_facilities,
    nearest,
    resolve_canonical,
)

__all__ = [
    "Facility",
    "FacilitySource",
    "FacilityStatus",
    "FacilityType",
    "SourceKind",
    "add_source",
    "confirm_with_second_signal",
    "coordinates",
    "create_candidate_from_checkin",
    "create_facility",
    "find_duplicate_candidates",
    "get_facility",
    "merge_facilities",
    "nearest",
    "resolve_canonical",
]
