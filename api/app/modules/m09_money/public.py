"""AI-CONTEXT: Public interface for M9 Driver Money & Tax Tools.

The ONLY import surface other packages may use to reach M9 (import-linter
enforced). The settlement auditor (F9 parse seam + reconciliation vs the
driver's M3/M4 receivables), the earnings/North-Star DDD dashboard (M3/M4 + M7),
expense capture-lite (F6), and the IFTA + per-diem seams (basis surfaced). Runs
behind the F13 flag m09_money.
"""

from .domain.enums import DiscrepancyStatus
from .domain.models import Discrepancy, ExpenseReceipt, Settlement, SettlementLine
from .domain.service import (
    AUDITABLE_KINDS,
    CLAIM_PAID_CATEGORY,
    FLAG_KEY,
    MODULE,
    SETTLEMENT_PROMPT,
    EarningsSummary,
    ExpenseSummary,
    IftaSummary,
    PerDiemResult,
    SettlementNotParsed,
    add_receipt,
    audit_settlement,
    earnings_dashboard,
    expense_summary,
    ifta_summary,
    mark_receivable_paid,
    parse_settlement_lines,
    per_diem_days,
    register_module,
    upload_settlement,
)

__all__ = [
    "DiscrepancyStatus",
    "Discrepancy",
    "ExpenseReceipt",
    "Settlement",
    "SettlementLine",
    "AUDITABLE_KINDS",
    "CLAIM_PAID_CATEGORY",
    "FLAG_KEY",
    "MODULE",
    "SETTLEMENT_PROMPT",
    "EarningsSummary",
    "ExpenseSummary",
    "IftaSummary",
    "PerDiemResult",
    "SettlementNotParsed",
    "add_receipt",
    "audit_settlement",
    "earnings_dashboard",
    "expense_summary",
    "ifta_summary",
    "mark_receivable_paid",
    "parse_settlement_lines",
    "per_diem_days",
    "register_module",
    "upload_settlement",
]
