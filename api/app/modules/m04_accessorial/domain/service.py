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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.foundation.f02_facility import public as facility_registry
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


class InvalidAmount(ValueError):
    pass


class AlreadyFiled(Exception):
    """This target already has a claim of this kind. Carries it so the caller can say so.

    AI-CONTEXT: M3 learned this one filing over (its `ClaimAlreadyFiled`): a retry after a
    success — a double tap, or a queued request replayed when the truck comes back into
    signal — is not an error the driver caused, and answering it as one invites them to
    file again on a claim the broker already has.
    """

    def __init__(self, claim):
        self.claim = claim
        super().__init__(f"{claim.kind.value} already filed for this target")


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags
    from app.foundation.f14_admin import public as admin

    flags.register_flag(db, FLAG_KEY, description="M4 Accessorial Recovery Suite", default_on=True)
    admin.register_admin_view(db, "m04.owed", MODULE, "Money Owed", "/admin/m04/owed")
    if ai.get_active_prompt(db, LUMPER_PROMPT) is None:
        ai.register_prompt(
            db, LUMPER_PROMPT, ai.AiTask.document_parse, "extract lumper amount from {doc}"
        )


# AI-CONTEXT: D3 — the idempotency key each kind files under, or None for "no key".
#
# These ride `uq_receivable_external_ref`, the partial unique index migration 0067 added
# for M3. TONU is once per LOAD (a truck is ordered-not-used once) and layover is once per
# STOP (one overnight per dock visit), so both have a target that identifies them.
#
# LUMPER IS EXCLUDED ON PURPOSE, and the exclusion is the decision. Multiple lumper fees
# per load are legitimate — one per stop — and the route carries no `stop_id`, so any key
# that could be built here would be wrong in one of two directions: keyed on the load it
# would silently refuse a driver's second real receipt, and keyed on anything else it
# would not dedupe at all. A per-stop shape is the recorded follow-up. Pinned by a test so
# this stays a decision rather than an oversight.
def _external_ref(kind, load, stop_ref) -> str | None:
    if kind is AccessorialKind.tonu:
        return f"m04:tonu:{load.id}"
    if kind is AccessorialKind.layover and stop_ref is not None:
        return f"m04:layover:{stop_ref}"
    return None


def claim_for_external_ref(db: Session, external_ref: str):
    """The claim that already holds this key — via the receivable that carries it."""
    receivable = db.scalar(
        select(ledger.Receivable).where(ledger.Receivable.external_ref == external_ref)
    )
    if receivable is None:
        return None
    return db.scalar(
        select(AccessorialClaim).where(AccessorialClaim.receivable_ref == receivable.id)
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
    # AI-CONTEXT: the floor lives HERE as well as on the Pydantic inputs, because this is
    # the layer every caller crosses — the worker, a future importer, and a test all reach
    # it without touching a route. M3's `generate_pack` set the precedent by refusing to
    # open a receivable for a claim worth nothing; M4 filed whatever it was handed, so a
    # zero or a negative went to a broker as an invoice under the driver's name.
    if amount_cents is None or amount_cents <= 0:
        raise InvalidAmount("an accessorial claim must be worth more than zero")

    external_ref = _external_ref(kind, load, stop_ref)
    if external_ref is not None:
        existing = claim_for_external_ref(db, external_ref)
        if existing is not None:
            raise AlreadyFiled(existing)

    claim = AccessorialClaim(
        account_id=load.account_id,
        load_ref=load.id,
        stop_ref=stop_ref,
        counterparty_ref=load.counterparty_id,
        kind=kind,
        amount_cents=amount_cents,
        document_ref=document_ref,
    )
    # AI-CONTEXT: claim AND receivable inside one SAVEPOINT. The unique index is the only
    # thing that can catch the concurrent filing — an application read cannot see a row a
    # parallel transaction has not committed — and without the savepoint the losing side
    # would leave its CLAIM row behind after the receivable insert blew up: a filed-looking
    # accessorial with no receivable, on the driver's own money screen.
    try:
        with db.begin_nested():
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
                external_ref=external_ref,
            )
    except IntegrityError:
        db.expunge(claim)
        won = claim_for_external_ref(db, external_ref) if external_ref else None
        if won is None:
            raise  # the constraint fired for some other reason — do not swallow it
        raise AlreadyFiled(won) from None

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
    # AI-CONTEXT: "overnight" is a question about the DOCK'S calendar, not UTC's (F-22).
    #
    # `_as_utc(...).date()` is the UTC calendar day, and a layover is a local overnight.
    # In Dallas an 8pm→4am stop — an overnight by any reading — is 01:00→09:00 on ONE
    # UTC day, so the dates matched and the claim was refused outright. This is F-21's
    # defect pointing the other way: that one filed claims that should not exist, this
    # one refused claims that should. Same line, same missing input.
    facility = facility_registry.get_facility(db, stop.facility_id)
    if facility is not None:
        arrived_on = facility_registry.local_date(db, facility, arrival)
        departed_on = facility_registry.local_date(db, facility, departure)
    else:  # the dock is gone from the registry: UTC is all that is left to compare
        arrived_on, departed_on = _as_utc(arrival).date(), _as_utc(departure).date()
    if arrived_on == departed_on:
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
        # AI-CONTEXT: a FEE is not a row on this list (J1-R1, §23 entry 173).
        #
        # Every other kind here is money a BROKER owes the driver, and this list is summed
        # into the "what you are owed" hero (§23 entry 142). A fee receivable is money the
        # driver owes the PLATFORM and never leaves `invoiced`, because no collection
        # rails exist — so leaving it in would have added our own fee to the figure
        # telling a driver what brokers are sitting on. The biggest number on the screen,
        # wrong, in the direction that flatters us. It belongs to the recovery it came
        # from, and it is attached to that row below.
        if r.kind is ledger.ReceivableKind.fee:
            continue
        aging = (now - _as_utc(r.created_at)).days
        fee = ledger.fee_for(db, r)
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
                # AI-CONTEXT: WHO owes it (§23 entry 142). The Money tab listed
                # "Detention · Invoiced · $187.50 · 12d" and never said who was sitting
                # on it — so the one screen about being paid could not name the person
                # who had not paid. `counterparty_ref` has been on this row since F7.
                "counterparty_name": _counterparty_name(db, r),
                # WHERE it happened, which is how a driver recognises their own claim:
                # a broker's name is a company, a dock is a memory.
                "facility_name": _receivable_facility(db, r),
                # the stop this money came from, so the driver can open the evidence
                # that argues it. §13.5's rule for notifications, applied to a row.
                "stop_id": _receivable_stop_id(db, r),
                # WHAT HAS ALREADY BEEN SENT. The chasers are recorded as timestamps on
                # the claim and were read by nothing outside the dunning job itself, so
                # a driver could not tell a claim that had been chased twice from one
                # nobody had touched — which is the whole difference between "wait" and
                # "do something".
                "history": _receivable_history(db, r),
                # WHAT WE TOOK, and what is left. Present on every row so the shape does
                # not shift between a recovery with a fee and one without: no fee means
                # zero taken and the whole amount kept, which is a statement rather than
                # an absence.
                "fee_cents": fee.amount_cents if fee is not None else 0,
                "net_cents": r.amount_cents - (fee.amount_cents if fee is not None else 0),
            }
        )
    return rows


def _counterparty_name(db: Session, receivable) -> str | None:
    if receivable.counterparty_ref is None:
        return None
    cp = loads.get_counterparty(db, receivable.counterparty_ref)
    return getattr(cp, "name", None)


def _receivable_stop_id(db: Session, receivable):
    """The stop behind this money, through whichever module opened the receivable."""
    claim = claim_for_receivable(db, receivable.id)
    stop_ref = getattr(claim, "stop_ref", None)
    if stop_ref is None:
        m3_claim = m3.claim_for_receivable(db, receivable.id)
        stop_ref = getattr(m3_claim, "stop_ref", None)
    return str(stop_ref) if stop_ref is not None else None


def _receivable_facility(db: Session, receivable) -> str | None:
    """The dock this money came from — a broker's name is a company, a dock is a memory."""
    stop_ref = _receivable_stop_id(db, receivable)
    if stop_ref is None:
        return None
    stop = loads.get_stop(db, stop_ref)
    if stop is None:
        return None
    fac = facility_registry.get_facility(db, stop.facility_id)
    return getattr(fac, "name", None)


def _receivable_history(db: Session, receivable) -> list[dict]:
    """What has already gone to this counterparty, oldest first.

    AI-CONTEXT: read off the claim's own dunning columns rather than stored again. They
    are set by `run_dunning` at dispatch and were, until this, consulted only by the job
    that writes them — a driver looking at a 63-day-old claim had no way to know whether
    anyone had chased it. Absent columns mean absent chasers, which is exactly what a
    NULL says; nothing here invents a step that did not happen.
    """
    out = [{"event": "invoiced", "at": _as_utc(receivable.created_at)}]
    claim = m3.claim_for_receivable(db, receivable.id)
    if claim is None:
        return out
    for event, column in (
        ("nudged", "dunning_nudge_sent_at"),
        ("firmed", "dunning_firm_sent_at"),
        ("final_notice_sent", "dunning_final_notice_sent_at"),
    ):
        at = getattr(claim, column, None)
        if at is not None:
            out.append({"event": event, "at": _as_utc(at)})
    return sorted(out, key=lambda e: e["at"])


def claim_for_receivable(db: Session, receivable_ref) -> AccessorialClaim | None:
    # AI-CONTEXT: M3 carries the same lookup for the same reason (§13.5) — an
    # accessorial receivable must deep-link to the stop it was filed against, and the
    # two claim tables are the only places that mapping is recorded.
    return db.scalar(
        select(AccessorialClaim).where(AccessorialClaim.receivable_ref == receivable_ref)
    )

