"""AI-CONTEXT: Public interface for F2 Canonical Facility Registry (keystone).

The ONLY import surface other packages may use to reach F2 (import-linter
enforced). Every module keys off facility_id; one physical location = one
canonical record forever. Consumed by every module.
"""

from .domain.enums import FacilityStatus, FacilityType, SourceKind
from .domain.ingest import adapters as _adapters
from .domain.ingest.adapters import (
    LOW,
    SERVICE_KINDS,
    SERVICE_MOBILE_REPAIR,
    SERVICE_PARTS,
    SERVICE_REPAIR,
    SERVICE_SCALE,
    SERVICE_TIRE,
    SERVICE_TOWING,
    SERVICE_WASH,
    ChainLocatorAdapter,
    DynamicStatus,
    StagedRecord,
    derive_parking_status,
    has_usable_reading,
    iter_ntad_pages,
    osm_services,
    parse_ntad,
    parse_osm,
    parse_tpims_dynamic,
    parse_tpims_static,
)
from .domain.ingest.pipeline import (
    AMENITY_PRIORITY,
    CAPACITY_PRIORITY,
    UNION_KEYS,
    IngestStats,
    ingest_records,
    upsert_record,
)
from .domain.models import Facility, FacilitySource, SourceRecord
from .domain.service import (
    add_source,
    colocated_host,
    confirm_with_second_signal,
    contains_point,
    coordinates,
    create_candidate_from_checkin,
    create_facility,
    facility_for_source,
    find_duplicate_candidates,
    get_facility,
    in_bbox,
    merge_facilities,
    nearest,
    resolve_canonical,
    search_service_facilities,
    set_lot_polygon,
)

# the ingest adapters module, for live-fetch functions used by make-target scripts
ingest = _adapters

__all__ = [
    "SERVICE_MOBILE_REPAIR",
    "SERVICE_PARTS",
    "SERVICE_REPAIR",
    "SERVICE_SCALE",
    "SERVICE_TIRE",
    "SERVICE_TOWING",
    "SERVICE_WASH",
    "SERVICE_KINDS",
    "UNION_KEYS",
    "osm_services",
    "Facility",
    "FacilitySource",
    "SourceRecord",
    "FacilityStatus",
    "FacilityType",
    "SourceKind",
    "add_source",
    "confirm_with_second_signal",
    "contains_point",
    "coordinates",
    "create_candidate_from_checkin",
    "create_facility",
    "facility_for_source",
    "colocated_host",
    "find_duplicate_candidates",
    "get_facility",
    "in_bbox",
    "merge_facilities",
    "nearest",
    "resolve_canonical",
    "search_service_facilities",
    "set_lot_polygon",
    # --- ingestion (PRD §12) ---
    "ingest",
    "StagedRecord",
    "DynamicStatus",
    "LOW",
    "ChainLocatorAdapter",
    "parse_ntad",
    "parse_tpims_static",
    "parse_tpims_dynamic",
    "has_usable_reading",
    "parse_osm",
    "derive_parking_status",
    "iter_ntad_pages",
    "ingest_records",
    "upsert_record",
    "IngestStats",
    "AMENITY_PRIORITY",
    "CAPACITY_PRIORITY",
]
