"""AI-CONTEXT: M3 Detention Tracker & Recovery (PRD §8.3) — the differentiator.
Zero-effort GPS-verified detention: the driver drives to the stop and does
nothing; the app proves arrival, runs the clock, warns the broker, invoices the
moment detention accrues, and opens a receivable. Composes foundation publics
only: F1 (invoicing gate), F3 (geofence events), F4 (hash-chained evidence +
pack), F5 (stop/load/counterparty), F7 (receivable), F8 (counterparty notices),
F13/F14 (flags/gates/admin). The clock math is the money core — exact, integer
cents. Runs behind the F13 flag m03_detention, gated on legal + collection-partner
validation gates.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundation.f01_identity import public as identity
from app.foundation.f03_location import public as location
from app.foundation.f04_evidence import public as evidence
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.foundation.f08_notifications import public as notify

from .enums import ClaimMode, ClaimState, DetentionPhase, DetentionTrigger
from .models import DetentionClaim

FLAG_KEY = "m03_detention"
MODULE = "m03"
PRE_DETENTION_THRESHOLD = timedelta(minutes=30)  # M3-FR3 default (-> F13 config)
DUNNING_DAYS = [3, 10, 21]  # M3-FR6 (-> F13 config)
GATES = ["legal_signoff", "collection_partner_agreement"]
# detention-term defaults for a new load (design-prd §9): 2h free / $75/h. Live
# F13-config knobs (edited in the F14 admin console) with these as the fallback.
DEFAULT_FREE_TIME_MINUTES = 120
DEFAULT_RATE_CENTS_PER_HOUR = 7500
CONFIG_FREE_TIME_KEY = "m03_free_time_minutes"
CONFIG_RATE_KEY = "m03_rate_cents_per_hour"


def default_free_time_minutes(db: Session) -> int:
    from app.foundation.f13_flags import public as flags

    return int(flags.get_config(db, CONFIG_FREE_TIME_KEY, DEFAULT_FREE_TIME_MINUTES))


def default_rate_cents_per_hour(db: Session) -> int:
    from app.foundation.f13_flags import public as flags

    return int(flags.get_config(db, CONFIG_RATE_KEY, DEFAULT_RATE_CENTS_PER_HOUR))


@dataclass
class DetentionState:
    phase: DetentionPhase
    free_time_remaining_seconds: int
    detention_seconds: int
    amount_cents: int


# --- Detention clock math (the money core) ---
def compute_detention(
    trigger_time: datetime,
    free_time_minutes: int | None,
    rate_cents_per_hour: int | None,
    now: datetime,
    departed_at: datetime | None = None,
) -> DetentionState:
    free = (free_time_minutes or 0) * 60
    detention_start = trigger_time + timedelta(seconds=free)
    if departed_at is None and now < detention_start:
        remaining = (detention_start - now).total_seconds()
        return DetentionState(DetentionPhase.within_free_time, int(remaining), 0, 0)
    end = departed_at or now
    accrued = max(0.0, (end - detention_start).total_seconds())
    # AI-CONTEXT: the amount is derived from the SECONDS WE REPORT, not from the float
    # behind them. A claim is a document a third party verifies, and the clerk checking
    # it does the only arithmetic available to them: the time and the rate printed on
    # its face. Rounding the amount off 38.7s while reporting 38s produced an invoice
    # reading "0:00:38 · $120/h · $1.29" — where 38 seconds at $120/h is $1.27. The
    # gap is pennies and the credibility cost is not: an invoice whose own figures do
    # not reproduce invites the one question a detention claim cannot afford.
    seconds = int(accrued)
    amount = round(seconds / 3600 * (rate_cents_per_hour or 0))
    phase = DetentionPhase.ended if departed_at is not None else DetentionPhase.accruing
    return DetentionState(phase, 0, seconds, int(amount))


def register_module(db: Session) -> None:
    from app.foundation.f13_flags import public as flags

    flags.register_flag(db, FLAG_KEY, description="M3 Detention Tracker & Recovery")
    for gate in GATES:
        flags.add_gate(db, FLAG_KEY, gate)
    from app.foundation.f14_admin import public as admin

    admin.register_admin_view(db, "m03.claims", MODULE, "Claims Pipeline", "/admin/m03/claims")


def _default_mode(db: Session, account_id) -> ClaimMode:
    profile = db.get(identity.DriverProfile, account_id)
    return ClaimMode.invoice if identity.can_invoice(profile) else ClaimMode.evidence_only


def start_claim(
    db: Session,
    stop,
    mode: ClaimMode | None = None,
    trigger: DetentionTrigger = DetentionTrigger.arrival,
    started_at: datetime | None = None,
) -> DetentionClaim:
    load = loads.get_load(db, stop.load_id)
    if not stop.geofence_armed:
        loads.arm_stop(db, stop)  # opens the F4 evidence log + arms the F3 geofence
    free_time, rate = loads.effective_detention_terms(db, stop)
    claim = DetentionClaim(
        stop_ref=stop.id,
        facility_ref=stop.facility_id,
        account_id=load.account_id,
        counterparty_ref=load.counterparty_id,
        mode=mode or _default_mode(db, load.account_id),
        trigger=trigger,
        free_time_minutes=free_time,
        detention_rate_cents_per_hour=rate,
        evidence_log_ref=stop.evidence_log_id,
        clock_since=started_at or datetime.now(UTC),
    )
    db.add(claim)
    db.flush()
    return claim


# --- Evidence accrual (fills the F5->F4 seam; F3 events -> hash-chained log) ---
def accrue_events(db: Session, claim: DetentionClaim) -> int:
    """This visit's geofence events, into this stop's chain (§23 entry 75).

    AI-CONTEXT: the same unscoped read as the clock defect (entry 73), three lines
    above the function that had it, and missed while fixing that one. It pulled EVERY
    geofence event ever recorded for the account at this facility into the stop's
    hash-chained log, so a driver's second load to the same dock filed the first
    load's arrivals as evidence of this one. Seen in a real pack: four ENTER records
    for a stop the driver arrived at once, three of them from earlier that afternoon.

    The chain is append-only, so a log this has already polluted stays polluted —
    which is the argument for scoping the write rather than filtering the read.
    """
    log = db.get(evidence.EvidenceLog, claim.evidence_log_ref)
    accrued = {r.payload.get("event_id") for r in log.records if r.payload}
    added = 0
    arrival, departure = _arrival_departure(db, claim)
    # before the truck arrives there is no visit yet, so the claim's own start is the
    # earliest anything can belong to it
    floor = arrival or claim.clock_since
    for event in location.list_events(db, claim.account_id, claim.facility_ref):
        if str(event.id) in accrued:
            continue
        if floor is not None and event.occurred_at < floor:
            continue
        if departure is not None and event.occurred_at > departure:
            continue
        evidence.append_record(
            db,
            log,
            evidence.RecordType.GEOFENCE,
            {"event": event.event_type.value, "event_id": str(event.id)},
            occurred_at=event.occurred_at,
        )
        added += 1
    return added


def _arrival_departure(db: Session, claim: DetentionClaim):
    """This visit's arrival and departure — not the facility's whole history.

    AI-CONTEXT: the money defect (§23 entry 73). This replayed EVERY geofence event
    ever recorded for the account at this facility and took the earliest ENTER and
    the latest EXIT, so any previous visit to the same dock became the start of this
    claim's clock. Measured on a real two-stop load: a delivery the driver was at for
    53 seconds billed 2h20m — $187.76 against $0.00 owed — because an ENTER from an
    earlier run that afternoon was still the earliest one on file. F3 had the correct
    answer the whole time in its presence sessions; the question was never asked.
    """
    if claim.clock_since is None:
        return None, None
    return location.visit_window(db, claim.account_id, claim.facility_ref, claim.clock_since)


def clock(db: Session, claim: DetentionClaim, now: datetime) -> DetentionState:
    stop = loads.get_stop(db, claim.stop_ref)
    arrival, departure = _arrival_departure(db, claim)
    if claim.trigger == DetentionTrigger.appointment and stop.appointment_start is not None:
        trigger_time = stop.appointment_start
    else:
        trigger_time = arrival or now
    return compute_detention(
        trigger_time, claim.free_time_minutes, claim.detention_rate_cents_per_hour, now, departure
    )


# --- Counterparty notices (F8, contract-citing) ---
def _counterparty_email(db: Session, claim: DetentionClaim) -> str | None:
    if claim.counterparty_ref is None:
        return None
    cp = loads.get_counterparty(db, claim.counterparty_ref)
    return cp.contact_email if cp is not None else None


def send_pre_detention_notice(
    db: Session, claim: DetentionClaim, gateway, now: datetime
) -> notify.OutboundMessage | None:
    state = clock(db, claim, now)
    if state.phase != DetentionPhase.within_free_time:
        return None
    if state.free_time_remaining_seconds > PRE_DETENTION_THRESHOLD.total_seconds():
        return None
    return _send_counterparty(
        db,
        claim,
        gateway,
        now,
        subject="Free time expiring — detention will begin",
        body="Per the rate confirmation, free time is nearly used at this stop. "
        "Detention will begin accruing shortly.",
    )


def send_detention_start_notice(
    db: Session, claim: DetentionClaim, gateway, now: datetime
) -> notify.OutboundMessage | None:
    state = clock(db, claim, now)
    if state.phase == DetentionPhase.within_free_time:
        return None  # nothing owed yet — no notice to send
    message = _send_counterparty(
        db,
        claim,
        gateway,
        now,
        subject="Detention now accruing",
        body="Per the rate confirmation, free time has been exceeded at this stop; "
        "detention is now accruing at the contracted rate.",
    )
    claim.start_notice_sent_at = now  # record it so the Meter/evidence reflect it
    db.flush()
    return message


def _send_counterparty(db, claim, gateway, now, subject, body):
    to_ref = _counterparty_email(db, claim) or "counterparty@unknown"
    thread = notify.create_thread(
        db, claim.account_id, subject=subject, counterparty_ref=claim.counterparty_ref
    )
    return notify.send_counterparty_message(db, thread, body, gateway, to_ref, now=now)


# --- Shared invoice rail (reused by M4 accessorial claims) ---
def open_receivable(
    db: Session,
    account_id,
    kind,
    amount_cents: int,
    counterparty_ref=None,
    gateway=None,
    now: datetime | None = None,
    notice_subject: str = "Invoice",
    notice_body: str = "Please find attached the GPS-verified evidence and invoice "
    "per the rate confirmation.",
):
    receivable = ledger.create_receivable(
        db, account_id, kind, amount_cents, counterparty_ref=counterparty_ref
    )
    cp = None
    if counterparty_ref is not None:
        cp = loads.get_counterparty(db, counterparty_ref)
        if cp is not None:
            loads.record_claim(db, cp)
    if gateway is not None and counterparty_ref is not None:
        to_ref = (cp.contact_email if cp is not None else None) or "counterparty@unknown"
        thread = notify.create_thread(
            db, account_id, subject=notice_subject, counterparty_ref=counterparty_ref
        )
        notify.send_counterparty_message(db, thread, notice_body, gateway, to_ref, now=now)
    return receivable


# --- Claim pack on EXIT (M3-FR5 / FR9) ---
def generate_pack(db: Session, claim: DetentionClaim, now: datetime, gateway=None) -> dict:
    accrue_events(db, claim)
    state = clock(db, claim, now)
    claim.detention_seconds = state.detention_seconds
    claim.amount_cents = state.amount_cents

    log = db.get(evidence.EvidenceLog, claim.evidence_log_ref)
    evidence.anchor_chain(db, log)
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)

    receivable = None
    if claim.mode == ClaimMode.invoice and claim.amount_cents > 0:
        receivable = open_receivable(
            db,
            claim.account_id,
            ledger.ReceivableKind.detention,
            claim.amount_cents,
            counterparty_ref=claim.counterparty_ref,
            gateway=gateway,
            now=now,
            notice_subject="Detention invoice",
            notice_body="Please find attached the GPS-verified detention evidence and invoice "
            "per the rate confirmation.",
        )
        claim.receivable_ref = receivable.id
        claim.state = ClaimState.invoiced
    else:
        claim.state = ClaimState.exported  # company-driver: pack for carrier, no invoice
    db.flush()
    return {"pack": pack, "claim": claim, "receivable": receivable}


# --- Dunning cadence (M3-FR6) ---
def dunning_schedule(invoiced_at: datetime) -> list[dict]:
    actions = ["nudge", "firm", "escalation_offer"]
    return [
        {"day": day, "action": action, "at": invoiced_at + timedelta(days=day)}
        for day, action in zip(DUNNING_DAYS, actions, strict=True)
    ]


def escalate(db: Session, claim: DetentionClaim, external_ref: str | None = None) -> DetentionClaim:
    # AI-CONTEXT: M3-FR7 hand-off to the licensed collection partner — seam.
    # The partner integration + fee tier are wired at activation (F13 gate).
    claim.state = ClaimState.escalated
    db.flush()
    return claim


def get_claim(db: Session, claim_id) -> DetentionClaim | None:
    return db.get(DetentionClaim, claim_id)


def claim_for_stop(db: Session, stop_ref) -> DetentionClaim | None:
    return db.scalar(select(DetentionClaim).where(DetentionClaim.stop_ref == stop_ref))


def claim_evidence(db: Session, claim: DetentionClaim) -> dict:
    # read-only view of the claim's F4 evidence chain — what's IN the pack, so the
    # driver can see the GPS-verified proof behind their claim (M3-FR5)
    log = db.get(evidence.EvidenceLog, claim.evidence_log_ref) if claim.evidence_log_ref else None
    if log is None:
        return {"chain_valid": True, "record_count": 0, "artifact_count": 0, "timeline": []}
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)
    return {
        "chain_valid": pack.verification["chain_valid"],
        "record_count": pack.verification["record_count"],
        "artifact_count": len(pack.artifacts),
        "timeline": [
            {
                "type": t["type"],
                "occurred_at": t["occurred_at"].isoformat() if t["occurred_at"] else None,
            }
            for t in pack.timeline
        ],
    }
