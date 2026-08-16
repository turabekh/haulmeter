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

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.foundation.f06_documents import public as documents
from app.foundation.f07_ledger import public as ledger
from app.foundation.f08_notifications import public as notify
from app.foundation.f09_ai_gateway import public as ai
from app.foundation.f13_flags import public as flags
from app.modules.m03_detention import public as m3
from app.modules.m04_accessorial import public as m4
from app.modules.m07_fuel import public as m7

from . import messages
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



# AI-CONTEXT: finding N-02 — an English literal on a driver's push. F8 resolves the
# locale; the compiled English below is the fallback so a missing row cannot silence it.
def _alert(db: Session, account_id, key: str, **values) -> str:
    return notify.localized_text(
        db,
        account_id,
        messages.KEY_PREFIX + key,
        messages.ALERT_MESSAGES[key][messages.DEFAULT_LOCALE_KEY],
        **values,
    )


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags
    from app.foundation.f14_admin import public as admin

    flags.register_flag(db, FLAG_KEY, description="M9 Driver Money & Tax Tools", default_on=True)
    from app.foundation.f15_localization import public as localization

    localization.register_catalogue(db, messages.KEY_PREFIX, messages.ALERT_MESSAGES)
    admin.register_admin_view(db, "m09.audits", MODULE, "Settlement Audits", "/admin/m09/audits")
    # J1-R1 (§23 entry 172). OFF until the owner puts a price in front of a driver.
    flags.register_flag(
        db,
        FEE_FLAG,
        description=(
            "J1-R1: post the contingency fee as a receivable on recovery, and disclose "
            "gross/fee/net at the paid moment."
        ),
        default_on=False,
    )
    # PRD §159 lists fee percentages as runtime config; §242/§414 set the automated-stage
    # rate at ~15%. A price must be changeable on a live box without a deploy.
    flags.register_config(
        db,
        CONFIG_FEE_BASIS_POINTS,
        DEFAULT_FEE_BASIS_POINTS,
        "Contingency fee on recovered claims, in basis points (1500 = 15.00%)",
    )
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
    """AI-CONTEXT: re-auditing a pay period REPLACES it rather than adding another
    (§23 entry 154).

    A settlement is a document that exists once. The driver types what their carrier paid,
    and typing it again — after a typo, or with the layover line they missed the first
    time — is a correction to that one document, not a second settlement. Measured before
    the fix: three runs, three settlements, `flagged_cents` 15000 → 30000 → 45000.

    The gross is recomputed from the new lines unless the caller states one, because a
    stale gross beside corrected lines is a document that disagrees with itself.
    """
    total = gross_cents if gross_cents is not None else sum(x["amount_cents"] for x in lines)
    settlement = db.scalar(
        select(Settlement).where(
            Settlement.driver_account_id == account_id,
            Settlement.carrier == carrier,
            Settlement.period_start == period_start,
            Settlement.period_end == period_end,
        )
    )
    if settlement is None:
        settlement = Settlement(
            driver_account_id=account_id,
            carrier=carrier,
            period_start=period_start,
            period_end=period_end,
            gross_cents=total,
            doc_ref=doc_ref,
        )
        db.add(settlement)
    else:
        settlement.gross_cents = total
        # a re-upload that names no document must not erase the one already attached
        if doc_ref is not None:
            settlement.doc_ref = doc_ref
        # AI-CONTEXT: the lines ARE the correction, so the old ones go rather than
        # accumulate — and this is a statement, not a collection edit, because the
        # relationship collections on this object are NOT reliable here. `audit_settlement`
        # writes discrepancies with `db.add` rather than through `settlement.discrepancies`,
        # so an in-memory collection can be stale the moment a caller re-uses a settlement
        # it already audited. Deleting by query and expiring is the version that does not
        # depend on which of the two paths last touched the object.
        db.execute(delete(SettlementLine).where(SettlementLine.settlement_id == settlement.id))
        db.expire(settlement, ["lines"])
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


def _owed_by_kind(db: Session, account_id, period_start, period_end) -> tuple[dict, dict]:
    """What the carrier owed FOR THIS PAY PERIOD, not for all time (audit F-23).

    AI-CONTEXT: `paid` is scoped to one settlement document and `owed` was every
    unsettled receivable the driver had, across every load, ever. Subtracting one from
    the other is not a like-for-like comparison, and it was wrong in two directions.

    A lumper receivable from a load this settlement does not cover was reported as
    "missed" — the driver told their broker underpaid on money that broker had never been
    billed for. And because a receivable stays owed until somebody taps *the broker paid
    this* — driver-initiated, and the only path to `recovered` until a second actor
    exists — the same balance was re-flagged on every later settlement, with
    `_flagged_total` summing the duplicates into the earnings dashboard. Overstating
    "money the broker owes you" is §11.7's honesty failure pointed at the driver, on a
    number adjacent to the North Star.

    THE REMAINING GAP, stated rather than hidden: this scopes by the receivable's
    creation date against the settlement's pay period, because there is no settlement→load
    link in the schema. That is a proxy. Work performed inside the period whose receivable
    is filed after `period_end` still falls outside this audit, and closing that properly
    needs the link the audit named — which is a schema change and its own session.
    """
    owed: dict[str, int] = {}
    refs: dict[str, str] = {}
    for row in m4.money_owed(db, account_id):
        if row["state"] in _SETTLED_STATES:
            continue
        created = row["created_at"].date()
        if created < period_start or created > period_end:
            continue
        kind = row["kind"]
        owed[kind] = owed.get(kind, 0) + row["amount_cents"]
        refs.setdefault(kind, row["receivable_id"])  # first receivable = evidence anchor
    return owed, refs


def audit_settlement(db: Session, settlement: Settlement) -> list[Discrepancy]:
    """AI-CONTEXT: re-auditing clears the previous FLAGGED findings and keeps the acted-on
    ones (§23 entry 154).

    `_flagged_total` counts every `flagged` discrepancy the driver has, so a second run
    over the same settlement used to stack a second copy of the same finding into the
    figure on the Money tab. Clearing them is what makes a re-run a re-run.

    `submitted` and `resolved` are NOT cleared, and the asymmetry is the point: those are
    a record of the driver acting — sending the discrepancy to their carrier, or the
    carrier settling it — and re-running an audit is not permission to erase what someone
    did. They also cost nothing to keep, because neither status is counted by
    `_flagged_total`. A kind that is still genuinely owed is re-flagged beside its
    submitted history, which is one flagged row and therefore counted once.
    """
    # by QUERY, for the reason given in `upload_settlement`: this function adds
    # discrepancies with `db.add`, so `settlement.discrepancies` may not reflect what a
    # previous run wrote. Expiring afterwards makes the collection correct for the caller.
    db.execute(
        delete(Discrepancy).where(
            Discrepancy.settlement_id == settlement.id,
            Discrepancy.status == DiscrepancyStatus.flagged,
        )
    )
    db.expire(settlement, ["discrepancies"])

    paid: dict[str, int] = {}
    for line in settlement.lines:
        paid[line.kind] = paid.get(line.kind, 0) + line.amount_cents
    owed, refs = _owed_by_kind(
        db, settlement.driver_account_id, settlement.period_start, settlement.period_end
    )

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
    db.expire(settlement, ["discrepancies"])
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


# --- Recovery: the moment a claim is actually paid (§13.2 / §23 entry 108) ---
#
# AI-CONTEXT: `ReceivableState.recovered` and F7's `record_recovery` have existed since
# the ledger shipped and **no application code has ever called either** — only tests.
# So a claim could never become paid, `recovered_cents` on this module's own earnings
# dashboard was structurally $0 forever, and M12's fleet rollup counted a state nothing
# could reach. §13.2 names "claim paid" as a P0 example; the notification was not
# missing a dispatch site, the EVENT did not exist.
#
# WHO MARKS IT — owner decision. The driver. M3's whole model is that the driver
# invoices the broker in their own name and the money lands in the driver's bank, not
# ours: nobody else is in a position to know it arrived. No integration, no operator
# standing between a driver and their own recovery.
#
# WHO IS TOLD — and this is the part that decides whether the P0 fires at all. A
# notification exists to tell someone something they do not already know. A driver who
# just tapped "the broker paid this" is the last person who needs a push about it, so
# the alert fires only when the recovery was recorded by someone ELSE — a fleet manager
# (M12) or the collection partner M3-FR7 hands escalated claims to. Today that means it
# is correct and dormant: the endpoint below is driver-only, so nothing reaches the
# branch yet. It is written this way so the P0 is right by construction the moment a
# second actor exists, rather than remembered later.
#
# WHY NO LEDGER ENTRY IS POSTED, which looks like an omission and is not.
#
# **Affirmed unamended by J1-R1 (§23 entry 172), which added the other half**: the
# contingency fee becomes a `fee` RECEIVABLE rather than a ledger entry, for exactly the
# reasoning below. A receivable records that something is OWED; a journal entry records
# that something MOVED. Only the first is true until collection rails exist. F7's
# `record_recovery` posts cash_clearing -> driver_payable with a contingency split, and
# it is the right call for the M3-FR7 collection partner, where the money passes
# through us and we take a fee. A driver who invoices a broker in their own name is
# paid into their OWN bank: no cash crosses this platform, and posting an entry saying
# it did would be inventing a movement we never handled. The receivable's state is the
# honest record of it, which is exactly what F7's transition table is for.
CLAIM_PAID_CATEGORY = "claim_paid"

# AI-CONTEXT: the contingency share, as CONFIG rather than a constant (J1-R1).
#
# PRD §242 and §414 set it at ~15% for the automated stage (25-30% is the
# partner-escalated rate, and that rung does not exist — see entry 171). PRD §159 lists
# "fee percentages" among the things that must be runtime config, so this is an F13 key
# with the PRD's number as its default: a price is an owner's decision and must be
# changeable on a live box without a deploy.
FEE_FLAG = "j1_fee_disclosure"
CONFIG_FEE_BASIS_POINTS = "m09.contingency_fee_basis_points"
DEFAULT_FEE_BASIS_POINTS = 1500  # 15.00%


def fee_basis_points(db: Session) -> int:
    return int(flags.get_config(db, CONFIG_FEE_BASIS_POINTS, DEFAULT_FEE_BASIS_POINTS))


def fee_cents_for(db: Session, recovered_cents: int) -> int:
    """BASIS POINTS, not a float percentage — money is integer arithmetic here and
    everywhere else in this ledger. Rounded half-up on the cent, so the fee never exceeds
    the recovery it is taken from."""
    return min(recovered_cents, (recovered_cents * fee_basis_points(db) + 5000) // 10000)


def fee_receivable_for(db: Session, receivable) -> object | None:
    """The fee owed on ONE recovery, or None if it was never posted."""
    return db.scalar(
        select(ledger.Receivable).where(ledger.Receivable.external_ref == _fee_ref(receivable))
    )


def _fee_ref(receivable) -> str:
    # the RECOVERY is the real-world thing being billed, so it is the external ref — and
    # `uq_receivable_external_ref` makes a second post impossible rather than unlikely
    return f"fee:{receivable.id}"


def _post_fee_receivable(db: Session, receivable):
    """The platform's share of a recovery, as a RECEIVABLE (J1-R1, §23 entry 172).

    AI-CONTEXT: **no ledger entry, and no dunning, ever.** Both halves are the ruling.

    No ledger entry, because no cash crossed this platform: the driver invoiced the broker
    in their own name and was paid into their own bank. The rationale above this function
    has said so since the recovery path was built and R1 affirmed it unamended.

    No dunning, because the machinery that chases an unpaid receivable is pointed at
    BROKERS. It selects through `DetentionClaim.receivable_ref`, and a fee receivable has
    no claim — so it is unreachable by construction rather than by a filter someone has to
    remember. `test_no_dunning_path_can_select_a_fee` asserts that structurally. This
    product does not chase its own drivers, and the day it collects a fee that will be a
    designed moment with rails, not a side effect of a cadence written for counterparties.

    Idempotent on `external_ref`: a second call returns the row the first one wrote.
    """
    existing = fee_receivable_for(db, receivable)
    if existing is not None:
        return existing
    amount = fee_cents_for(db, receivable.amount_cents)
    if amount <= 0:
        return None
    # F7's own factory rather than the model — the receivable table is the ledger's, and
    # reaching past its public surface to insert a row is how two writers end up
    # disagreeing about what a receivable needs
    return ledger.create_receivable(
        db,
        # the SUBJECT is the driver: this is what they owe out of what they were paid
        receivable.account_id,
        ledger.ReceivableKind.fee,
        amount,
        # no counterparty — the platform is not a broker, and pointing this at one would
        # put our fee in a broker's payment history
        counterparty_ref=None,
        external_ref=_fee_ref(receivable),
    )


def _receivable_deep_link(db: Session, receivable) -> str | None:
    """§13.5: the exact claim, never a tab root.

    A receivable knows an account and an amount; only the claim that opened it knows
    which stop the money came from. M3 and M4 are the two modules that open them.
    """
    claim = m3.claim_for_receivable(db, receivable.id) or m4.claim_for_receivable(
        db, receivable.id
    )
    stop_ref = getattr(claim, "stop_ref", None) if claim is not None else None
    return f"/claim/{stop_ref}" if stop_ref is not None else None


def mark_receivable_paid(
    db: Session,
    receivable,
    actor_account_id,
    gateway=None,
    now=None,
):
    """Record that a receivable was actually paid, and tell the driver if they are not
    the one who said so.

    Raises F7's `InvalidTransition` for a receivable that cannot legally reach
    `recovered` — already recovered, or written off. The state machine is the ledger's
    and is not restated here.
    """
    ledger.transition_receivable(db, receivable, ledger.ReceivableState.recovered)
    # J1-R1: the platform's share becomes a receivable at the moment the money lands.
    # Behind `j1_fee_disclosure` because a fee is a PRICE, and a price appears in front of
    # a driver when the owner says so.
    if flags.is_enabled(db, FEE_FLAG):
        _post_fee_receivable(db, receivable)
    if gateway is None or actor_account_id == receivable.account_id:
        return receivable, None
    deep_link = _receivable_deep_link(db, receivable)
    if deep_link is None:
        # §13.5 is not negotiable and `dispatch` enforces it. A receivable no claim
        # owns cannot be deep-linked, so it is recorded and not announced — silence is
        # better than a P0 that lands on a tab root.
        return receivable, None
    amount = receivable.amount_cents / 100
    figure = f"${amount:,.0f}" if receivable.amount_cents % 100 == 0 else f"${amount:,.2f}"
    notification = notify.dispatch(
        db,
        receivable.account_id,
        notify.NotificationTier.P0,
        CLAIM_PAID_CATEGORY,
        _alert(db, receivable.account_id, "claim_paid.title", figure=figure),
        _alert(db, receivable.account_id, "claim_paid.body"),
        deep_link,
        gateway,
        now=now,
        subject_ref=str(receivable.id),
    )
    return receivable, notification

