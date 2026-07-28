"""AI-CONTEXT: Public interface for F4 Evidence Engine.

The ONLY import surface other packages may use to reach F4 (import-linter
enforced). Turns raw events into tamper-evident, hash-chained artifacts that
survive a dispute. Consumed by M3, M4, M5, M9, M12.
"""

from .domain.enums import ArtifactType, PackTemplate, RecordType
from .domain.models import (
    ChainAnchor,
    EvidenceArtifact,
    EvidenceLog,
    EvidenceRecord,
    SharedPack,
)
from .domain.render import PackContext
from .domain.service import (
    ChainVerification,
    EvidencePack,
    anchor_chain,
    append_record,
    attach_artifact,
    compose_grouped_pack,
    compose_pack,
    compose_stop_pack,
    create_log,
    get_artifact,
    render_pack_pdf,
    stop_evidence,
    verify_chain,
)
from .domain.sharing import (
    CONFIG_SHARE_DAYS,
    DEFAULT_SHARE_DAYS,
    ShareNotFound,
    extend_share,
    open_share,
    resolve_share,
    revoke_share,
    share_pack,
    shares_for_log,
)

__all__ = [
    "ChainAnchor",
    "EvidenceArtifact",
    "EvidenceLog",
    "EvidenceRecord",
    "SharedPack",
    "ShareNotFound",
    "CONFIG_SHARE_DAYS",
    "DEFAULT_SHARE_DAYS",
    "extend_share",
    "open_share",
    "resolve_share",
    "revoke_share",
    "share_pack",
    "shares_for_log",
    "ArtifactType",
    "PackTemplate",
    "RecordType",
    "ChainVerification",
    "EvidencePack",
    "PackContext",
    "anchor_chain",
    "append_record",
    "attach_artifact",
    "compose_pack",
    "compose_grouped_pack",
    "compose_stop_pack",
    "get_artifact",
    "stop_evidence",
    "create_log",
    "render_pack_pdf",
    "verify_chain",
]
