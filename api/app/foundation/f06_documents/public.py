"""AI-CONTEXT: Public interface for F6 Documents Service.

The ONLY import surface other packages may use to reach F6 (import-linter
enforced). Typed document storage with OCR/F9 extraction and a 30/14/3-day
expiry engine (send via F8). Consumed by M3, M4, M5, M6, M9, M12.
"""

from .domain.audio import (
    AUDIO_CONTENT_TYPES,
    InvalidRange,
    UnsupportedAudioType,
    content_range_header,
    is_audio,
    parse_range,
    require_audio,
)
from .domain.enums import DocType, ExtractionStatus, RetentionClass
from .domain.models import Document
from .domain.retention import (
    AUDIO_TTL,
    RetentionClassRefused,
    bytes_available,
    classify_audio_30d,
    delete_bytes,
    due_for_sweep,
    sweep,
)
from .domain.service import (
    ARCHIVE_REMOVED,
    ARCHIVE_SUPERSEDED,
    REMINDER_OFFSETS,
    active_reminder_offset,
    apply_extraction,
    archive_document,
    documents_for_account,
    documents_for_subject,
    due_reminders,
    get_document_bytes,
    mark_extraction_failed,
    mark_reminder_sent,
    restore_document,
    set_document_subject,
    store_document,
    supersede_document,
    update_document_meta,
)
from .domain.storage import (
    InMemoryObjectStorage,
    MinioObjectStorage,
    ObjectStorage,
    default_storage,
    is_missing_object,
    set_default_storage,
)
from .domain.thumbnails import (
    THUMB_CONTENT_TYPE,
    THUMB_EDGE,
    make_thumbnail,
    thumbnail_key,
)

__all__ = [
    "AUDIO_CONTENT_TYPES",
    "AUDIO_TTL",
    "InvalidRange",
    "RetentionClass",
    "RetentionClassRefused",
    "UnsupportedAudioType",
    "bytes_available",
    "classify_audio_30d",
    "content_range_header",
    "delete_bytes",
    "due_for_sweep",
    "is_audio",
    "parse_range",
    "require_audio",
    "sweep",
    "THUMB_CONTENT_TYPE",
    "THUMB_EDGE",
    "make_thumbnail",
    "thumbnail_key",
    "Document",
    "DocType",
    "ExtractionStatus",
    "ARCHIVE_REMOVED",
    "ARCHIVE_SUPERSEDED",
    "REMINDER_OFFSETS",
    "active_reminder_offset",
    "apply_extraction",
    "archive_document",
    "restore_document",
    "set_document_subject",
    "documents_for_account",
    "documents_for_subject",
    "due_reminders",
    "get_document_bytes",
    "mark_extraction_failed",
    "mark_reminder_sent",
    "store_document",
    "supersede_document",
    "update_document_meta",
    "ObjectStorage",
    "InMemoryObjectStorage",
    "MinioObjectStorage",
    "default_storage",
    "is_missing_object",
    "set_default_storage",
]
