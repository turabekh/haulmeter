"""AI-CONTEXT: M4 Accessorial Recovery Suite (PRD §8.4). The same evidence-and-
invoice rail as M3, extended to the accessorials nobody bundles: TONU, layover,
and lumper reimbursement. Reuses the M3 pipeline via m03.public.open_receivable
(F7 receivable + F8 counterparty notice + F5 claim-count) so the claim-type
registry, templates, and analytics stay independently testable. Composes
foundation publics + m03.public only (import-linter). Runs behind the F13 flag
m04_accessorial.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f03_location import public as location
from app.foundation.f05_load import public as loads
from app.foundation.f06_documents import public as documents
from app.foundation.f07_ledger import public as ledger
from app.foundation.f09_ai_gateway import public as ai
from app.modules.m03_detention import public as m3

from .enums import AccessorialKind, AccessorialState
from .models import AccessorialClaim

FLAG_KEY = "m04_accessorial"
MODULE = "m04"
LUMPER_PROMPT = "lumper_ocr"
# the amount is the whole answer, and `required` + nullable says "I read the receipt
# and there was no amount on it" rather than leaving the caller to guess from a
# missing key. additionalProperties:false is required on every object by the format.
LUMPER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["amount_cents"],
    "properties": {"amount_cents": {"anyOf": [{"type": "integer"}, {"type": "null"}]}},
}

_KIND_TO_RECEIVABLE = {
    AccessorialKind.tonu: ledger.ReceivableKind.tonu,
    AccessorialKind.layover: ledger.ReceivableKind.layover,
    AccessorialKind.lumper: ledger.ReceivableKind.lumper,
}


class NoLayover(Exception):
    pass


class MissingLumperAmount(Exception):
    pass


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags
    from app.foundation.f14_admin import public as admin

    flags.register_flag(db, FLAG_KEY, description="M4 Accessorial Recovery Suite")
    admin.register_admin_view(db, "m04.owed", MODULE, "Money Owed", "/admin/m04/owed")
    if ai.get_active_prompt(db, LUMPER_PROMPT) is None:
        ai.register_prompt(
            db, LUMPER_PROMPT, ai.AiTask.document_parse, "extract lumper amount from {doc}"
        )


def _file(
    db,
    load,
    kind,
    amount_cents,
    gateway,
    stop_ref=None,
    document_ref=None,
    subject="Invoice",
    body="Invoice per the rate confirmation.",
):
    claim = AccessorialClaim(
        account_id=load.account_id,
        load_ref=load.id,
        stop_ref=stop_ref,
        counterparty_ref=load.counterparty_id,
        kind=kind,
        amount_cents=amount_cents,
        document_ref=document_ref,
    )
    db.add(claim)
    db.flush()
    receivable = m3.open_receivable(
        db,
        load.account_id,
        _KIND_TO_RECEIVABLE[kind],
        amount_cents,
        counterparty_ref=load.counterparty_id,
        gateway=gateway,
        notice_subject=subject,
        notice_body=body,
    )
    claim.receivable_ref = receivable.id
    claim.state = AccessorialState.invoiced
    db.flush()
    return claim


# --- TONU (M4-FR1) ---
def file_tonu(db: Session, load, amount_cents: int, stop=None, gateway=None) -> AccessorialClaim:
    return _file(
        db,
        load,
        AccessorialKind.tonu,
        amount_cents,
        gateway,
        stop_ref=stop.id if stop is not None else None,
        subject="TONU invoice",
        body="Truck Ordered Not Used per the rate confirmation; invoice attached.",
    )


# --- Layover (M4-FR2) — overnight dwell detection ---
def _visit_anchor(load, stop) -> datetime:
    """Which moment this stop's visit belongs to.

    AI-CONTEXT: the appointment is the contracted window for THIS stop, so it is the
    most precise anchor available. Falling back to the load's creation is safe because
    a load always exists before it is driven — the visit that matters is the first one
    at this dock after the paperwork existed, never one from a previous run.
    """
    return stop.appointment_start or load.created_at


def _arrival_departure(db: Session, account_id, facility_id, since: datetime):
    """ONE visit's arrival and departure — §23 entry 73, which M4 never received.

    AI-CONTEXT: this used to replay raw ENTER/EXIT events and take the EARLIEST enter
    ever recorded at the facility and the LATEST exit, so a driver's second load to the
    same dock read the first visit's arrival. M3 was fixed by `location.visit_window`;
    M4 kept its own copy of the original bug, and M4's consequence is the worse one.

    M3's version produced a wrong AMOUNT on a real claim. This one decides whether a
    claim EXISTS: with an arrival from weeks ago and a departure from today the dates
    differ, `NoLayover` is not raised, and a layover invoice is filed for a stop that
    was never overnight — then sent to a broker under the driver's name. A wrong figure
    invites a question; a fabricated claim invites a refusal to deal.

    The primitive already existed. This function simply never asked it.
    """
    return location.visit_window(db, account_id, facility_id, since)


def file_layover(db: Session, stop, layover_rate_cents: int, gateway=None) -> AccessorialClaim:
    load = loads.get_load(db, stop.load_id)
    arrival, departure = _arrival_departure(
        db, load.account_id, stop.facility_id, _visit_anchor(load, stop)
    )
    if arrival is None or departure is None:
        raise NoLayover("no completed stop at this facility")
    if _as_utc(arrival).date() == _as_utc(departure).date():
        raise NoLayover("dwell did not span overnight")
    return _file(
        db,
        load,
        AccessorialKind.layover,
        layover_rate_cents,
        gateway,
        stop_ref=stop.id,
        subject="Layover invoice",
        body="Overnight layover held at this stop per the rate confirmation; invoice attached.",
    )


# --- Lumper reimbursement (M4-FR3): receipt -> F6 -> F9 OCR -> invoice ---
def file_lumper(
    db: Session,
    load,
    provider,
    receipt_bytes: bytes | None = None,
    amount_cents: int | None = None,
    gateway=None,
    storage=None,
) -> AccessorialClaim:
    doc = documents.store_document(
        db,
        load.account_id,
        documents.DocType.lumper_receipt,
        receipt_bytes or b"",
        filename="lumper.jpg",
        storage=storage,
    )
    if amount_cents is None:
        parsed = ai.parse_structured(
            db,
            provider,
            MODULE,
            LUMPER_PROMPT,
            {"doc": doc.content_hash},
            required_keys=["amount_cents"],
            schema=LUMPER_SCHEMA,
        )
        amount_cents = parsed["amount_cents"]
    if amount_cents is None:
        raise MissingLumperAmount("could not read lumper amount")
    documents.apply_extraction(db, doc, {"amount_cents": amount_cents})
    return _file(
        db,
        load,
        AccessorialKind.lumper,
        amount_cents,
        gateway,
        document_ref=doc.id,
        subject="Lumper reimbursement",
        body="Lumper fee paid at the dock (receipt attached); reimbursement requested "
        "per the rate confirmation.",
    )


# --- Accessorial terms check (M4-FR4) ---
def check_accessorial_terms(load) -> dict:
    terms = load.accessorial_terms or {}
    present = {
        "detention": load.detention_rate_cents_per_hour is not None,
        "tonu": "tonu" in terms,
        "layover": "layover" in terms,
    }
    missing = [k for k, ok in present.items() if not ok]
    return {"present": present, "missing": missing, "silent": bool(missing)}


# --- Unified "Money Owed" (M4-FR5): M3 + M4 receivables with aging ---
def money_owed(db: Session, account_id, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    rows = []
    for r in ledger.list_receivables(db, account_id):
        aging = (now - _as_utc(r.created_at)).days
        rows.append(
            {
                "receivable_id": str(r.id),
                "kind": r.kind.value,
                "amount_cents": r.amount_cents,
                "state": r.state.value,
                "aging_days": aging,
                # M9 audits a settlement against ONE pay period, so it needs the date and
                # not only the age (F-23). `aging_days` answers "how long has this been
                # outstanding"; this answers "which period does it belong to".
                "created_at": _as_utc(r.created_at),
                "is_reimbursement": r.kind == ledger.ReceivableKind.lumper,
            }
        )
    return rows


def claim_for_receivable(db: Session, receivable_ref) -> AccessorialClaim | None:
    # AI-CONTEXT: M3 carries the same lookup for the same reason (§13.5) — an
    # accessorial receivable must deep-link to the stop it was filed against, and the
    # two claim tables are the only places that mapping is recorded.
    return db.scalar(
        select(AccessorialClaim).where(AccessorialClaim.receivable_ref == receivable_ref)
    )

