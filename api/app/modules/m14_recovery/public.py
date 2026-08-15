"""AI-CONTEXT: M14's public surface (PRD Extension E2, owner decision D8, slice 1).

Everything outside this module reaches M14 through here, and M14 reaches M3 through
`m03.public` only — never past it. The import-linter contract `m14_recovery-domain-private`
holds the first half; the spine contract holds the second.

What is deliberately NOT exported: the crypto helpers. A caller that can reach
`decrypt_key` can put a fleet's telematics credential on a screen or in a log, and no
caller outside this module has a reason to hold the plaintext — the poller decrypts it
inside `poll_connector` and it never leaves that call.
"""

from .domain.crypto import ConnectorKeyUnavailable
from .domain.enums import ConnectorStatus, EvidenceClass, HoldState, Provider
from .domain.models import Connector, HeldClaim, TraceImport, VehicleMap
from .domain.provider import Breadcrumb, FakeMotiveClient, MotiveClient, parse_vehicle_locations
from .domain.service import (
    FLAG_KEY,
    GATES,
    MODULE,
    SOURCE_PREFIX,
    IngestResult,
    NotHeld,
    active_connectors,
    approve,
    can_send,
    connect_fleet,
    draft_holds_for_events,
    evidence_class_for,
    held_claims,
    ingest_breadcrumbs,
    is_enabled,
    map_vehicle,
    poll_connector,
    provider_names,
    register_module,
    reject,
)

__all__ = [
    "FLAG_KEY",
    "GATES",
    "MODULE",
    "SOURCE_PREFIX",
    "Breadcrumb",
    "Connector",
    "ConnectorKeyUnavailable",
    "ConnectorStatus",
    "EvidenceClass",
    "FakeMotiveClient",
    "HeldClaim",
    "HoldState",
    "IngestResult",
    "NotHeld",
    "MotiveClient",
    "Provider",
    "TraceImport",
    "VehicleMap",
    "active_connectors",
    "approve",
    "can_send",
    "connect_fleet",
    "draft_holds_for_events",
    "evidence_class_for",
    "held_claims",
    "ingest_breadcrumbs",
    "is_enabled",
    "map_vehicle",
    "parse_vehicle_locations",
    "poll_connector",
    "provider_names",
    "register_module",
    "reject",
]
