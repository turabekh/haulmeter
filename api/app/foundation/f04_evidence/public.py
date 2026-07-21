"""AI-CONTEXT: Public interface for F4 Evidence Engine.

The ONLY import surface other packages may use to reach F4 (import-linter
enforced). Turns raw events into tamper-evident, hash-chained artifacts that
survive a dispute. Consumed by M3, M4, M5, M9, M12.
"""

from .domain.enums import ArtifactType, PackTemplate, RecordType
from .domain.models import ChainAnchor, EvidenceArtifact, EvidenceLog, EvidenceRecord
from .domain.service import (
    ChainVerification,
    EvidencePack,
    RenderNotEnabled,
    anchor_chain,
    append_record,
    attach_artifact,
    compose_pack,
    create_log,
    render_pack_pdf,
    stop_evidence,
    verify_chain,
)

__all__ = [
    "ChainAnchor",
    "EvidenceArtifact",
    "EvidenceLog",
    "EvidenceRecord",
    "ArtifactType",
    "PackTemplate",
    "RecordType",
    "ChainVerification",
    "EvidencePack",
    "RenderNotEnabled",
    "anchor_chain",
    "append_record",
    "attach_artifact",
    "compose_pack",
    "stop_evidence",
    "create_log",
    "render_pack_pdf",
    "verify_chain",
]
