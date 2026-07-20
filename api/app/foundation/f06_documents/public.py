"""AI-CONTEXT: Public interface for F6 Documents Service.

The ONLY import surface other packages may use to reach F6 (import-linter
enforced). Typed document storage with OCR/F9 extraction and a 30/14/3-day
expiry engine (send via F8). Consumed by M3, M4, M5, M6, M9, M12.
"""
from .domain.enums import DocType, ExtractionStatus
from .domain.models import Document
from .domain.service import (
    REMINDER_OFFSETS,
    active_reminder_offset,
    apply_extraction,
    documents_for_account,
    due_reminders,
    get_document_bytes,
    mark_extraction_failed,
    mark_reminder_sent,
    store_document,
)
from .domain.storage import (
    InMemoryObjectStorage,
    MinioObjectStorage,
    ObjectStorage,
    default_storage,
    set_default_storage,
)

__all__ = [
    "Document",
    "DocType",
    "ExtractionStatus",
    "REMINDER_OFFSETS",
    "active_reminder_offset",
    "apply_extraction",
    "documents_for_account",
    "due_reminders",
    "get_document_bytes",
    "mark_extraction_failed",
    "mark_reminder_sent",
    "store_document",
    "ObjectStorage",
    "InMemoryObjectStorage",
    "MinioObjectStorage",
    "default_storage",
    "set_default_storage",
]
