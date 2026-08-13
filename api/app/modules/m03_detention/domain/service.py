"""AI-CONTEXT: M3 Detention Tracker & Recovery (PRD §8.3) — the differentiator.
Zero-effort GPS-evidenced detention: the driver drives to the stop and does
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

from sqlalchemy import case, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.foundation.f01_identity import public as identity
from app.foundation.f03_location import public as location
from app.foundation.f04_evidence import public as evidence
from app.foundation.f05_load import public as loads
from app.foundation.f07_ledger import public as ledger
from app.foundation.f08_notifications import public as notify

from . import messages
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

    flags.register_flag(
        db, FLAG_KEY, description="M3 Detention Tracker & Recovery", default_on=True
    )
    for gate in GATES:
        flags.add_gate(db, FLAG_KEY, gate)
    from app.foundation.f14_admin import public as admin

    admin.register_admin_view(db, "m03.claims", MODULE, "Claims Pipeline", "/admin/m03/claims")
    from app.foundation.f15_localization import public as localization

    localization.register_catalogue(db, messages.KEY_PREFIX, messages.ALERT_MESSAGES)


# AI-CONTEXT: finding N-02 — these alerts were English literals. F8 resolves the driver's
# locale (it is what already knows the account) and falls back to the compiled English
# below if a catalogue row is missing, so a translation gap can never silence a P0.
def _alert(db: Session, account_id, key: str, **values) -> str:
    return notify.localized_text(
        db,
        account_id,
        messages.KEY_PREFIX + key,
        messages.ALERT_MESSAGES[key][messages.DEFAULT_LOCALE_KEY],
        **values,
    )


def _default_mode(db: Session, account_id) -> ClaimMode:
    profile = db.get(identity.DriverProfile, account_id)
    return ClaimMode.invoice if identity.can_invoice(profile) else ClaimMode.evidence_only


class EvidenceCheckFailed(Exception):
    """This claim's evidence chain does not verify, so nothing was sent (finding F4-3).

    AI-CONTEXT: F4 refuses at `share_pack` — the chokepoint every pack path crosses — and
    this is M3 turning that refusal into something a driver can read. It is deliberately
    NOT a silent no-op: a claim that cannot be filed is the one fact the driver most needs,
    because the alternative is a Meter frozen on money nobody was ever told about.
    """

    def __init__(self, verification=None):
        self.verification = verification
        super().__init__("evidence chain invalid — the pack was not sent")


class ClaimAlreadyFiled(Exception):
    """This claim has left `open` — it cannot be filed a second time (finding F2).

    Carries the claim so a caller can answer "already filed" with the receivable the
    FIRST filing opened, rather than reporting a failure for work that succeeded.
    """

    def __init__(self, claim: DetentionClaim):
        self.claim = claim
        super().__init__(f"claim {claim.id} is {claim.state.value}, not open")


def open_claim_for_stop(db: Session, stop_ref) -> DetentionClaim | None:
    """The one open claim for this stop, which `uq_detention_claim_open_stop` guarantees."""
    return db.scalar(
        select(DetentionClaim).where(
            DetentionClaim.stop_ref == stop_ref,
            DetentionClaim.state == ClaimState.open,
        )
    )


def start_claim(
    db: Session,
    stop,
    mode: ClaimMode | None = None,
    trigger: DetentionTrigger = DetentionTrigger.arrival,
    started_at: datetime | None = None,
) -> DetentionClaim:
    """Get-or-create. Returns this stop's open claim, creating one only if none exists.

    AI-CONTEXT: finding F1. This created a claim unconditionally, and the arrival endpoint
    wrapped it in `claim_for_stop(...) or start_claim(...)` — a check-then-act over rows a
    concurrent transaction has not committed yet. Two arrivals for one stop both missed
    and both inserted, and from then on `claim_for_stop`'s `db.scalar` RAISED on the pair
    it found: every read of that stop's money broke, permanently, from one double-tap.

    The database now refuses the second row, so the race is a caught `IntegrityError`
    rather than a corrupted stop. The insert runs inside a SAVEPOINT because a failed
    flush poisons the whole session otherwise, and the caller here — an arrival — has
    already written a geofence event and a stop event it must not lose.
    """
    existing = open_claim_for_stop(db, stop.id)
    if existing is not None:
        return existing

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
    try:
        with db.begin_nested():
            db.add(claim)
            db.flush()
    except IntegrityError:
        db.expunge(claim)
        winner = open_claim_for_stop(db, stop.id)
        if winner is None:
            raise  # the constraint fired for some other reason — do not swallow it
        return winner
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


# --- What "sent" means (finding F5) ---
#
# AI-CONTEXT: the rule this section installs, in one line: **"sent" means the linked
# message row has `sent_at` — never merely that a message object came back.**
#
# `POST /load/{stop_id}/notice` returned `{"sent": message is not None}`, set
# `start_notice_sent_at`, and appended a `notice_sent` record into the TAMPER-EVIDENT
# EVIDENCE LOG — all of it on the strength of an object existing. `send_counterparty_message`
# always returns one: on an SMTP failure it returns a row with a `smtp-failed-…` ref and
# `sent_at = NULL`, because a gateway may never fail its caller (F-06). So the three
# assertions fired over a mail that never left, and the worst of them is the evidence
# record — "we notified the broker at 10:05" is the fact a detention dispute turns on, and
# it was going into the legal pack for an email sitting in a dead-letter queue.
#
# The five states below are DERIVED from the message row on every read rather than
# cached, so a send that fails now and succeeds later on the retry sweep tells the truth
# without anything having to remember to update the claim.
DELIVERY_SENT = "sent"
DELIVERY_QUEUED = "queued"
DELIVERY_RETRYING = "retrying"
DELIVERY_FAILED = "failed"
DELIVERY_NO_EMAIL = "no_email"
DELIVERY_NOT_SENT = "not_sent"


def delivery_of(message) -> str | None:
    """One message row's delivery state, or None when there is no row to read.

    Split out because the PRE-DETENTION warning (F7) is a different message with the same
    question asked of it, and two copies of this ladder would drift.
    """
    if message is None:
        return None
    if message.sent_at is not None:
        return DELIVERY_SENT
    # AI-CONTEXT: the SIXTH state, and without it moving sends off the request thread
    # would have replaced one lie with its opposite.
    #
    # A row that has never been attempted has `provider_ref` NULL, which is not a failure
    # — `is_retryable(None)` is False because it asks "is this failure worth another go?"
    # of something nothing has tried. So this ladder fell straight through to FAILED, and
    # a driver who tapped Send would have read **"Notice failed — broker not reached"**
    # about a notice sitting correctly in the outbox, seconds before it went.
    #
    # QUEUED is what the row actually says: we hold it, it has not gone yet. It resolves
    # to `sent` on the next `outbound_mail` sweep, within a minute.
    if message.provider_ref is None and message.attempts == 0:
        return DELIVERY_QUEUED
    if notify.is_retryable(message.provider_ref) and message.attempts < notify.MAX_SEND_ATTEMPTS:
        return DELIVERY_RETRYING
    return DELIVERY_FAILED


def notice_delivery(db: Session, claim: DetentionClaim) -> str:
    """What actually happened to this claim's start notice, read off the F8 row.

    ACCEPTED ASYMMETRY, stated rather than discovered: a send that fails now and succeeds
    later via `retry_unsent_messages` will read `sent` here — this is computed live — but
    gains no `notice_sent` evidence record, because nothing re-enters that code path. So
    the evidence pack UNDERSTATES what happened. That is the correct direction for a legal
    document: a pack that omits a notice the broker did receive costs the driver an
    argument, while a pack that asserts one they did not costs them the claim.
    """
    ref = claim.start_notice_message_ref
    if ref is not None:
        state = delivery_of(db.get(notify.OutboundMessage, ref))
        if state is not None:
            return state
    # nothing on file. Which of the two reasons is the difference between "tap Send" and
    # "there is nobody to send it to", and only the second is the driver's to fix.
    if _counterparty_email(db, claim) is None:
        return DELIVERY_NO_EMAIL
    return DELIVERY_NOT_SENT


def reconcile_delivered_notices(db: Session, delivered: list) -> int:
    """Close the loop after the sweep actually delivers. Returns how many claims moved.

    AI-CONTEXT: this exists because moving sends off the request thread would otherwise
    have quietly weakened every detention pack in the product.

    `notice_delivery` above records an "ACCEPTED ASYMMETRY": a message that fails now and
    succeeds later on the sweep reads `sent` — that state is computed live — but gains no
    `notice_sent` evidence record, because nothing re-enters this code path. The reasoning
    was sound while the sweep only caught rare failures, and it even chose the safe
    direction: a pack that omits a notice the broker DID receive costs the driver an
    argument, while one asserting a notice they did not costs them the claim.

    Asynchronous sending makes that rare case the ONLY case. Every notice would now be
    delivered by the sweep, so every pack would omit the line — "we notified the broker at
    10:05" is the fact a detention dispute turns on, and it would have silently stopped
    being written for anybody. The asymmetry had to be closed rather than inherited.

    Three things kept exactly as the synchronous path had them:
      · the timestamp is the message's own `sent_at`, not "now" — the pack states when the
        broker was reached, not when a janitor noticed
      · ONLY the start notice writes `notice_sent`. A pre-detention WARNING is a different
        fact (F7), and filing it here would put a claim in the pack nothing supports
      · the record is appended once. `start_notice_sent_at` already being set is what says
        this claim has been through here, so a re-run cannot append a second entry to a
        hash-chained log.
    """
    if not delivered:
        return 0
    by_id = {m.id: m for m in delivered}
    claims = db.scalars(
        select(DetentionClaim).where(
            DetentionClaim.start_notice_message_ref.in_(list(by_id)),
            DetentionClaim.start_notice_sent_at.is_(None),
        )
    ).all()
    moved = 0
    for claim in claims:
        message = by_id.get(claim.start_notice_message_ref)
        if message is None or message.sent_at is None:
            continue
        claim.start_notice_sent_at = message.sent_at
        stop = loads.get_stop(db, claim.stop_ref)
        if stop is not None:
            loads.record_stop_event(db, stop, loads.EVENT_NOTICE_SENT, message.sent_at)
        moved += 1
    db.flush()
    return moved


def send_pre_detention_notice(
    db: Session, claim: DetentionClaim, gateway, now: datetime
) -> notify.OutboundMessage | None:
    state = clock(db, claim, now)
    if state.phase != DetentionPhase.within_free_time:
        return None
    if state.free_time_remaining_seconds > PRE_DETENTION_THRESHOLD.total_seconds():
        return None
    if claim.pre_notice_sent_at is not None:
        return None  # one warning per stop; the window is half an hour, the job is not
    message = _send_counterparty(
        db,
        claim,
        gateway,
        now,
        subject="Free time expiring — detention will begin",
        body="Per the rate confirmation, free time is nearly used at this stop. "
        "Detention will begin accruing shortly.",
    )
    if message is None:
        return None  # no counterparty email (finding F4)
    # AI-CONTEXT: its OWN column, deliberately. `start_notice_sent_at` means the broker was
    # told the clock STARTED, which is the fact the `notice_sent` evidence record asserts
    # and the fact a dispute turns on. A warning that detention is ABOUT to begin is not
    # that fact, and writing it here would make the evidence pack claim a notice that was
    # never sent — the exact defect F5 closes one function up.
    claim.pre_notice_sent_at = now
    db.flush()
    return message


def _existing_start_notice(db: Session, claim: DetentionClaim):
    """The message that stands in the way of a fresh send, or None if nothing does.

    AI-CONTEXT: **a fresh send is allowed exactly when re-sending cannot double-notify.**
    The previous session guarded only the QUEUED case, which left the delivered one open:
    a claim whose notice had actually gone fell straight through and sent a SECOND email to
    the broker — and, because the route appends `notice_sent` on synchronous success, wrote
    a second record into the tamper-evident evidence log for one stop. The UI hid it (the
    rung retires once `notice_sent`), so it needed a replayed request — which is exactly
    what the offline write queue exists to produce.

    The five cases, in one place:

      no linked message              -> send        (nothing to double)
      linked and DELIVERED           -> never       (the broker has it; this is the dispute
                                                     anchor and it may not be re-anchored)
      linked, failed, RETRYABLE,
        and addressed to the address
        now on file                  -> never       (`retry_unsent_messages` owns that row)
      linked, failed PERMANENTLY,
        or attempts exhausted        -> send fresh
      linked, failed to a DIFFERENT
        address than the one on file -> send fresh

    The last case is what makes this session's whole point work. A broker whose address was
    wrong produces `SMTPRecipientsRefused`, which is permanent and correctly never retried
    — so without an address-aware rule, fixing the address would leave the notice
    unsendable forever. The old row is left untouched as history; the claim relinks.
    """
    ref = claim.start_notice_message_ref
    if ref is None:
        return None
    message = db.get(notify.OutboundMessage, ref)
    if message is None:
        return None  # the ref points at nothing — treat it as never sent
    if message.sent_at is not None:
        return message
    # AI-CONTEXT: a SIXTH case, and without it asynchronous sending re-opens the exact
    # defect the five above were written to close.
    #
    # A queued notice has never been attempted, so `is_retryable(None)` is False and it
    # fell through every branch below to "send fresh" — meaning a second tap, a replayed
    # offline write, or simply a driver returning to the screen inside the sweep's minute
    # would have created a SECOND message row for the same claim and mailed the broker
    # twice. §23 entry 136 fixed that once at the UI (`onSendNotice` had no in-flight
    # guard and "genuinely sent a broker two emails on a double tap"); deferring the send
    # widened the window from one round trip to a whole sweep interval, where a guard on
    # the client cannot reach.
    #
    # Addressed-to-the-current-address for the same reason as the retryable case: if the
    # driver has since corrected the broker's email, the queued row is going to the wrong
    # place and a fresh one is right.
    queued = message.provider_ref is None and message.attempts == 0
    retryable = notify.is_retryable(message.provider_ref) and (
        message.attempts < notify.MAX_SEND_ATTEMPTS
    )
    if (queued or retryable) and message.to_ref == _counterparty_email(db, claim):
        return message
    return None


def send_detention_start_notice(
    db: Session, claim: DetentionClaim, gateway, now: datetime
) -> notify.OutboundMessage | None:
    state = clock(db, claim, now)
    if state.phase == DetentionPhase.within_free_time:
        return None  # nothing owed yet — no notice to send
    existing = _existing_start_notice(db, claim)
    if existing is not None:
        return existing
    message = _send_counterparty(
        db,
        claim,
        gateway,
        now,
        subject="Detention now accruing",
        body="Per the rate confirmation, free time has been exceeded at this stop; "
        "detention is now accruing at the contracted rate.",
    )
    if message is None:
        return None  # no counterparty email — nothing was addressed, nothing was sent
    # the ref records that we DECIDED to send, on every attempt; the timestamp records
    # that it WENT, and only the message row knows that (finding F5)
    claim.start_notice_message_ref = message.id
    if message.sent_at is not None:
        claim.start_notice_sent_at = now
    db.flush()
    return message


def _send_counterparty(db, claim, gateway, now, subject, body):
    """None when there is no counterparty email — no thread, no row, no gateway call.

    AI-CONTEXT: finding F4. This addressed an invented `counterparty@unknown`, which is not
    an address anywhere. Against the recording gateway it looked like a send; against real
    SMTP it is an `SMTPRecipientsRefused`, which `PERMANENT_FAILURES` correctly refuses to
    retry — so the notice was unrecoverable — while the driver-facing path reported
    success over it. Refusing BEFORE the gateway leaves nothing on file, which is what
    lets `notice_delivery` say `no_email` and name the one thing that fixes it.
    """
    to_ref = _counterparty_email(db, claim)
    if not to_ref:
        return None
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
    title = (
        _alert(db, claim.account_id, "detention_started.title", rate=rate)
        if rate
        else _alert(db, claim.account_id, "detention_started.title_no_rate")
    )
    # §12.6 verbatim for the invoicing driver. A company driver cannot bill anyone, so
    # promising them a notice would name an action their mode does not have (M3-FR9).
    action = _alert(
        db,
        claim.account_id,
        "detention_started.action_invoice"
        if claim.mode == ClaimMode.invoice
        else "detention_started.action_record",
    )
    notification = notify.dispatch(
        db,
        claim.account_id,
        notify.NotificationTier.P0,
        DETENTION_START_CATEGORY,
        title,
        _alert(db, claim.account_id, "detention_started.body", action=action),
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
    body = (
        _alert(db, claim.account_id, "free_time_warning.body", rate=rate)
        if rate
        else _alert(db, claim.account_id, "free_time_warning.body_no_rate")
    )
    notification = notify.dispatch(
        db,
        claim.account_id,
        notify.NotificationTier.P1,
        FREE_TIME_WARNING_CATEGORY,
        _alert(db, claim.account_id, "free_time_warning.title", minutes=minutes),
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
    delivered = 0
    for claim in claims:
        # AI-CONTEXT: `gateway` may be a gateway or a FACTORY taking (db, account_id).
        # Web Push is addressed to one driver's browsers, so a scan across many claims
        # cannot share one instance; a plain gateway still works for tests and for the
        # single-claim callers above.
        gw = gateway(db, claim.account_id) if callable(gateway) else gateway
        if dispatch_detention_start(db, claim, gw, now) is not None:
            started += 1
        elif dispatch_free_time_warning(db, claim, gw, now) is not None:
            warned += 1
        else:
            continue
        delivered += getattr(gw, "delivered", len(getattr(gw, "sent", ())))
    return {
        "scanned": len(claims),
        "started": started,
        "warned": warned,
        "delivered": delivered,
    }


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
    notice_body: str = "Please find attached the GPS evidence and invoice "
    "per the rate confirmation.",
    external_ref: str | None = None,
):
    # `external_ref` is the caller's idempotency key, unique where present
    # (`uq_receivable_external_ref`). M3 passes `m03:<claim_id>`; M4 does not pass one
    # yet, which is a named follow-up rather than a silent expectation.
    receivable = ledger.create_receivable(
        db, account_id, kind, amount_cents, counterparty_ref=counterparty_ref,
        external_ref=external_ref,
    )
    cp = None
    if counterparty_ref is not None:
        cp = loads.get_counterparty(db, counterparty_ref)
        if cp is not None:
            loads.record_claim(db, cp)
    to_ref = cp.contact_email if cp is not None else None
    # finding F4: no address, no send. The receivable is still opened — the driver is
    # owed the money whether or not we hold an email for the broker — but an invoice
    # addressed to `counterparty@unknown` is a bounce that the F8 row then reported as
    # delivered. The claim screen's `no_email` state is what tells the driver to add it.
    if gateway is not None and counterparty_ref is not None and to_ref:
        thread = notify.create_thread(
            db, account_id, subject=notice_subject, counterparty_ref=counterparty_ref
        )
        notify.send_counterparty_message(db, thread, notice_body, gateway, to_ref, now=now)
    return receivable


def _location_basis_for(db: Session, claim: DetentionClaim) -> dict | None:
    """The visit's location basis, for the pack's honesty section (D6).

    Bounded to the VISIT, not the claim's whole life: the question a broker is judging is
    the quality of the fixes behind this stop's arrival and departure. Falls back to the
    clock window when F3 cannot place the visit, and returns None when there is no window
    to ask about — which renders as nothing rather than as a zero.
    """
    arrival, departure = _arrival_departure(db, claim)
    since = arrival or claim.clock_since
    until = departure or datetime.now(UTC)
    if since is None:
        return None
    return location.location_basis(db, claim.account_id, since, until)


def render_pack_bytes(db: Session, pack, claim: DetentionClaim | None = None) -> bytes:
    """`render_pack_pdf(pack, context)` — the db is not a parameter, and the context is
    what carries the artifact images. M5 builds the same thing one module over; this
    stays minimal deliberately, because M3's pack is composed from the evidence log
    rather than from a photo set."""
    context = evidence.PackContext(
        location_basis=_location_basis_for(db, claim) if claim is not None else None
    )
    return evidence.render_pack_pdf(pack, context)


def _notice_body(db: Session, shared) -> str:
    """§12.1: state facts and next steps. An honest body names where the evidence IS —
    and when this deployment cannot address itself, says so rather than printing a link
    that goes nowhere.

    The URL is built by F4, which issued the token. It was built here first and moved
    the moment a second caller needed it, which is the whole of §23 entry 94's lesson."""
    link = evidence.share_link(shared)
    where = (
        f"The GPS evidence for this detention is here: {link}"
        if link
        else "The GPS evidence pack for this detention is available on request."
    )
    return (
        f"{where}\n\n"
        "The invoice is raised per the rate confirmation's detention terms."
    )


# --- Claim pack on EXIT (M3-FR5 / FR9) ---
def generate_pack(db: Session, claim: DetentionClaim, now: datetime, gateway=None) -> dict:
    """File the claim: pack, share link, invoice, receivable. ONCE.

    AI-CONTEXT: finding F2. There was no guard of any kind here, so `POST /load/{id}/claim`
    twice re-invoiced the broker and opened a SECOND receivable for one detention — the
    driver's own money surface then showing twice what they were owed, and the broker
    holding two invoices for one stop. The state guard answers the double-tap;
    `uq_receivable_external_ref` answers the concurrent one, because the ref is derived
    from the claim rather than generated per call.
    """
    if claim.state != ClaimState.open:
        raise ClaimAlreadyFiled(claim)
    accrue_events(db, claim)
    state = clock(db, claim, now)
    claim.detention_seconds = state.detention_seconds
    claim.amount_cents = state.amount_cents

    log = db.get(evidence.EvidenceLog, claim.evidence_log_ref)
    evidence.anchor_chain(db, log)
    pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)

    # AI-CONTEXT: the notice used to say "please find attached" and attach nothing.
    # `send_email(to_ref, subject, body)` is the WHOLE F8 gateway protocol — there is no
    # attachment parameter in any of its four implementations — so the broker received a
    # claim about evidence they had no way to reach. Every piece needed already existed
    # and had simply never been connected on this path: F4 pins the rendered bytes and
    # issues a token, and `/pack/s/<token>` serves the PDF. M5 has used both since it
    # shipped. This is M3's wedge document, so it is the worst place in the product for
    # prose to be describing a behaviour nobody checked (§23 entry 116, addressed to a
    # counterparty instead of a developer).
    try:
        shared = evidence.share_pack(
            db,
            log,
            pack.template,
            render_pack_bytes(db, pack, claim),
            claim.account_id,
            now=now,
        )
    except evidence.ChainInvalid as exc:
        # nothing is pinned, no link is minted and no email goes out — and the claim is
        # left OPEN rather than marked filed, so the driver's money is still claimable
        # once whatever broke the chain is understood
        raise EvidenceCheckFailed(exc.verification) from exc

    receivable = None
    if claim.mode == ClaimMode.invoice and claim.amount_cents > 0:
        try:
            with db.begin_nested():
                receivable = open_receivable(
                    db,
                    claim.account_id,
                    ledger.ReceivableKind.detention,
                    claim.amount_cents,
                    counterparty_ref=claim.counterparty_ref,
                    gateway=gateway,
                    now=now,
                    notice_subject="Detention invoice",
                    notice_body=_notice_body(db, shared),
                    external_ref=f"{MODULE}:{claim.id}",
                )
        except IntegrityError:
            # the concurrent filing the state guard cannot see: another transaction has
            # already opened this claim's receivable and committed. Re-read and answer
            # "already filed" — the work succeeded, it just was not ours.
            db.refresh(claim)
            raise ClaimAlreadyFiled(claim) from None
        claim.receivable_ref = receivable.id
        claim.state = ClaimState.invoiced
    else:
        claim.state = ClaimState.exported  # company-driver: pack for carrier, no invoice
    db.flush()
    return {"pack": pack, "claim": claim, "receivable": receivable, "shared": shared}


# --- Dunning cadence (M3-FR6) ---
def dunning_schedule(invoiced_at: datetime) -> list[dict]:
    actions = ["nudge", "firm", "escalation_offer"]
    return [
        {"day": day, "action": action, "at": invoiced_at + timedelta(days=day)}
        for day, action in zip(DUNNING_DAYS, actions, strict=True)
    ]


def escalate(db: Session, claim: DetentionClaim, external_ref: str | None = None) -> DetentionClaim:
    # AI-CONTEXT: M3-FR7 hand-off to the licensed collection partner — still a seam. The
    # partner integration + fee tier are wired at activation (F13 gate).
    #
    # `external_ref` was accepted and DISCARDED (finding F6): a claim handed to a partner
    # kept no way back to the file they opened, so the one fact the hand-off produces was
    # thrown away at the moment it was created. Kept now, and deliberately not overwritten
    # with None — re-escalating without a ref must not erase the one already on file.
    claim.state = ClaimState.escalated
    if external_ref is not None:
        claim.escalation_ref = external_ref
    db.flush()
    return claim


# --- Dunning (M3-FR6), which had never run ---
#
# AI-CONTEXT: finding F6. `dunning_schedule` computed day 3 / 10 / 21 correctly and had
# exactly ONE caller in the tree: its own unit test. No job walked invoiced claims, so no
# broker has ever been chased for a detention invoice, and the cadence the PRD promises
# was three lines of arithmetic nobody ran.
#
# THREE BOUNDS, and each is here because the first run of a job like this meets a BACKLOG
# rather than a steady state — which is not hypothetical: `dispatch_detention_start`'s
# first run against real data fired ELEVEN stale P0s at once (§23 entry 106).
#
#   · the scan is bounded to receivables opened in the last 28 days, so the set cannot
#     grow without limit as the product ages;
#   · an action more than 7 days past due is counted `skipped_stale` and never sent, so
#     switching this on cannot spray a year of missed follow-ups at real brokers in one
#     tick. Nothing is marked on that path — a stale action was not suppressed, it never
#     had a send to make, and recording one would say otherwise;
#   · day 21 offers escalation to a collection partner, and may only be sent when
#     `collection_partner_agreement` is SATISFIED. Otherwise `skipped_ungated`. The
#     product must not offer a driver a path it does not have — which is exactly what
#     F13's gates exist to prevent, and exactly what they were failing to prevent before
#     migration 0066.
DUNNING_ACTIONS = ["nudge", "firm", "escalation_offer"]
DUNNING_COLUMN = {
    "nudge": "dunning_nudge_sent_at",
    "firm": "dunning_firm_sent_at",
    "escalation_offer": "dunning_escalation_offer_sent_at",
}
DUNNING_COUNTER = {"nudge": "nudged", "firm": "firmed", "escalation_offer": "offered"}
# distinct and greppable, so an AP clerk's thread and our own logs both say which of the
# three a broker actually received
DUNNING_SUBJECT = {
    "nudge": "Detention invoice — payment reminder",
    "firm": "Detention invoice — second request",
    "escalation_offer": "Detention invoice — final notice before collection",
}
DUNNING_GRACE = timedelta(days=7)
# 28 = 21 + 7, and the two are NOT independent knobs. The window must be at least the last
# action's day plus its grace, or the escalation offer could fall out of the scan set while
# it is still current — a follow-up that silently never sends, which is F6's own shape.
# Pinned by a test so a later edit to either number has to look at the other.
DUNNING_WINDOW = timedelta(days=max(DUNNING_DAYS)) + DUNNING_GRACE
ESCALATION_GATE = "collection_partner_agreement"
DUNNING_TERMINAL_STATES = ("recovered", "escalated")


def _escalation_gate_satisfied(db: Session) -> bool:
    from app.foundation.f13_flags import public as flags

    gate = flags.get_gate(db, FLAG_KEY, ESCALATION_GATE)
    return bool(gate is not None and gate.satisfied)


def claims_awaiting_dunning(db: Session, now: datetime) -> list[DetentionClaim]:
    """Invoiced claims, still unpaid, opened recently enough to still be worth chasing."""
    terminal = [s for s in ledger.ReceivableState if s.value in DUNNING_TERMINAL_STATES]
    return list(
        db.scalars(
            select(DetentionClaim)
            .join(ledger.Receivable, ledger.Receivable.id == DetentionClaim.receivable_ref)
            .where(
                DetentionClaim.state == ClaimState.invoiced,
                ledger.Receivable.state.not_in(terminal),
                ledger.Receivable.created_at >= now - DUNNING_WINDOW,
                or_(
                    DetentionClaim.dunning_nudge_sent_at.is_(None),
                    DetentionClaim.dunning_firm_sent_at.is_(None),
                    DetentionClaim.dunning_escalation_offer_sent_at.is_(None),
                ),
            )
        )
    )


def _dunning_body(db: Session, claim: DetentionClaim, now: datetime) -> str:
    """Self-contained, and English like every other counterparty message.

    Each notice restates the amount, the dock, the service date and carries a FRESH
    evidence link, because it must never presume an earlier email arrived — the whole
    reason a broker is being chased is that something did not land.
    """
    stop = loads.get_stop(db, claim.stop_ref)
    log = db.get(evidence.EvidenceLog, claim.evidence_log_ref)
    where = "The GPS evidence pack for this detention is available on request."
    if log is not None:
        pack = evidence.compose_pack(db, log, evidence.PackTemplate.detention_claim)
        try:
            shared = evidence.share_pack(
                db,
                log,
                pack.template,
                render_pack_bytes(db, pack, claim),
                claim.account_id,
                now=now,
            )
        except evidence.ChainInvalid:
            # a chaser must not carry a link to a pack that failed its own check. The
            # dunning notice still goes — the invoice is owed either way — and it simply
            # does not offer evidence it cannot stand behind. The refusal is logged at the
            # chokepoint; raising here would silence a legitimate follow-up.
            shared = None
        link = evidence.share_link(shared) if shared is not None else None
        if link:
            where = f"The GPS evidence for this detention is here: {link}"
    amount = f"${claim.amount_cents / 100:,.2f}"
    served = claim.clock_since.date().isoformat() if claim.clock_since else "the service date"
    # the LOAD REFERENCE, not a facility id — A1's subject line already established that
    # the thing an accounts-payable clerk files by is the reference they were given, and a
    # UUID from our database means nothing on their desk
    load = loads.get_load(db, stop.load_id) if stop is not None else None
    reference = getattr(load, "reference_number", None)
    which = f" on load {reference}" if reference else ""
    return (
        f"Detention of {amount} was invoiced per the rate confirmation for the stop"
        f"{which} served on {served}, and remains outstanding.\n\n{where}"
    )


def run_dunning(db: Session, gateway, now: datetime | None = None) -> dict:
    """Walk invoiced claims and send whichever follow-up has come due."""
    now = now or datetime.now(UTC)
    claims = claims_awaiting_dunning(db, now)
    summary = {
        "scanned": len(claims),
        "nudged": 0,
        "firmed": 0,
        "offered": 0,
        "skipped_no_email": 0,
        "skipped_stale": 0,
        "skipped_ungated": 0,
    }
    gate_open = _escalation_gate_satisfied(db)
    for claim in claims:
        receivable = db.get(ledger.Receivable, claim.receivable_ref)
        if receivable is None:
            continue
        for entry in dunning_schedule(receivable.created_at):
            action = entry["action"]
            column = DUNNING_COLUMN[action]
            if getattr(claim, column) is not None:
                continue  # this one has already gone out
            due = entry["at"]
            if now < due:
                continue
            if now - due > DUNNING_GRACE:
                summary["skipped_stale"] += 1
                continue
            if action == "escalation_offer" and not gate_open:
                summary["skipped_ungated"] += 1
                continue
            message = _send_counterparty(
                db,
                claim,
                gateway,
                now,
                subject=DUNNING_SUBJECT[action],
                body=_dunning_body(db, claim, now),
            )
            if message is None:
                summary["skipped_no_email"] += 1
                continue  # finding F4: never a fake recipient, not even to a chaser
            setattr(claim, column, now)  # DISPATCHED, matching the alert columns
            summary[DUNNING_COUNTER[action]] += 1
    db.flush()
    return summary


def get_claim(db: Session, claim_id) -> DetentionClaim | None:
    return db.get(DetentionClaim, claim_id)


def claim_for_stop(db: Session, stop_ref) -> DetentionClaim | None:
    """This stop's claim: the open one if there is one, else the most recent.

    AI-CONTEXT: finding F1's second half. This was `db.scalar(select(...))` over an
    UNORDERED set, which does two wrong things at once. With several claims it raises
    `MultipleResultsFound` rather than answering — every caller here is a read on the
    driver's money, so the Meter, the claim screen and the Load tab all break together.
    With one it answers, but which one is whatever Postgres returns first, so a stop the
    driver has visited twice could show either visit's figure between two page loads.

    Open first, then newest, because every caller wants the claim that is RUNNING and
    only falls back to history when nothing is.
    """
    return db.scalars(
        select(DetentionClaim)
        .where(DetentionClaim.stop_ref == stop_ref)
        .order_by(
            case((DetentionClaim.state == ClaimState.open, 0), else_=1),
            DetentionClaim.created_at.desc(),
            # `created_at` is `now()`, which is TRANSACTION time — two claims written in
            # one transaction share it exactly. The id breaks that tie so the order is
            # total and this function cannot return different rows for the same question.
            DetentionClaim.id.desc(),
        )
        .limit(1)
    ).first()


def claim_for_receivable(db: Session, receivable_ref) -> DetentionClaim | None:
    # AI-CONTEXT: the reverse of `open_receivable` — money back to the stop it came
    # from. §13.5 needs it: a "claim paid" notification must deep-link to the exact
    # claim, and a receivable on its own knows only an account and an amount.
    return db.scalar(
        select(DetentionClaim).where(DetentionClaim.receivable_ref == receivable_ref)
    )


def claim_evidence(db: Session, claim: DetentionClaim) -> dict:
    # read-only view of the claim's F4 evidence chain — what's IN the pack, so the
    # driver can see the GPS evidence behind their claim (M3-FR5)
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
                # AI-CONTEXT: §23 entry 70's fix, which never reached THIS projection.
                # Entry 70 taught the pack renderer and `stop_evidence` to say what
                # happened rather than only which record type it was; `claim_evidence`
                # kept dropping `event`, so the claim screen could only ever render
                # "Action recorded". That became visible when the manual arrival stopped
                # being a manufactured GEOFENCE (entry 138) and correctly became a
                # USER_ACTION — the driver's own arrival would have read as a generic
                # action on the screen that argues their claim.
                # from the record's own payload, which `compose_pack` carries — the
                # payload itself stays OUT, because a timeline is a sequence of facts
                # and not a dump of internals (entry 70's own rule).
                "event": (t.get("payload") or {}).get("event"),
                "occurred_at": t["occurred_at"].isoformat() if t["occurred_at"] else None,
            }
            for t in pack.timeline
        ],
    }
