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

from sqlalchemy import or_, select
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


# AI-CONTEXT: M2-FR3's source, living where the data does (§23 entry 87).
#
# "Detention-risk indicator per facility derived from M3 CLAIM EVENTS (rate of stops
# exceeding free time)." M2 shipped it as a stub — `{"rate": None, "basis":
# "m3_pending"}` — and the reason it stayed one is structural, not neglect:
# import-linter orders M2 before M3, so **M2 can never read a claim**. The indicator
# was specified into a module that cannot compute it.
#
# So it is computed here and composed at the router, exactly as M1's marketplace
# badges are (`_fuel_badge`) — the codebase's existing answer to "a module needs a
# later module's data".
#
# WHY EACH STOP'S OWN FREE TIME. M8 already has a `detention_risk_flag` that measures
# F3 dwell against a free time the CALLER supplies, which answers a different and also
# useful question: "given MY terms, how often does this dock blow them?" M2-FR3 is the
# facility's objective record, so it is measured against the free time each stop was
# actually contracted for. Two questions, two functions, neither redundant.
#
# ONLY FINISHED VISITS COUNT. A stop with no departure is still running, and counting
# it would score a dock on a driver who is standing in it. Claims whose visit F3 cannot
# resolve are skipped rather than assumed compliant.
FACILITY_STATS_SAMPLE_CAP = 50


def facility_detention_stats(db: Session, facility_id, limit: int = FACILITY_STATS_SAMPLE_CAP):
    """The rate of finished stops at this facility that ran past their free time.

    Bounded to the most recent `limit` claims: this feeds a map badge drawn per pin,
    and an unbounded per-facility scan would put a full claim history behind every
    overlay request.
    """
    claims = db.scalars(
        select(DetentionClaim)
        .where(DetentionClaim.facility_ref == facility_id)
        .order_by(DetentionClaim.created_at.desc())
        .limit(limit)
    ).all()
    finished = 0
    exceeded = 0
    for claim in claims:
        arrival, departure = _arrival_departure(db, claim)
        if arrival is None or departure is None:
            continue  # still on the dock, or F3 cannot place the visit
        finished += 1
        free_seconds = (claim.free_time_minutes or 0) * 60
        if (departure - arrival).total_seconds() > free_seconds:
            exceeded += 1
    return {
        # None, not 0.0 — "nobody has finished a tracked stop here" and "nobody has
        # ever been detained here" are different facts, and §11.7 forbids rendering
        # the first as the second
        "exceed_rate": (exceeded / finished) if finished else None,
        "sample_size": finished,
        "basis": "tracked_stops",
    }


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


# --- Driver alerts: the P0 §13.2 names first (§23 entries 106, 107) ---
#
# AI-CONTEXT: everything above this line tells the BROKER. Until now nothing told the
# DRIVER: §13.2's three P0 examples — detention started, booking failed, claim paid —
# had zero dispatch sites in the product, and M3 never called `notify.dispatch` at all.
#
# WHICH INSTANT. Owner decision, §23 entry 106: free-time expiry — the
# `within_free_time -> accruing` boundary `compute_detention` already computes as
# `trigger_time + free_time_minutes`. Not geofence ENTER, where §12.6's own copy
# ("Detention started · $75/h — Notice ready to send") is false in both halves: the
# amount owed is $0.00 and `send_detention_start_notice` refuses to send. Not the first
# billable minute either, which is not a distinct instant here — the clock accrues from
# second zero and M3 has no minimum billing increment to round to.
#
# NO NOTIFICATION CLASS. Also the owner's, and the reason is the point: a class is an
# OPT-IN bundle, and an opt-in switch on the one money-critical fact this product
# exists to tell a driver would let them be silently un-told. With no class registered,
# `dispatch` skips the class laws and applies the tier — P0 is "allowed always" (§13.2)
# and the warning below stays subject to quiet hours, RESTING and the 2/day budget.
DETENTION_START_CATEGORY = "detention_start"
FREE_TIME_WARNING_CATEGORY = "free_time_warning"
# AI-CONTEXT: how late a P0 may still be called news — and this was NOT theoretical.
# The first run of this job against the real dev database dispatched ELEVEN "Detention
# started" alerts at once, for claims whose free time had expired days earlier and
# whose drivers F3 still places on the dock. Every test was green: the suite knew the
# boundary, and only real data knew there was a backlog sitting behind it. On the
# deployed box that first tick would have been a burst of stale P0s to real accounts,
# each announcing a moment that had long passed.
#
# §13.2 defines P0 as time-sensitive, so lateness is not a delivery detail — past some
# point the event is simply not news, and there is no alert to send rather than a late
# one. The job runs every 60s, so this forgives half an hour of worker downtime and
# stays silent beyond it; the money is never lost, it is on the Claim screen and in the
# pack. It is also what makes deploying this safe: every claim that predates the
# feature is far outside the window and alerts nobody.
ALERT_FRESHNESS = timedelta(minutes=30)


def _rate_label(cents_per_hour: int | None) -> str | None:
    # §12.2 leads with the figure — but only when there is one. A claim with no
    # contracted rate says "Detention started" and nothing it cannot support.
    if not cents_per_hour:
        return None
    dollars = cents_per_hour / 100
    if cents_per_hour % 100 == 0:
        return f"${dollars:,.0f}/h"
    return f"${dollars:,.2f}/h"


def _alert_anchor(db: Session, claim: DetentionClaim) -> datetime | None:
    """The instant this claim's clock is anchored to, or None if nothing anchors it.

    AI-CONTEXT: found in the real data, not in the suite (§23 entry 107). `clock()`
    falls back to `trigger_time = arrival or now`, so a claim F3 cannot place has a
    trigger that slides forward on every call. With free time remaining that is
    harmless — the phase never reaches accruing. With free time of 0 or None it is
    not: `detention_start` equals `now` on every tick, so the claim reports
    "accruing, 0 seconds, $0.00" FOREVER and reads to an alerting job as a boundary
    crossed one second ago. FIVE live claims were in exactly that state, and each
    would have pushed a P0 announcing detention at a stop the driver never reached,
    for no money — the precise failure entry 106 rejected geofence ENTER to avoid.

    So an alert requires a REAL anchor: a resolved F3 arrival, or the appointment the
    claim was triggered on. A sliding `now` is the absence of one.

    The underlying fallback is left alone deliberately. It is the money core's, four
    callers depend on it, and narrowing it is a separate change on its own evidence —
    recorded as debt rather than smuggled into a notification feature.
    """
    stop = loads.get_stop(db, claim.stop_ref)
    if claim.trigger == DetentionTrigger.appointment and stop.appointment_start is not None:
        return stop.appointment_start
    arrival, _ = _arrival_departure(db, claim)
    return arrival


def _claim_deep_link(claim: DetentionClaim) -> str:
    # §13.5: the exact screen, never a tab root. ClaimSurface is keyed by the STOP and
    # is where the figure, the evidence and "Send notice" already live, so the driver
    # lands on the thing the notification is about.
    return f"/claim/{claim.stop_ref}"


def dispatch_detention_start(
    db: Session, claim: DetentionClaim, gateway, now: datetime
) -> object | None:
    """The P0. Fires once, at the instant money starts being owed.

    AI-CONTEXT: only while ACCRUING, never for a visit that has already ended. §13.2
    defines P0 as time-sensitive, and a P0 delivered after the driver has pulled off
    the dock is an interruption whose urgency expired — the money is not lost, it is on
    the Claim screen and in the pack, which is where a finished visit belongs. The same
    reasoning bounds lateness on the other side (`ALERT_FRESHNESS`). The consequence,
    stated rather than discovered: if the worker is down for more than half an hour
    across the boundary, that driver is never pushed about it.

    `driver_state` is left at F8's default. No server-side driver state exists to read
    (nothing in the tree computes one), and a driver accruing detention is by
    definition stationary at a dock — the DRIVING channel would be the wrong guess.
    """
    if claim.driver_start_alert_at is not None:
        return None
    if _alert_anchor(db, claim) is None:
        return None
    state = clock(db, claim, now)
    if state.phase != DetentionPhase.accruing:
        return None
    # `detention_seconds` is already exactly "how long ago the boundary was crossed",
    # so the freshness rule needs no second clock and cannot disagree with the first.
    # Nothing is marked on this path: a stale claim did not have its alert suppressed,
    # it never had an alert to send, and recording one would say otherwise.
    if state.detention_seconds > ALERT_FRESHNESS.total_seconds():
        return None
    rate = _rate_label(claim.detention_rate_cents_per_hour)
    title = f"Detention started · {rate}" if rate else "Detention started"
    # §12.6 verbatim for the invoicing driver. A company driver cannot bill anyone, so
    # promising them a notice would name an action their mode does not have (M3-FR9).
    action = (
        "Notice ready to send."
        if claim.mode == ClaimMode.invoice
        else "Your evidence pack is recording."
    )
    notification = notify.dispatch(
        db,
        claim.account_id,
        notify.NotificationTier.P0,
        DETENTION_START_CATEGORY,
        title,
        f"Free time is used up at this stop. {action}",
        _claim_deep_link(claim),
        gateway,
        now=now,
        subject_ref=str(claim.id),
    )
    claim.driver_start_alert_at = now
    db.flush()
    return notification


def dispatch_free_time_warning(
    db: Session, claim: DetentionClaim, gateway, now: datetime
) -> object | None:
    """The P1 §13.2 names beside it — measured from the SAME boundary.

    AI-CONTEXT: "free time 30-min warning" is defined relative to the instant entry 106
    settled, so the two notifications cannot be computed from different starts. It
    reports the minutes actually remaining rather than the constant 30: a worker that
    was down for twenty minutes must not tell a driver they have thirty left.
    """
    if claim.driver_warning_alert_at is not None:
        return None
    if _alert_anchor(db, claim) is None:
        return None
    state = clock(db, claim, now)
    if state.phase != DetentionPhase.within_free_time:
        return None
    remaining = state.free_time_remaining_seconds
    if remaining > PRE_DETENTION_THRESHOLD.total_seconds():
        return None
    minutes = max(1, int(remaining // 60))
    rate = _rate_label(claim.detention_rate_cents_per_hour)
    body = f"Detention starts after that at {rate}." if rate else "Detention starts after that."
    notification = notify.dispatch(
        db,
        claim.account_id,
        notify.NotificationTier.P1,
        FREE_TIME_WARNING_CATEGORY,
        f"{minutes} min free time left",
        body,
        _claim_deep_link(claim),
        gateway,
        now=now,
        subject_ref=str(claim.id),
    )
    claim.driver_warning_alert_at = now
    db.flush()
    return notification


def claims_awaiting_alerts(db: Session) -> list[DetentionClaim]:
    """The undecided set: open claims still owed at least one of the two alerts.

    AI-CONTEXT: NOT capped. A silent top-N here would mean some driver's P0 is dropped
    on a busy afternoon and the summary still reads as though everything was covered.
    The set bounds itself instead — a claim leaves it as soon as both alerts have been
    dispatched, and the partial index in migration 0054 is built on exactly this
    predicate. The residue is claims that can no longer produce either alert — ended
    inside free time, or accruing from before `ALERT_FRESHNESS` — and never packed.
    They are re-evaluated cheaply and never fire; `scanned` in the job summary is what
    shows it if that residue ever stops being small.
    """
    return list(
        db.scalars(
            select(DetentionClaim).where(
                DetentionClaim.state == ClaimState.open,
                DetentionClaim.clock_since.is_not(None),
                or_(
                    DetentionClaim.driver_start_alert_at.is_(None),
                    DetentionClaim.driver_warning_alert_at.is_(None),
                ),
            )
        )
    )


def dispatch_clock_alerts(db: Session, gateway, now: datetime | None = None) -> dict:
    """Walk the undecided claims and fire whichever alert has come due.

    AI-CONTEXT: this is the thing that was missing, not the copy. `clock()` is computed
    on READ, so before this job the instant free time expired passed unobserved unless
    a driver happened to open the screen. Each claim costs its own `clock()` — a stop
    read and an F3 visit window — which is a per-claim query pattern this codebase has
    been bitten by (§23 entry 98). It is deliberate here and bounded: the set is open
    claims only, it runs on the worker rather than in a request, and the alternative is
    a bulk read across F5 and F3 for a set that is normally a handful of rows. If
    `scanned` ever stops being small, batch it then and not before.

    A claim whose F3 arrival cannot be resolved computes `trigger_time` from `now` on
    every call and therefore never reaches `accruing` — no alert fires for it, ever
    (§23 entry 106, caveat b). That is pre-existing behaviour, recorded here because
    this job is where its consequence becomes visible.
    """
    now = now or datetime.now(UTC)
    claims = claims_awaiting_alerts(db)
    started = 0
    warned = 0
    for claim in claims:
        if dispatch_detention_start(db, claim, gateway, now) is not None:
            started += 1
        elif dispatch_free_time_warning(db, claim, gateway, now) is not None:
            warned += 1
    return {"scanned": len(claims), "started": started, "warned": warned}


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


def claim_for_receivable(db: Session, receivable_ref) -> DetentionClaim | None:
    # AI-CONTEXT: the reverse of `open_receivable` — money back to the stop it came
    # from. §13.5 needs it: a "claim paid" notification must deep-link to the exact
    # claim, and a receivable on its own knows only an account and an amount.
    return db.scalar(
        select(DetentionClaim).where(DetentionClaim.receivable_ref == receivable_ref)
    )


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
