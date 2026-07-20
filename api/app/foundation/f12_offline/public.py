"""AI-CONTEXT: Public interface for F12 Offline Sync & Outbox.

The ONLY import surface other packages may use to reach F12 (import-linter
enforced). The generic idempotent-ingest primitive: same (account,
idempotency_key) applied twice = one effect; server-authoritative received_at,
client occurred_at preserved. Consumed by every module.
"""

from .domain.models import SyncEnvelope
from .domain.service import SyncReceipt, get_receipt, ingest, list_for_account

__all__ = [
    "SyncEnvelope",
    "SyncReceipt",
    "get_receipt",
    "ingest",
    "list_for_account",
]
