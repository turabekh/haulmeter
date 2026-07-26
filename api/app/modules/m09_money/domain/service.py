"""AI-CONTEXT: M9 Driver Money & Tax Tools (PRD §8.9) — the quiet compounders that
make the app the driver's financial system of record and the wedge into the
company-driver majority. Owns schema m09.

Built this session (real + tested):
  · Settlement auditor (M9-FR1): a settlement's pay lines are reconciled against
    the driver's own GPS-backed receivables (M3/M4 via m04.money_owed); anything
    owed-but-unpaid is flagged with the evidence attached — "review with your
    carrier", never legal advice (PRD §8.9 note). The AI parse of a raw
    settlement doc is the F9 seam (parse_settlement_lines).
  · Earnings dashboard / North Star DDD (M9-FR4): recovered claims (M3/M4) +
    fuel saved (M7) + audit-flagged, in one figure.
  · Expense capture-lite (M9-FR5): receipt photos on F6, categorized for export.

Honest seams (basis surfaced, pending data — NOT fabricated, design-prd §11.7):
  · IFTA mileage (M9-FR2): needs jurisdiction-boundary geometry to split F3
    traces per state — totals from provided legs, per-jurisdiction is a seam.
  · Per-diem days (M9-FR3): needs account-wide traces + a home base — a seam.

Composes f06 + f09 + m04 + m07. Runs behind the F13 flag m09_money.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f06_documents import public as documents
from app.foundation.f09_ai_gateway import public as ai
from app.modules.m04_accessorial import public as m4
from app.modules.m07_fuel import public as m7

from .enums import DiscrepancyStatus
from .models import Discrepancy, ExpenseReceipt, Settlement, SettlementLine

FLAG_KEY = "m09_money"
MODULE = "m09"
SETTLEMENT_PROMPT = "m09_settlement_parse"
# every pay line carries both fields or it is not a pay line — a settlement row with
# no amount is the kind of half-read the auditor would go on to compare against
SETTLEMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["lines"],
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "amount_cents"],
                "properties": {
                    "kind": {"type": "string"},
                    "amount_cents": {"type": "integer"},
                },
            },
        }
    },
}
# the accessorial pay kinds an auditor reconciles (match F7 ReceivableKind)
AUDITABLE_KINDS = ("detention", "tonu", "layover", "lumper")


class SettlementNotParsed(Exception):
    pass


@dataclass
class EarningsSummary:
    recovered_cents: int
    fuel_saved_cents: int
    flagged_cents: int
    ddd_cents: int  # Driver Dollars Delivered (North Star)


@dataclass
class IftaSummary:
    total_miles: float
    by_jurisdiction: dict
    basis: str


@dataclass
class PerDiemResult:
    nights_away: int | None
    basis: str


@dataclass
class ExpenseSummary:
    by_category: dict
    total_cents: int
    receipt_count: int
    basis: dict = field(default_factory=dict)


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags
    from app.foundation.f14_admin import public as admin

    flags.register_flag(db, FLAG_KEY, description="M9 Driver Money & Tax Tools")
    admin.register_admin_view(db, "m09.audits", MODULE, "Settlement Audits", "/admin/m09/audits")
    if ai.get_active_prompt(db, SETTLEMENT_PROMPT) is None:
        ai.register_prompt(
            db, SETTLEMENT_PROMPT, ai.AiTask.document_parse, "extract pay lines from {doc}"
        )


# --- Settlement auditor (M9-FR1) ---
def upload_settlement(
    db: Session,
    account_id,
    carrier: str,
    period_start: date,
    period_end: date,
    lines: list[dict],
    gross_cents: int | None = None,
    doc_ref=None,
) -> Settlement:
    settlement = Settlement(
        driver_account_id=account_id,
        carrier=carrier,
        period_start=period_start,
        period_end=period_end,
        gross_cents=gross_cents
        if gross_cents is not None
        else sum(x["amount_cents"] for x in lines),
        doc_ref=doc_ref,
    )
    db.add(settlement)
    db.flush()
    for line in lines:
        db.add(
            SettlementLine(
                settlement_id=settlement.id, kind=line["kind"], amount_cents=line["amount_cents"]
            )
        )
    db.flush()
    return settlement


def parse_settlement_lines(db: Session, provider, doc_ref, account_id) -> list[dict]:
    # AI-CONTEXT: the F9 seam — a real settlement PDF/photo is parsed to pay lines
    # by the model gateway; deterministic in tests via a FakeModelProvider fixture.
    parsed = ai.parse_structured(
        db,
        provider,
        MODULE,
        SETTLEMENT_PROMPT,
        {"doc": str(doc_ref)},
        required_keys=["lines"],
        account_id=account_id,
        schema=SETTLEMENT_SCHEMA,
    )
    return parsed["lines"]


# receivables already settled through our own rails aren't "missed" carrier pay
_SETTLED_STATES = {"recovered", "written_off"}


def _owed_by_kind(db: Session, account_id) -> tuple[dict, dict]:
    owed: dict[str, int] = {}
    refs: dict[str, str] = {}
    for row in m4.money_owed(db, account_id):
        if row["state"] in _SETTLED_STATES:
            continue
        kind = row["kind"]
        owed[kind] = owed.get(kind, 0) + row["amount_cents"]
        refs.setdefault(kind, row["receivable_id"])  # first receivable = evidence anchor
    return owed, refs


def audit_settlement(db: Session, settlement: Settlement) -> list[Discrepancy]:
    paid: dict[str, int] = {}
    for line in settlement.lines:
        paid[line.kind] = paid.get(line.kind, 0) + line.amount_cents
    owed, refs = _owed_by_kind(db, settlement.driver_account_id)

    found: list[Discrepancy] = []
    for kind in AUDITABLE_KINDS:
        owed_cents = owed.get(kind, 0)
        if owed_cents <= 0:
            continue
        paid_cents = paid.get(kind, 0)
        missed = owed_cents - paid_cents
        if missed <= 0:
            continue
        disc = Discrepancy(
            settlement_id=settlement.id,
            kind=kind,
            owed_cents=owed_cents,
            paid_cents=paid_cents,
            missed_cents=missed,
            evidence_ref=uuid.UUID(refs[kind]) if kind in refs else None,
            status=DiscrepancyStatus.flagged,
        )
        db.add(disc)
        found.append(disc)
    db.flush()
    return found


def _flagged_total(db: Session, account_id) -> int:
    rows = db.scalars(
        select(Discrepancy)
        .join(Settlement, Discrepancy.settlement_id == Settlement.id)
        .where(
            Settlement.driver_account_id == account_id,
            Discrepancy.status == DiscrepancyStatus.flagged,
        )
    )
    return sum(d.missed_cents for d in rows)


# --- Earnings dashboard / North Star DDD (M9-FR4) ---
def earnings_dashboard(db: Session, account_id) -> EarningsSummary:
    recovered = sum(
        r["amount_cents"] for r in m4.money_owed(db, account_id) if r["state"] == "recovered"
    )
    fuel_saved = m7.driver_analytics(db, account_id).savings_cents
    flagged = _flagged_total(db, account_id)
    return EarningsSummary(
        recovered_cents=recovered,
        fuel_saved_cents=fuel_saved,
        flagged_cents=flagged,
        ddd_cents=recovered + fuel_saved + flagged,
    )


# --- Expense capture-lite (M9-FR5) ---
def add_receipt(
    db: Session,
    account_id,
    category: str,
    amount_cents: int,
    occurred_on: date,
    receipt_bytes: bytes | None = None,
    storage=None,
) -> ExpenseReceipt:
    doc_ref = None
    if receipt_bytes is not None:
        doc = documents.store_document(
            db,
            account_id,
            documents.DocType.other,
            receipt_bytes,
            filename="receipt.jpg",
            storage=storage,
        )
        doc_ref = doc.id
    receipt = ExpenseReceipt(
        driver_account_id=account_id,
        category=category,
        amount_cents=amount_cents,
        occurred_on=occurred_on,
        doc_ref=doc_ref,
    )
    db.add(receipt)
    db.flush()
    return receipt


def expense_summary(db: Session, account_id, year: int) -> ExpenseSummary:
    receipts = list(
        db.scalars(select(ExpenseReceipt).where(ExpenseReceipt.driver_account_id == account_id))
    )
    in_year = [r for r in receipts if r.occurred_on.year == year]
    by_category: dict[str, int] = {}
    for r in in_year:
        by_category[r.category] = by_category.get(r.category, 0) + r.amount_cents
    return ExpenseSummary(
        by_category=by_category,
        total_cents=sum(by_category.values()),
        receipt_count=len(in_year),
        basis={"year": year},
    )


# --- IFTA mileage (M9-FR2) — jurisdiction split is a seam ---
def ifta_summary(db: Session, account_id, legs: list[dict] | None = None) -> IftaSummary:
    # AI-CONTEXT: real per-jurisdiction split needs state-boundary geometry crossed
    # against F3 traces (not in the foundation yet). Totals come from provided
    # legs; per-jurisdiction stays a seam with an explicit basis (never faked).
    legs = legs or []
    total = sum(leg.get("miles", 0) for leg in legs)
    by_jurisdiction: dict[str, float] = {}
    basis = "legs" if legs else "no_data"
    for leg in legs:
        if "jurisdiction" in leg:
            j = leg["jurisdiction"]
            by_jurisdiction[j] = by_jurisdiction.get(j, 0) + leg.get("miles", 0)
    if not by_jurisdiction and legs:
        basis = "needs_jurisdiction_boundaries"
    return IftaSummary(total_miles=total, by_jurisdiction=by_jurisdiction, basis=basis)


# --- Per-diem day counter (M9-FR3) — needs account-wide traces + home base ---
def per_diem_days(db: Session, account_id, year: int, home_base_facility_id=None) -> PerDiemResult:
    # AI-CONTEXT: nights-away detection needs a continuous account trace vs. the
    # home base; F3 exposes per-facility dwell, not an account-wide track. A seam
    # with an explicit basis until the trace query lands.
    return PerDiemResult(nights_away=None, basis="needs_account_traces")
